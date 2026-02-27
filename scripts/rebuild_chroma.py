"""Rebuild the Chroma vector store from program descriptions in the database."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from services.api.app.llm.embeddings import get_embeddings  # noqa: E402
from services.api.app.database import engine  # noqa: E402
from services.api.app.models import Program  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

CHROMA_DIR = str(ROOT / "chroma_store")


def main():
    embeddings = get_embeddings()

    with Session(engine) as session:
        programs = session.exec(select(Program)).all()

    docs = []
    for p in programs:
        if p.description:
            docs.append(Document(
                page_content=p.description,
                metadata={"program_id": p.program_stream_id},
            ))

    print(f"Building Chroma store with {len(docs)} documents at {CHROMA_DIR} ...")
    Chroma.from_documents(docs, embeddings, persist_directory=CHROMA_DIR)
    print(f"Done! Chroma store rebuilt with {len(docs)} documents.")


if __name__ == "__main__":
    main()
