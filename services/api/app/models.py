from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List

class Discipline(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    programs: List["Program"] = Relationship(back_populates="discipline")


class School(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    programs: List["Program"] = Relationship(back_populates="school")


class ProgramStream(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: Optional[str] = Field(default=None)

    programs: List["Program"] = Relationship(back_populates="stream")


class Program(SQLModel, table=True):
    program_stream_id: str = Field(primary_key=True)  # ← IMPORTANT FIX

    name: str
    site: str
    url: Optional[str] = None
    description: Optional[str] = None

    discipline_id: int = Field(foreign_key="discipline.id")
    school_id: int = Field(foreign_key="school.id")
    stream_id: int = Field(foreign_key="programstream.id")

    discipline: Optional[Discipline] = Relationship(back_populates="programs")
    school: Optional[School] = Relationship(back_populates="programs")
    stream: Optional[ProgramStream] = Relationship(back_populates="programs")