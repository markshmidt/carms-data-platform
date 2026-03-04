from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session
from services.api.app.llm.qa import ask_hybrid, qa
from services.api.app.database import get_session

router = APIRouter()

class QuestionRequest(BaseModel):
    question: str
 
@router.post("/qa")
def ask_question(request: QuestionRequest, session: Session = Depends(get_session)):
    return ask_hybrid(session, request.question)