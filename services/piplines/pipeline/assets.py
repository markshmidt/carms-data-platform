from datetime import datetime
from dagster import asset
import json
import re
import sys
from pathlib import Path
from dagster import AssetExecutionContext, AssetCheckResult, asset_check
import hashlib

BASE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE_DIR))

from services.api.app.models import Discipline, Program, ProgramChangeLog, ProgramStream, School  # noqa: E402
from services.api.app.database import engine, Session  # noqa: E402
from sqlmodel import select  # noqa: E402
from langchain_huggingface import HuggingFaceEmbeddings

DATA_PATH = BASE_DIR / "data" / "raw" / "1503_markdown_program_descriptions_v2.json"


@asset
def raw_program_descriptions(context: AssetExecutionContext):
    """
    Loads raw scraped program descriptions JSON.
    """

    with open(DATA_PATH) as f:
        data = json.load(f)
        
    context.add_output_metadata({
        "records_count": len(data),
        "sample_id": data[0].get("id") if data else None
    })
    return data

@asset
def staging_program_descriptions(raw_program_descriptions):
    """
    Cleans markdown and extracts structured fields
    """

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
            "clean_text": text.strip()
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

        header_line = next(
            (line.strip("# ").strip() for line in lines if line.startswith("#")),
            None
        )

        if not header_line:
            skipped_headers.append("NO HEADER")
            continue

        parts = header_line.split(" - ") # school_name - discipline_name - program_site

        school_name = parts[0].strip()

        # If header contains site normally (725 cases)
        if len(parts) >= 3 and parts[-1].strip():
            program_site = parts[-1].strip()
            discipline_name = " - ".join(parts[1:-1]).strip()

        # If header ends with dash (site missing) (90 cases)
        elif len(parts) >= 2:
            discipline_name = " - ".join(parts[1:]).strip(" -")
            program_site = None

            # Find index of header in original lines
            header_index = next(
                i for i, line in enumerate(lines)
                if line.startswith("#")
            )

            # Look for first non-empty line after header (like "#  University of Manitoba - Family Medicine integrated Clinician Scholar -\nWinnipeg  \n  )
            for candidate in lines[header_index + 1:]:
                candidate = candidate.strip()
                if candidate and not candidate.startswith("#"):
                    program_site = candidate
                    break

            if not program_site:
                raise ValueError(f"Could not determine site for: {header_line}")

        else:
            raise ValueError(f"Unexpected header format: {header_line}")
        
    
        raw_id = record["program_id"]
        parts = raw_id.split("|")
        if len(parts) != 2:
            raise ValueError(f"Invalid program_id format: {raw_id}")

        program_stream_id = parts[1].strip()

        program_stream = next(
            (line.strip() for line in lines if "Stream" in line),
            "Unknown"
        )

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

    # HARD FAIL if anything skipped
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

    with Session(engine) as session:
        count = session.exec(select(Program)).all()

    return AssetCheckResult(
        passed=len(count) == 815,
        metadata={"db_program_count": len(count)}
    )

@asset
def embed_programs(context: AssetExecutionContext, load_programs_to_db):

    embeddings = HuggingFaceEmbeddings(
        model_name="intfloat/e5-small-v2"
    )

    embedded = 0
    skipped = 0

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
        texts = [p.description for p in programs_to_embed]

        #Batch embed (THIS IS THE KEY)
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