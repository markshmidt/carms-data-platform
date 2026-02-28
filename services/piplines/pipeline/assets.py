import json
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path

from dagster import asset, asset_check, AssetExecutionContext, AssetCheckResult
from sqlmodel import select
from langchain_huggingface import HuggingFaceEmbeddings

# ── Project root on sys.path so cross-service imports work ─────────
BASE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE_DIR))

from services.api.app.models import (  # noqa: E402
    Discipline,
    Program,
    ProgramChangeLog,
    ProgramStream,
    School,
)
from services.api.app.database import engine, Session  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────
DATA_PATH = BASE_DIR / "data" / "raw" / "1503_markdown_program_descriptions_v2.json"


# ═══════════════════════════════════════════════════════════════════
#  Assets
# ═══════════════════════════════════════════════════════════════════


@asset
def raw_program_descriptions(context: AssetExecutionContext):
    """Load raw scraped program-descriptions JSON."""

    with open(DATA_PATH) as f:
        data = json.load(f)

    context.add_output_metadata({
        "records_count": len(data),
        "sample_id": data[0].get("id") if data else None,
    })
    return data


@asset
def staging_program_descriptions(raw_program_descriptions):
    """Clean markdown and extract structured fields."""

    cleaned = []

    for record in raw_program_descriptions:
        program_id = record.get("id")
        text = record.get("page_content", "")
        source = record.get("metadata", {}).get("source")

        # Remove excessive newlines
        text = re.sub(r"\n+", "\n", text)

        cleaned.append({
            "program_id": program_id,
            "source_url": source,
            "clean_text": text.strip(),
        })

    print(len(cleaned))
    print(cleaned[0])

    return cleaned


@asset
def parse_program_records(staging_program_descriptions):
    """Parse header, discipline, school, site, and stream from each record."""

    parsed = []
    skipped_headers = []

    for record in staging_program_descriptions:
        lines = record["clean_text"].split("\n")

        # ── Extract header ─────────────────────────────────────────
        header_line = next(
            (line.strip("# ").strip() for line in lines if line.startswith("#")),
            None,
        )

        if not header_line:
            skipped_headers.append("NO HEADER")
            continue

        parts = header_line.split(" - ")
        school_name = parts[0].strip()

        # Header contains site normally (725 cases)
        if len(parts) >= 3 and parts[-1].strip():
            program_site = parts[-1].strip()
            discipline_name = " - ".join(parts[1:-1]).strip()

        # Header ends with dash — site on the next line (90 cases)
        elif len(parts) >= 2:
            discipline_name = " - ".join(parts[1:]).strip(" -")
            program_site = None

            header_index = next(
                i for i, line in enumerate(lines)
                if line.startswith("#")
            )

            for candidate in lines[header_index + 1:]:
                candidate = candidate.strip()
                if candidate and not candidate.startswith("#"):
                    program_site = candidate
                    break

            if not program_site:
                raise ValueError(f"Could not determine site for: {header_line}")

        else:
            raise ValueError(f"Unexpected header format: {header_line}")

        # ── Extract program_stream_id ──────────────────────────────
        raw_id = record["program_id"]
        id_parts = raw_id.split("|")
        if len(id_parts) != 2:
            raise ValueError(f"Invalid program_id format: {raw_id}")

        program_stream_id = id_parts[1].strip()

        # ── Extract stream label ───────────────────────────────────
        program_stream = next(
            (line.strip() for line in lines if "Stream" in line),
            "Unknown",
        )

        # ── Extract description body ──────────────────────────────
        description_start = next(
            (i for i, line in enumerate(lines) if line.startswith("##")),
            None,
        )

        program_description = (
            "\n".join(lines[description_start:])
            if description_start is not None
            else record["clean_text"]
        )

        parsed.append({
            "program_stream_id": program_stream_id,
            "school_name": school_name,
            "discipline_name": discipline_name,
            "program_site": program_site,
            "program_stream": program_stream,
            "program_name": f"{school_name}/{discipline_name}/{program_site}",
            "program_description": program_description,
            "source_url": record["source_url"],
        })

    # Hard-fail if any records were skipped
    if skipped_headers:
        raise Exception(
            f"{len(skipped_headers)} records skipped. Example: {skipped_headers[:5]}"
        )

    print("Total parsed:", len(parsed))
    return parsed


