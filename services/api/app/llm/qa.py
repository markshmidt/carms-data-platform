from langchain_classic.chains import RetrievalQA
from langchain_ollama import OllamaLLM
from .retriever import get_retriever

def get_qa_chain():

    retriever = get_retriever()

    llm = OllamaLLM(model="phi")

    return RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True
    )