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
from .normalization import DISCIPLINE_FR_TO_EN, SCHOOL_FR_TO_EN
import unicodedata
from sqlalchemy import text
from sqlmodel import SQLModel
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()
SQLModel.metadata.create_all(engine)

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()

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

    parsed = []
    skipped_headers = []

    for record in staging_program_descriptions:
        lines = record["clean_text"].split("\n")

        # Find header
        header_index = next(
            (i for i, line in enumerate(lines) if line.startswith("#")),
            None
        )

        if header_index is None:
            skipped_headers.append("NO HEADER")
            continue

        header_line = lines[header_index].strip("# ").strip()

        # Handle wrapped header (French long ones)
        if header_index + 1 < len(lines):
            next_line = lines[header_index + 1].strip()

            if (
                next_line
                and not next_line.startswith("#")
                and "Stream" not in next_line
                and "Residency Match" not in next_line
            ):
                header_line = f"{header_line} {next_line}"
            if header_line.endswith("-"):
                header_line = f"{header_line}{next_line}"
            else:
                header_line = f"{header_line} {next_line}"

        # Normalize dashes + spacing
        header_line = header_line.replace("–", "-").replace("—", "-")
        header_line = re.sub(r"\s*-\s*", " - ", header_line)
        header_line = re.sub(r"\s+", " ", header_line).strip()

        parts = header_line.split(" - ")

        if len(parts) < 2:
            skipped_headers.append(header_line)
            continue

        school_name = parts[0].strip()
        school_norm = normalize_text(school_name)
        school_name = SCHOOL_FR_TO_EN.get(school_norm, school_name)
        remainder = [p.strip() for p in parts[1:] if p.strip()]

        # Discipline parsing logic

        discipline_name = None
        program_site = None

        if not remainder:
            skipped_headers.append(header_line)
            continue

        first = remainder[0]
        first_lower = first.lower()

       # Family Medicine (EN + FR)

        if (
            first_lower.startswith("family medicine")
            or first_lower.startswith("médecine familiale")
        ):

            discipline_base = "Family Medicine"

            # Exact allowed integrated variants
            allowed_integrated = {
                "integrated clinician scholar",
                "integrated emergency medicine",
            }

            if len(remainder) > 1:
                second_clean = remainder[1].strip().lower()

                if second_clean in allowed_integrated:
                    discipline_name = f"{discipline_base} {remainder[1]}"
                    program_site = " - ".join(remainder[2:]) if len(remainder) > 2 else None
                else:
                    # everything else is site
                    discipline_name = discipline_base
                    program_site = " - ".join(remainder[1:]) if len(remainder) > 1 else None
            else:
                discipline_name = discipline_base
                program_site = None

        else:
            discipline_name = remainder[0]
            program_site = " - ".join(remainder[1:]) if len(remainder) > 1 else None

        # French → English mapping

        discipline_norm = normalize_text(discipline_name)
        discipline_name = DISCIPLINE_FR_TO_EN.get(
            discipline_norm,
            discipline_name
        )

        # Program ID

        raw_id = record["program_id"]
        id_parts = raw_id.split("|")

        if len(id_parts) != 2:
            raise ValueError(f"Invalid program_id format: {raw_id}")

        program_stream_id = id_parts[1].strip()

        # Stream

        program_stream = next(
            (line.strip() for line in lines if "Stream" in line),
            "Unknown"
        )

        # Description

        description_start = next(
            (i for i, line in enumerate(lines) if line.startswith("##")),
            None
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
            "source_url": record["source_url"]
        })

    if skipped_headers:
        raise Exception(
            f"{len(skipped_headers)} records skipped. Example: {skipped_headers[:5]}"
        )

    print("Total parsed:", len(parsed))
    return parsed

@asset
def load_programs_to_db(context: AssetExecutionContext, parse_program_records):

   
    inserted = 0
    updated = 0
    skipped = 0
    change_logs = 0

    with Session(engine) as session:
        try:
            for record in parse_program_records:

                # --- Compute hash ---
                new_hash = hashlib.sha256(
                    record["program_description"].encode("utf-8")
                ).hexdigest()

                # --- Get or create school ---
                school = session.exec(
                    select(School).where(School.name == record["school_name"])
                ).first()

                if not school:
                    school = School(name=record["school_name"])
                    session.add(school)
                    session.flush()

                # --- Get or create discipline ---
                discipline = session.exec(
                    select(Discipline).where(
                        Discipline.name == record["discipline_name"]
                    )
                ).first()

                if not discipline:
                    discipline = Discipline(name=record["discipline_name"])
                    session.add(discipline)
                    session.flush()

                # --- Get or create stream ---
                stream = session.exec(
                    select(ProgramStream).where(
                        ProgramStream.name == record["program_stream"]
                    )
                ).first()

                if not stream:
                    stream = ProgramStream(name=record["program_stream"])
                    session.add(stream)
                    session.flush()

                # --- Get existing program ---
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
        "total_processed": len(parse_program_records)
    })

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "change_logs": change_logs,
    }

@asset_check(asset=load_programs_to_db)
def check_program_count(context):
    """Verify the expected number of programs ended up in the database."""

    with Session(engine) as session:
        count = session.exec(select(Program)).all()

    return AssetCheckResult(
        passed=len(count) == 815,
        metadata={"db_program_count": len(count)}
    )

@asset
def embed_programs(context: AssetExecutionContext, load_programs_to_db):
    """Generate vector embeddings for programs that don't have one yet."""

    embeddings = HuggingFaceEmbeddings(
        model_name="intfloat/e5-small-v2"
    )

    embedded = 0
    skipped = 0

    with Session(engine) as session:

        programs = session.exec(
            select(Program).where(Program.embedding.is_(None))
        ).all()

        programs_to_embed = [p for p in programs if p.embedding is None]

        if not programs_to_embed:
            context.add_output_metadata({
                "embedded": 0,
                "skipped": len(programs),
                "total": len(programs),
            })
            return 
        texts = [p.description for p in programs_to_embed]
        vectors = embeddings.embed_documents(texts)

        # Assign back
        for program, vector in zip(programs_to_embed, vectors):
            program.embedding = vector

        session.commit()

        context.add_output_metadata({
                "embedded": len(programs_to_embed),
                "skipped": len(programs) - len(programs_to_embed),
                "total": len(programs),
            })