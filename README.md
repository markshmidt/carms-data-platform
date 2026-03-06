# CaRMS Data Platform
Modern Data Engineering + AI RAG ans SQL analytic system using PostgreSQL, SQLModel, Alembic, Dagster, FastAPI, LangChain, pgvector, Ollama & OpenAI


<img width="1914" height="1071" alt="image" src="https://github.com/user-attachments/assets/135999a3-09ec-4e5c-90f7-724962a89732" />


## Project Overview

This project modernizes CaRMS residency program data into a fully containerized, production-style AI-enabled data platform. The system is designed to showcase modern Data Engineering, Data Science, Data Analysis 
and AI system design using an industry-relevant stack.

It demonstrates:
- End-to-end ETL pipeline (Dagster)
- Relational modeling (PostgreSQL + SQLModel)
- Schema migrations (Alembic)
- Change detection with hashing
- Vector search (pgvector)
- Retrieval-Augmented Generation (RAG)
- LLM integration (OpenAI support)
- REST API (FastAPI)
- Interactive dashboard (Streamlit)
- Docker-based orchestration
- Cloud deployment (AWS EC2)

The platform transforms scraped residency program descriptions into:

• Structured relational analytics  
• Vector searchable knowledge base  
• Natural language AI assistant
<img width="1878" height="1048" alt="image" src="https://github.com/user-attachments/assets/30043cbb-83c9-4441-912a-c950b8cbce05" />

---

# Architecture Overview

Scraped Data  
↓  
Dagster ETL Pipeline  
↓  
PostgreSQL Relational Database  
↓  
Embeddings Generation  
↓  
Vector Store (Chroma / pgvector)  
↓  
FastAPI Backend  
↓  
Hybrid AI Engine (RAG + SQL Agent)  
↓  
OpenAI LLM  
↓  
Streamlit User Interface  

---

# Data Engineering Layer

## Parsing & Normalization

Scraped CaRMS program data contained many inconsistencies such as:

- English and French naming (696 against 119 programs)
- Multi-line discipline names (most programs were in format school - name - site, while some might have line break)
- Site naming variations (Belleville - Quinte, though contains "-", should be parsed as site together)
- Irregular dash formatting (-, "—", etc)

The parser resolves these issues using:

• dash normalization  
• continuation line detection  (if the next line is not a stream or residency match, add it to the header)
• discipline/site separation  
• multilingual normalization  (through normalization dicts mapping french to english names)
• integrated program detection (if programs contains words like integrated)

The parsing strategy intentionally avoids hardcoded discipline lists to remain robust to future changes.

---

# Dagster Data Pipeline

Dagster orchestrates the ETL workflow through assets:

- raw_program_descriptions
- staging_program_descriptions
- parse_program_records
- load_programs_to_db
- check_program_count
- embed_programs
And helper functions / normalisations dict.
Dagster Web UI allows manual materialization of assets.
<img width="1152" height="248" alt="image" src="https://github.com/user-attachments/assets/710f2131-5e02-4dfc-8a43-6de0e77c3488" />

---


# Database Design

Relational schema implemented using **SQLModel**.

Entities:

- Program
- School
- Discipline
- ProgramStream
- ProgramChangeLog

---

# Change Detection with Hashing

Each program description is hashed in **load_programs_to_db()** using:

    hashlib.sha256(description.encode()).hexdigest()

During pipeline execution:

• unchanged programs are skipped  
• changed programs are updated  
• updates are recorded in ChangeLog  
<img width="317" height="144" alt="image" src="https://github.com/user-attachments/assets/60d2b1a7-c87d-4162-ad9a-e773ff473f68" />

Benefits:

- efficient incremental updates
- historical tracking
- idempotent ETL runs

---

# Alembic Migrations

Database schema evolution is managed with **Alembic**.
Why Alembic?
- Version-controlled schema changes
- Safe database evolution
- Reproducible deployment
Example workflow:

    alembic revision --autogenerate -m "init schema"
    alembic upgrade head

Alembic ensures consistent schema across:

- local development
- Docker environment
- cloud deployment

---

# Vector Search Layer

Program descriptions are embedded into vector representations for semantic search.

Embeddings are generated using OpenAI:
```
return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=OPENAI_API_KEY,
    )
```

Vectors are stored in:

• **Chroma vector store** for retrieval  
```
vectorstore = Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings
    )
```
• optional **pgvector** support within PostgreSQL

This enables semantic queries such as:

"Which programs emphasize rural training?"

instead of strict keyword matching.

---

# AI Layer — Hybrid RAG + SQL System

