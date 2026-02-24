from fastapi import FastAPI, Depends
from sqlmodel import SQLModel, Session
from .database import engine, get_session
from .models import Program, Discipline

app = FastAPI()


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


@app.get("/")
def root():
    return {"message": "CaRMS API is running 🚀"}


@app.post("/programs")
def create_program(program: Program, session: Session = Depends(get_session)):
    session.add(program)
    session.commit()
    session.refresh(program)
    return program

@app.get("/programs")
def get_programs(session: Session = Depends(get_session)):
    programs = session.exec(select(Program)).all()
    return programs

@app.get("/programs/{program_id}")
def get_program(program_id: int, session: Session = Depends(get_session)):
    program = session.get(Program, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    return program
@app.get("/disciplines")
def get_disciplines(session: Session = Depends(get_session)):
    disciplines = session.exec(select(Discipline)).all()
    return disciplines
@app.get("/disciplines/{discipline_id}")
def get_discipline(discipline_id: int, session: Session = Depends(get_session)):
    discipline = session.get(Discipline, discipline_id)
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")
    return discipline
@app.get("/schools")
def get_schools(session: Session = Depends(get_session)):
    schools = session.exec(select(School)).all()
    return schools
@app.get("/schools/{school_id}")
def get_school(school_id: int, session: Session = Depends(get_session)):
    school = session.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return school
@app.get("/program-streams")
def get_program_streams(session: Session = Depends(get_session)):
    program_streams = session.exec(select(ProgramStream)).all()
    return program_streams
@app.get("/program-streams/{program_stream_id}")
def get_program_stream(program_stream_id: int, session: Session = Depends(get_session)):
    program_stream = session.get(ProgramStream, program_stream_id)
    if not program_stream:
        raise HTTPException(status_code=404, detail="Program stream not found")
    return program_stream

