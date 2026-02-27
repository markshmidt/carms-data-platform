from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import RetrievalQA
from langchain_ollama import OllamaLLM
from .retriever import get_retriever

llm = OllamaLLM(model="phi")
retriever = get_retriever()

template = """
You are an assistant answering questions about Canadian residency programs.

You MUST answer ONLY using the provided context.
If the answer is not present in the context, say:

"Not found in database."

Context:
{context}

Question:
{question}

Answer:
"""

prompt = PromptTemplate(
    template=template,
    input_variables=["context", "question"],
)

qa = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
    chain_type_kwargs={"prompt": prompt},
    return_source_documents=True,
)