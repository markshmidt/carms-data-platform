from fastapi import APIRouter
from pydantic import BaseModel
from services.api.app.llm.qa import qa

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str


@router.post("/qa")
def ask_question(request: QuestionRequest):

    result = qa.invoke(request.question)

    return {
        "answer": result["result"],
        "sources": [
            doc.metadata for doc in result.get("source_documents", [])
        ]
    }