The AI assistant uses a **hybrid architecture** combining:

### Retrieval Augmented Generation (RAG)

Used for descriptive questions:

Example:

"Which programs require French?"

Workflow:

1. Question embedding generated
2. Vector similarity search retrieves relevant program descriptions
3. Context is inserted into LLM prompt
4. LLM generates grounded answer

---

### SQL Analytics Agent

Used for **numerical or statistical questions** such as:

- "How many programs require French?"
- "Which discipline has the most programs?"
- "Average number of streams per discipline"

The system automatically detects analytic questions and routes them to a **LangChain SQL Agent** which:

1. Generates SQL queries
2. Executes them against PostgreSQL
3. Converts results into natural language answers

This hybrid approach ensures:

• precise analytics via SQL  
• contextual explanations via RAG

---

# LangChain Orchestration

LangChain manages:

- LLM invocation
- vector retrieval
- SQL agent execution
- hybrid routing logic

Routing logic:

analytics question → SQL agent  
descriptive question → RAG pipeline

---

# Backend API — FastAPI

FastAPI provides:

• REST API endpoints  
• analytics endpoints  

Example AI endpoint:

```     
@router.post("/qa")
def ask_question(request: QuestionRequest, session: Session = Depends(get_session)):
    return ask_hybrid(session, request.question)
```
---

# Streamlit UI

The Streamlit interface provides:

• question input field  
• answer visualization  
• source document inspection  
• analytics visualizations  

It communicates with the FastAPI backend.

---

# Containerization

The platform runs as a **multi‑service Docker architecture**.

Docker Compose services:

- carms_postgres (pgvector database)
- carms_api (FastAPI backend)
- carms_streamlit (UI)
- carms_dagster-webserver
- carms_dagster-daemon
---

# Cloud Deployment

The system runs on an **AWS EC2 instance (Ubuntu Linux)**.

Deployment steps:

1. Build Docker image locally
2. Push image to Docker Hub
3. Pull image on server
4. Run `docker compose up`

For evaluation purposes:

**The deployment IP will be provided to CaRMS reviewers or employers upon request.**

---

# How To Run Locally

Clone repository:

    git clone https://github.com/markshmidt/carms-data-platform/
    cd carms-data-platform

Create .env file with:
```
OPENAI_API_KEY=your_key_here
DATABASE_URL=postgresql://carms_user:carms_password@localhost:5433/carms_db
```
Start containers:

    docker compose up --build

Access services:

FastAPI  
http://localhost:8000

Streamlit UI  
http://localhost:8501

Dagster UI  
http://localhost:3000

---

# Running the Data Pipeline

After starting containers:

1. Open Dagster UI
2. Materialize all assets.

This will populate the database and build the vector index.

---

# Development Stack
Database: PostgreSQL + pgvector  
ORM: SQLModel  
Migrations: Alembic  
Pipeline: Dagster  
API: FastAPI  
LLM Orchestration: LangChain  
LLM Providers: OpenAI  
UI: Streamlit  
Containerization: Docker Compose  
Dependency Management: Poetry  

---

# FUTURE IMPROVEMENTS
Although the current system successfully parses and structures CaRMS program data, several improvements could further enhance the quality, maintainability, and analytical value of the platform.

## 1. Structured Parsing of Program Descriptions

Currently, program descriptions are stored as raw markdown text. A future improvement would be to parse these descriptions into structured attributes such as:

- Accreditation status
- Approximate quota
- Application requirements
- Program director information
- Contact details
- Program duration

This would allow the platform to support more precise search filters and analytics, rather than relying only on full-text search.
to enable intelligent exploration of residency program data.

## 2.Improved Language Normalization

Although French disciplines and streams are currently mapped to English, additional improvements could include:
- bilingual discipline and stream tables
- improved normalization of French program descriptions
- automatic detection of language for description sections

## 3. Search and Question-Answering Improvements
The platform currently supports RAG-based question answering using embeddings. Future work could improve this by:
- hybrid search (vector + SQL filtering)
- improved prompt engineering for program comparison questions
- evaluation metrics for LLM answer accuracy

## 4. Improved Stream and Site Detection

The parsing logic currently handles many edge cases, but future improvements could include:
-probabilistic parsing validation
- anomaly detection for unusual site or stream patterns
- validation rules for program-site relationships

## 5. Dagster automation
Currently the data pipeline runs manually. Future improvements could include using Dagster automation features to:
- schedule periodic scraping and ingestion of new program data
- automatically trigger downstream assets when source data changes
- run data validation checks after each pipeline execution
- generate alerts when parsing errors or unexpected schema changes occur
