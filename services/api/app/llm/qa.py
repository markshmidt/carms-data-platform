from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import RetrievalQA
from langchain_ollama import OllamaLLM
from .retriever import get_retriever

llm = OllamaLLM(model="phi")
retriever = get_retriever()
template = """
You are an assistant answering questions about Canadian residency programs.

STRICT RULES:
- Answer ONLY the user question.
- Do NOT include unrelated text.
- Do NOT repeat questions found inside the context.
- Do NOT add additional questions.
- Only summarize relevant information.

If the answer is not found in the context, respond:
"Not found in database."

Context:
{context}

User Question:
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