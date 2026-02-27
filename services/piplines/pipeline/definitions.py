from dagster import Definitions
from .assets import check_program_count, embed_programs, load_programs_to_db, parse_program_records, raw_program_descriptions, staging_program_descriptions

defs = Definitions(
    assets=[
        raw_program_descriptions,
        staging_program_descriptions,
        parse_program_records,
        load_programs_to_db,
        embed_programs,
        check_program_count,
        
    ]
)