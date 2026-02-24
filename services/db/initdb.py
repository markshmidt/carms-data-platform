from sqlmodel import SQLModel
from services.api.app.database import engine
from services.api.app import models  # ensures tables are registered

def init_db():
    SQLModel.metadata.create_all(engine)