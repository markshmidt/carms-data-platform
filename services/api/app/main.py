import sys
from pathlib import Path

# Ensure project root is in sys.path for cross-package imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fastapi import FastAPI
from sqlalchemy import text
from sqlmodel import SQLModel
from services.api.app.database import engine
from services.api.routes import health, programs, qa

app = FastAPI(title="CaRMS Data Platform")

app.include_router(health.router)
app.include_router(programs.router)
app.include_router(qa.router)


@app.on_event("startup")
def on_startup():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    SQLModel.metadata.create_all(engine)


@app.get("/")
def root():
    return {"message": "CaRMS API is running"}
