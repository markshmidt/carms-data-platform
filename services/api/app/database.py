from sqlmodel import create_engine, Session
from .config import DATABASE_URL, SQL_ECHO

engine = create_engine(DATABASE_URL, echo=SQL_ECHO)


def get_session():
    with Session(engine) as session:
        yield session