@asset
def load_programs_to_db(context: AssetExecutionContext, parse_program_records):
    """Upsert parsed programs into the database, tracking description changes."""

    inserted = 0
    updated = 0
    skipped = 0
    change_logs = 0

    with Session(engine) as session:
        try:
            for record in parse_program_records:

                # ── Hash the description ───────────────────────────
                new_hash = hashlib.sha256(
                    record["program_description"].encode("utf-8")
                ).hexdigest()

                # ── Get or create School ───────────────────────────
                school = session.exec(
                    select(School).where(School.name == record["school_name"])
                ).first()

                if not school:
                    school = School(name=record["school_name"])
                    session.add(school)
                    session.flush()

                # ── Get or create Discipline ───────────────────────
                discipline = session.exec(
                    select(Discipline).where(
                        Discipline.name == record["discipline_name"]
                    )
                ).first()

                if not discipline:
                    discipline = Discipline(name=record["discipline_name"])
                    session.add(discipline)
                    session.flush()

                # ── Get or create ProgramStream ────────────────────
                stream = session.exec(
                    select(ProgramStream).where(
                        ProgramStream.name == record["program_stream"]
                    )
                ).first()

                if not stream:
                    stream = ProgramStream(name=record["program_stream"])
                    session.add(stream)
                    session.flush()

                # ── Get existing program or insert ─────────────────
                program = session.get(Program, record["program_stream_id"])

                if not program:
                    program = Program(
                        program_stream_id=record["program_stream_id"],
                        name=record["program_name"],
                        site=record["program_site"],
                        url=record["source_url"],
                        description=record["program_description"],
                        description_hash=new_hash,
                        school_id=school.id,
                        discipline_id=discipline.id,
                        stream_id=stream.id,
                    )
                    session.add(program)
                    inserted += 1

                else:
                    if program.description_hash != new_hash:
                        session.add(
                            ProgramChangeLog(
                                program_stream_id=program.program_stream_id,
                                old_hash=program.description_hash,
                                new_hash=new_hash,
                            )
                        )
                        program.description = record["program_description"]
                        program.description_hash = new_hash
                        program.updated_at = datetime.utcnow()
                        updated += 1
                        change_logs += 1
                    else:
                        skipped += 1

            session.commit()

        except Exception:
            session.rollback()
            raise

    context.add_output_metadata({
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "change_logs": change_logs,
        "total_processed": len(parse_program_records),
    })

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "change_logs": change_logs,
    }


# ═══════════════════════════════════════════════════════════════════
#  Asset Checks
# ═══════════════════════════════════════════════════════════════════


@asset_check(asset=load_programs_to_db)
def check_program_count(context):
    """Verify the expected number of programs ended up in the database."""

    with Session(engine) as session:
        count = session.exec(select(Program)).all()

    return AssetCheckResult(
        passed=len(count) == 815,
        metadata={"db_program_count": len(count)},
    )


# ═══════════════════════════════════════════════════════════════════
#  Embedding
# ═══════════════════════════════════════════════════════════════════


@asset
def embed_programs(context: AssetExecutionContext, load_programs_to_db):
    """Generate vector embeddings for programs that don't have one yet."""

    embeddings = HuggingFaceEmbeddings(model_name="intfloat/e5-small-v2")

    with Session(engine) as session:
        programs = session.exec(select(Program)).all()
        programs_to_embed = [p for p in programs if not p.embedding]

        if not programs_to_embed:
            context.add_output_metadata({
                "embedded": 0,
                "skipped": len(programs),
                "total": len(programs),
            })
            return

        # Batch embed all descriptions at once
        texts = [p.description for p in programs_to_embed]
        vectors = embeddings.embed_documents(texts)

        for program, vector in zip(programs_to_embed, vectors):
            program.embedding = vector

        session.commit()

        context.add_output_metadata({
            "embedded": len(programs_to_embed),
            "skipped": len(programs) - len(programs_to_embed),
            "total": len(programs),
        })
