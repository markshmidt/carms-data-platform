from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import RetrievalQA
from langchain_openai import ChatOpenAI
from .retriever import get_retriever
from ..config import OPENAI_API_KEY

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=OPENAI_API_KEY,
)

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
