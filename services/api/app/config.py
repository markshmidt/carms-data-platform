"""
Centralized configuration management.

All configuration values are read from environment variables.
No hardcoded defaults - missing required values will raise clear errors.
"""
import os
from pathlib import Path
from dotenv import load_dotenv


# ── Load .env file from project root ─────────────────────────────────
# Find project root (3 levels up from this file: services/api/app/config.py)
_project_root = Path(__file__).resolve().parents[3]
_env_file = _project_root / ".env"

if _env_file.exists():
    load_dotenv(_env_file)


def _require_env(key: str) -> str:
    """Get a required environment variable, raise if missing."""
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set.\n"
            f"Please set it in your .env file or export it as an environment variable.\n"
            f"Expected location for .env file: {_env_file}"
        )
    return value


# ── Database Configuration ──────────────────────────────────────────
DATABASE_URL: str = _require_env("DATABASE_URL")

# SQLAlchemy echo mode (for debugging SQL queries)
SQL_ECHO: bool = os.getenv("SQL_ECHO", "false").lower() == "true"

API_URL: str = os.getenv("API_URL", "http://localhost:8000")              # used by Streamlit


# ── OpenAI Configuration ──────────────────────────────────────────
OPENAI_API_KEY: str = _require_env("OPENAI_API_KEY")
