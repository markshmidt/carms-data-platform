from pathlib import Path
from langchain_chroma import Chroma
from .embeddings import get_embeddings

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CHROMA_DIR = str(PROJECT_ROOT / "chroma_store")

def get_retriever():

    embeddings = get_embeddings()

    vectorstore = Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings
    )

    return vectorstore.as_retriever(search_kwargs={"k": 5})