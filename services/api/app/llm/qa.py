from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_classic.chains import RetrievalQA

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent

from .retriever import get_retriever
from ..config import OPENAI_API_KEY, DATABASE_URL

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

# to avoid connection attempts at module import time
_sql_agent = None
_sql_db = None

def _get_sql_agent():
    """Get or create SQL agent lazily."""
    global _sql_agent, _sql_db
    if _sql_agent is None:
        _sql_db = SQLDatabase.from_uri(DATABASE_URL,
                                       include_tables=["program", "school", "discipline", "programstream", "programchangelog"],) # create wrapper around database
        _sql_agent = create_sql_agent( #create agent that can call SQL functions
            llm=llm,
            db=_sql_db,
            verbose=True,  # Set to True for debugging
            agent_type="openai-tools",  # Uses OpenAI function calling
            prefix="""
You are a data assistant querying a PostgreSQL database about Canadian residency programs.

The database schema:

program (
    program_stream_id TEXT PRIMARY KEY,
    name TEXT,
    site TEXT,
    url TEXT,
    description TEXT,
    discipline_id INTEGER REFERENCES discipline(id),
    school_id INTEGER REFERENCES school(id),
    stream_id INTEGER REFERENCES programstream(id),
    description_hash TEXT,
    embedding VECTOR(1536),
    updated_at TIMESTAMP
)

school (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)

discipline (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)

programstream (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    category TEXT
)

programchangelog (
    id INTEGER PRIMARY KEY,
    program_stream_id TEXT REFERENCES program(program_stream_id),
    changed_at TIMESTAMP,
    old_hash TEXT,
    new_hash TEXT
)

Important:
- Use JOINs to connect programs with schools, disciplines, and streams via foreign keys.
- When counting or aggregating, use proper SQL aggregation functions (COUNT, SUM, AVG, etc.).
- Check program description with ISLIKE("%%") to find program that matches words in the question. Use similarity search to find the most similar program.
- Use French to English translation to check if french programs descriptions have the same words as the question.
- Always return the final answer in natural language, not just raw numbers.
- If no data is found, say "Not found in database."
"""
        )
    return _sql_agent


_ANALYTICS_HINTS = (
    "how many", "count", "number of", "total",
    "average", 
    "most", "least", "top ", "by discipline", "group by",
    "percentage", "percent", "ratio",
)

def _should_use_sql(question: str) -> bool:
    q = question.lower().strip()
    return any(h in q for h in _ANALYTICS_HINTS) #if question contains any of the hints, returns True and use SQL


# guard
_FORBIDDEN_SQL = (
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "grant", "revoke", "vacuum", "analyze",
)
def _run_sql(question: str) -> dict[str, Any]:
    """
    Use SQL agent to answer analytics questions.
    The agent uses SQLDatabaseToolkit which provides safe SQL execution.
    """
    try:
        # Get SQL agent (lazy initialization)
        agent = _get_sql_agent()
        # Agent handles SQL generation, execution, and formatting
        result = agent.invoke({"input": question})
        
        # The agent result structure can vary - try multiple keys
        answer = None
        if isinstance(result, dict):
            answer = result.get("output") or result.get("result") or result.get("answer")
        elif isinstance(result, str):
            answer = result
        
        if not answer or not answer.strip():
            answer = "Not found in database."
        else:
            answer = str(answer).strip()
        
        return {
            "mode": "sql",
            "answer": answer,
        }
    except Exception as e:
        # If agent fails, log and re-raise so caller can fall back to RAG
        print(f"SQL agent error: {e}")
        import traceback
        traceback.print_exc()
        raise e


def ask_hybrid(session: Session, question: str) -> dict[str, Any]:
    """
    Main entry point:
    - routes analytics/count questions to SQL
    - routes everything else to RAG
    """
    if _should_use_sql(question):
        try:
            return _run_sql(question)
        except Exception as e:
            # If SQL fails for any reason, fall back to RAG
            # Log the error for debugging (you can add proper logging here)
            print(f"SQL agent error: {e}")
            import traceback
            traceback.print_exc()
            pass

    # RAG fallback
    rag = qa.invoke({"query": question})
    answer = (rag.get("result") or "").strip() or "Not found in database."

    return {
        "mode": "rag",
        "answer": answer,
        "sources": [getattr(d, "metadata", {}) for d in rag.get("source_documents", [])],
    }