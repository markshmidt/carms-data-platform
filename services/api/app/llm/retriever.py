from langchain_chroma import Chroma
from .embeddings import get_embeddings

def get_retriever():

    embeddings = get_embeddings()

    vectorstore = Chroma(
        persist_directory="./chroma_store",
        embedding_function=embeddings
    )

    return vectorstore.as_retriever(search_kwargs={"k": 5})