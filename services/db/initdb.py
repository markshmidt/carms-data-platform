from sqlmodel import SQLModel
from services.api.app.database import engine

def init_db():
    SQLModel.metadata.create_all(engine)