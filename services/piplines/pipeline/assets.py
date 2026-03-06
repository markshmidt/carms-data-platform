import json
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path

from dagster import asset, asset_check, AssetExecutionContext, AssetCheckResult
from sqlmodel import select
from langchain_openai import OpenAIEmbeddings

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
from .parsing_helpers import (
    _clean_discipline_name,
    _extract_stream,
    _is_metadata_line,
    _next_nonempty,
    _take_until_metadata,
    normalize_text,
    split_discipline_and_site,
)
from sqlalchemy import text
from sqlmodel import SQLModel
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()
SQLModel.metadata.create_all(engine)

# ── Constants ──────────────────────────────────────────────────────
DATA_PATH = BASE_DIR / "data" / "1503_markdown_program_descriptions_v2.json"


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
    """
    Parse program records in two passes:
    1. First pass: Parse all records (may include cities in discipline names)
    2. Second pass: Analyze parsed data to identify common discipline bases,
       then extract city suffixes from disciplines that share the same base
    """
    parsed = []
    skipped_headers = []

    for record in staging_program_descriptions:
        # keep original lines for description joining
        raw_lines = record["clean_text"].split("\n")

        # cleaned lines for header detection
        lines = [ln.strip() for ln in raw_lines if ln.strip()]

        # Find the header line
        header_index = next(
            (
                i
                for i, line in enumerate(lines)
                if line.lstrip().startswith("#") and not line.lstrip().startswith("##")
            ),
            None
        ) # header index is the index of the line that starts with "#" and does not start with "##"

        if header_index is None:
            skipped_headers.append("NO HEADER")
            continue

        header_line = lines[header_index].lstrip("# ").strip() 

        # Handle header continuation: if header ends with "-", next line is site 
        # This handles cases like:
        # # School - Discipline -
        # St. John's
        site_continuation = None
        if header_line.endswith("-"):
            j = _next_nonempty(lines, header_index + 1) # next non empty line after header index
            if j is not None:
                next_line = lines[j].strip()
                # Only accept if it's NOT another header and NOT metadata
                if not next_line.startswith("#") and not _is_metadata_line(next_line):
                    site_continuation = next_line
                    # Remove the trailing "-" from header_line
                    header_line = header_line.rstrip("-").strip()

        # Normalize dash spacing
        header_line = header_line.replace("–", "-").replace("—", "-")
        header_line = re.sub(r"\s+-\s+", " - ", header_line)

        # clean extra spaces
        header_line = re.sub(r"\s+", " ", header_line).strip()

        # split header line into parts by " - "
        parts = [p.strip() for p in header_line.split(" - ") if p.strip()]
        if len(parts) < 2: #bad header line
            skipped_headers.append(header_line)
            continue

        # school is the first part in header like "McGill University - Medicine - Montreal"
        school_name = parts[0].strip()
        school_norm = normalize_text(school_name)
        school_name = SCHOOL_FR_TO_EN.get(school_norm, school_name)

        # discipline and site are the remaining parts in header like "Medicine - Montreal"
        # use known disciplines to identify where discipline ends and site begins (a bit hardcoded)
        remainder = parts[1:]
        if not remainder:
            skipped_headers.append(header_line)
            continue
        
        discipline_name, site_str = split_discipline_and_site(remainder)
        
        # If we found a site continuation (header ended with "-"), append it to site
        if site_continuation:
            if site_str:
                site_str = f"{site_str} {site_continuation}".strip()
            else:
                site_str = site_continuation
        
        site_parts = [site_str] if site_str else []
        
        if not discipline_name:
            skipped_headers.append(header_line)
            continue

        # Clean discipline name (fallback for edge cases - split_discipline_and_site should handle most)
        discipline_name = _clean_discipline_name(discipline_name)

        # take site parts until metadata line (no "Residency Match" hardcode)
        site_parts = _take_until_metadata(site_parts)
        program_site = " - ".join(site_parts).strip() if site_parts else ""

        # special case for Family Medicine integrated variants
        first_lower = discipline_name.lower()
        if first_lower.startswith("family medicine") or first_lower.startswith("médecine familiale"):
            discipline_base = "Family Medicine"
            allowed_integrated = {
                "integrated clinician scholar",
                "integrated emergency medicine",
            }
            #if program site contains an allowed integrated variant, add it to the discipline name
            if program_site and program_site.strip().lower() in allowed_integrated:
                discipline_name = f"{discipline_base} {program_site.strip()}"
                program_site = "" #make program site empty for now, we will add it back later
            else:
                discipline_name = discipline_base

        # French to English discipline mapping
        # Try full match first
        discipline_norm = normalize_text(discipline_name)
        discipline_name = DISCIPLINE_FR_TO_EN.get(discipline_norm, discipline_name)
        # if no match, try matching parts (for multi-part French disciplines)
        # for example "Oto-rhino-laryngologie et chirurgie cervico-faciale" -> "Oto-rhino-laryngologie and cervico-facial surgery"
        if discipline_name == discipline_norm:  # No translation happened
            # Split by " - " to check individual parts
            parts = discipline_name.split(" - ")
            translated_parts = []
            changed = False
            
            for part in parts:
                part_norm = normalize_text(part)
                translated_part = DISCIPLINE_FR_TO_EN.get(part_norm, part) #try matching again
                
                # Also try partial matches (for cases like "Oto-rhino-laryngologie et chirurgie cervico")
                if translated_part == part:
                    # Try to find a French discipline that starts with this part
                    for fr_name, en_name in DISCIPLINE_FR_TO_EN.items():
                        fr_norm = normalize_text(fr_name)
                        # Check if this part is the start of a French discipline name
                        if fr_norm.startswith(part_norm) or part_norm.startswith(fr_norm[:20]):
                            translated_part = en_name
                            changed = True
                            break
                
                if translated_part != part: #if the part was translated, add it to the translated parts
                    changed = True
                
                translated_parts.append(translated_part)
            
            # If any part was translated, reconstruct
            if changed:
                discipline_name = " - ".join(translated_parts)
            
            # Clean up any city names or location suffixes that might have been included in French discipline names
            # (e.g., "Oto-rhino-laryngologie et chirurgie cervico- faciale - Sherbrooke faciale")
            # structural approach: if a part appears after what looks like a complete discipline,
            # and it's short/capitalized, it's likely a city suffix that got included
            final_parts = discipline_name.split(" - ") #split discipline name into parts by " - " like "Oto-rhino-laryngologie and cervico-facial surgery" -> ["Oto-rhino-laryngologie", "and", "cervico-facial", "surgery"]
            cleaned_parts = []
            
            # Work through parts, keeping discipline parts and removing city-like suffixes
            for i, part in enumerate(final_parts):
                # Skip very short parts that appear at the end (likely city suffixes)
                # This handles cases like "faciale", "cervico" that are anatomical terms
                # but also cases where city names got included
                words = part.split()
                
                # If it's a very short part (1 word, <= 8 chars) at the end, might be a suffix (like "faciale", "cervico")
                # But only if we already have substantial discipline content (more than 15 chars)
                if i == len(final_parts) - 1 and len(words) == 1 and len(part) <= 8:
                    # Check if previous parts already form a substantial discipline name
                    prev_text = " - ".join(final_parts[:i])
                    if len(prev_text) > 15:  
                        continue
                
                cleaned_parts.append(part)
            
            if len(cleaned_parts) < len(final_parts): #if we removed some parts, join the remaining parts back together
                discipline_name = " - ".join(cleaned_parts).strip()

        # program stream id
        raw_id = record["program_id"]
        id_parts = raw_id.split("|") 
        if len(id_parts) != 2:
            raise ValueError(f"Invalid program_id format: {raw_id}")
        program_stream_id = id_parts[1].strip() #program stream id is the second part of the program_id after "|"

        # program stream is the stream of the program (IMG / CMG etc)
        program_stream = _extract_stream(lines, header_index)

        # program description
        description_start = next(
            (i for i, ln in enumerate(raw_lines) if ln.strip().startswith("##")),
            None
        )
        program_description = (
            "\n".join(raw_lines[description_start:]).strip()
            if description_start is not None
            else record["clean_text"].strip()
        )

        program_name = f"{school_name}/{discipline_name}/{program_site or ''}".rstrip("/")

        parsed.append({
            "program_stream_id": program_stream_id,
            "school_name": school_name,
            "discipline_name": discipline_name,
            "program_site": program_site,
            "program_stream": program_stream,
            "program_name": program_name,
            "program_description": program_description,
            "source_url": record["source_url"],
        })

    # Don't fail the whole pipeline if a few are weird
    if skipped_headers:
        print(f"[parse_program_records] skipped={len(skipped_headers)} sample={skipped_headers[:5]}")

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

    import os
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is required for embedding generation. "
            "Please set it in your environment or docker-compose.yaml"
        )
    
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=openai_api_key,
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
        
        # Batch embeddings to avoid rate limits (OpenAI allows ~3000 req/min)
        batch_size = 100
        total_batches = (len(programs_to_embed) + batch_size - 1) // batch_size
        
        context.log.info(f"Embedding {len(programs_to_embed)} programs in {total_batches} batches of {batch_size}")
        
        for batch_idx in range(0, len(programs_to_embed), batch_size):
            batch = programs_to_embed[batch_idx:batch_idx + batch_size]
            texts = [p.description for p in batch if p.description]
            
            if not texts:
                continue
                
            try:
                context.log.info(f"Processing batch {batch_idx // batch_size + 1}/{total_batches} ({len(texts)} texts)")
                vectors = embeddings.embed_documents(texts)
                
                # Assign back
                text_idx = 0
                for program in batch:
                    if program.description:
                        program.embedding = vectors[text_idx]
                        text_idx += 1
                
                session.commit()
                embedded += len(texts)
                context.log.info(f"Batch {batch_idx // batch_size + 1} complete. Total embedded: {embedded}")
                
            except Exception as e:
                context.log.error(f"Error embedding batch {batch_idx // batch_size + 1}: {e}")
                session.rollback()
                raise

        skipped = len(programs) - embedded

        context.add_output_metadata({
                "embedded": embedded,
                "skipped": skipped,
                "total": len(programs),
            })