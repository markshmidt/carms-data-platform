from __future__ import annotations

import re
from collections import Counter
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from services.api.app.database import get_session
from services.api.app.models import Program, Discipline, ProgramChangeLog, School, ProgramStream
from sqlalchemy import or_
from sqlalchemy import cast, Date
from datetime import datetime as dt
from fastapi import HTTPException
# ── Shared keyword lists (EN + FR) ─────────────────────────────────

_CITIZENSHIP_KEYWORDS = [
    "%canadian citizen%",
    "%permanent residen%",
    "%citizenship%",
    # French
    "%citoyenneté canadienne%",
    "%résident permanent%",
    "%résidence permanente%",
]

_INTERVIEW_SECTION_KEYWORDS = [
    "%# Interview%",
    # French
    "%# Entrevue%",
    "%# Entretien%",
    "%#d'examen%",
]

_APPLICATION_STATS_KEYWORDS = [
    "%average number of applications%",
    # French
    "%nombre moyen de demandes%",
    "%nombre moyen de candidatures%",
]

_EVALUATION_CRITERIA_KEYWORDS = [
    "%interview evaluation criteria%",
    # French
    "%évaluation pour les entrevues%",
    "%critères d'évaluation%",
    "%critères de sélection%",
    
]

_INTERVIEW_OFFER_PCT_KEYWORDS = [
    "%average percentage of applicants offered interviews%",
    # French
    "%pourcentage moyen%invités en entrevue%",
    "%pourcentage moyen%offert%entrevue%",
    "%nombre moyen de demandes%"
]

router = APIRouter()


@router.get("/programs")
def get_programs(
    program_stream_id: str | None = None,
    discipline: str | None = None,
    school: str | None = None,
    stream: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
        query = select(Program)
    
        if program_stream_id:
            query = query.where(Program.program_stream_id == program_stream_id)

        if discipline:
            query = query.join(Discipline).where(Discipline.name.ilike(f"%{discipline}%"))

        if school:
            query = query.join(School).where(School.name.ilike(f"%{school}%"))

        if stream:
            query = query.join(ProgramStream).where(ProgramStream.name.ilike(f"%{stream}%"))

        results = session.exec(query.limit(limit)).all()

        # Exclude embedding (numpy array) from JSON response
        return [
            r.model_dump(exclude={"embedding", "description_hash"}) for r in results
        ]


@router.get("/analytics/summary")
def summary(session: Session = Depends(get_session)):
    """High-level counts for the whole dataset."""
    total = session.exec(select(func.count(Program.program_stream_id))).one()
    with_desc = session.exec(
        select(func.count(Program.program_stream_id))
        .where(Program.description.isnot(None))
    ).one()
    disciplines = session.exec(select(func.count(Discipline.id))).one()
    schools = session.exec(select(func.count(School.id))).one()
    streams = session.exec(select(func.count(ProgramStream.id))).one()
    french_programs = session.exec(select(func.count(Program.program_stream_id)).where(Program.description.ilike("%Langue de candidature%"))).one()
    english_programs = session.exec(select(func.count(Program.program_stream_id)).where(Program.description.ilike("%Program application language%"))).one()
    return {
        "total_programs": total,
        "with_description": with_desc,
        "disciplines": disciplines,
        "schools": schools,
        "streams": streams,
        "french_programs": french_programs,
        "english_programs": english_programs,
    }


@router.get("/analytics/discipline-count")
def discipline_counts(session: Session = Depends(get_session)):
    result = session.exec(
        select(
            Discipline.name,
            func.count(Program.program_stream_id)
        )
        .join(Program)
        .group_by(Discipline.name)
    ).all()

    return [{"discipline": name, "count": count} for name, count in result]


@router.get("/analytics/school-count")
def school_counts(session: Session = Depends(get_session)):
    result = session.exec(
        select(
            School.name,
            func.count(Program.program_stream_id)
        )
        .join(Program)
        .group_by(School.name)
    ).all()
    return [{"school": name, "count": count} for name, count in result]


@router.get("/analytics/stream-count")
def stream_counts(session: Session = Depends(get_session)):
    result = session.exec(
        select(
            ProgramStream.name,
            func.count(Program.program_stream_id)
        )
        .join(Program)
        .group_by(ProgramStream.name)
    ).all()
    return [{"stream": name, "count": count} for name, count in result]


@router.get("/analytics/citizenship-mentions")
def citizenship_mentions(session: Session = Depends(get_session)):
    """Programs whose description mentions Canadian citizenship / permanent residency."""
    
    filters = or_(*[Program.description.ilike(kw) for kw in _CITIZENSHIP_KEYWORDS])

    programs = session.exec(
        select(
            Program.program_stream_id,
            Program.name,
            Program.site,
            Discipline.name.label("discipline"),
            School.name.label("school"),
        )
        .join(Discipline)
        .join(School)
        .where(Program.description.isnot(None))
        .where(filters)
    ).all()

    return {
        "total": len(programs),
        "programs": [
            {
                "program_stream_id": pid,
                "name": name,
                "site": site,
                "discipline": discipline,
                "school": school,
            }
            for pid, name, site, discipline, school in programs
        ],
    }

# ── Interview helpers ───────────────────────────────────────────────

# French to English mapping for interview evaluation criteria
_FR_TO_EN_CRITERIA: dict[str, str] = {
    "Activités savantes":          "Scholarly activities",
    "Collégialité":                "Collegiality",
    "Compétences en collaboration":"Collaboration skills",
    "Compétences en communication":"Communication skills",
    "Compétences en leadership":   "Leadership skills",
    "Intérêt envers la discipline":"Interest in the discipline",
    "Intérêt envers le programme": "Interest in the program",
    "Professionnalisme":           "Professionalism",
    "Promotion de la santé":       "Health advocacy",
    "Autres composants d'entrevue":"Other interview component(s)",
}

# Standard criteria (canonical English names, used for charts)
_STANDARD_CRITERIA = [
    "Collaboration skills",
    "Collegiality",
    "Communication skills",
    "Health advocacy",
    "Interest in the discipline",
    "Interest in the program",
    "Leadership skills",
    "Professionalism",
    "Scholarly activities",
]

# Canonical application-count buckets (order matters for charts)
_APP_COUNT_ORDER = ["0 - 50", "51 - 200", "201 - 400", "401 - 600", "601 +"]

# Canonical interview-offer-percentage buckets
_PCT_ORDER = ["0 - 25 %", "26 - 50 %", "51 - 75 %", "76 - 100 %"]

def _parse_interview_criteria(description: str) -> list[dict]:
    """Return list of {criterion, evaluated} dicts from the criteria table.

    Handles both English and French table formats and normalises French
    criterion names to their English equivalents via ``_FR_TO_EN_CRITERIA``.
    """
    results: list[dict] = []
    match = re.search(
        r"Interview evaluation criteria\s*:\s*\n(.*?)(?:\n\n|\n#|\n\*\*|\Z)",
        description, re.DOTALL,
    )
    if not match:
        match = re.search(
            r"[éÉe]valuation pour les entrevues\s*:\s*\n(.*?)(?:\n\n|\n#|\n\*\*|\Z)",
            description, re.DOTALL,
        )
    if not match:
        return results

    skip = {"Interview components", "Composants d'entrevue"}

    for line in match.group(1).split("\n"):
        line = line.strip()
        if "|" not in line or line.startswith("---"):
            continue
        parts = line.split("|", 1)
        criterion = parts[0].strip()
        detail = parts[1].strip() if len(parts) > 1 else ""
        if not criterion or criterion in skip:
            continue

        # Normalise French → English
        criterion = _FR_TO_EN_CRITERIA.get(criterion, criterion)

        if criterion not in _STANDARD_CRITERIA:
            continue

        not_evaluated = any( # If any of the keywords are in the detail, the criterion is not evaluated
            kw in detail.lower() 
            for kw in [
                "do not evaluate", "not formally", "not evaluated", "n/a", "do not offer" 
                # French equivalents
                "nous n'évaluons pas", "non évalué", "s/o",
            ]
        )
        results.append({"criterion": criterion, "evaluated": not not_evaluated})
    return results


def _parse_interview_dates(description: str) -> list[str]:
    """Extract interview dates (e.g. 'January 23, 2025') from the Interviews section."""
    # Try English then French section headers
    m = re.search(r"# (?:Interviews|Entrevues|Entretiens)\s*\nDates?\s*:\s*\n(.*?)(?:Details|Détails|$)", description, re.DOTALL)
    if not m:
        return []
    return re.findall(r"(\w+ \d+, \d{4})", m.group(1))


def _normalise_pct(raw: str) -> str:
    """Normalise dash variants so '26–50 %' becomes '26 - 50 %'."""
    return re.sub(r"\s*[–—-]\s*", " - ", raw).strip()


# ── Interview endpoints ─────────────────────────────────────────────


@router.get("/analytics/interview-dates")
def interview_dates(session: Session = Depends(get_session)):
    """Number of programs interviewing on each date."""
    interview_filter = or_(*[Program.description.ilike(kw) for kw in _INTERVIEW_SECTION_KEYWORDS])
    programs = session.exec(
        select(Program).where(interview_filter)
    ).all()

    counter: Counter[str] = Counter()
    for p in programs:
        seen: set[str] = set() # To avoid counting the same date multiple times
        for d in _parse_interview_dates(p.description or ""):
            if d not in seen:
                seen.add(d)
                counter[d] += 1

    def _sort_key(item: tuple[str, int]) -> dt:
        try:
            return dt.strptime(item[0], "%B %d, %Y") # datetime obj
        except ValueError:
            return dt.max

    return [
        {"date": date, "programs": cnt}
        for date, cnt in sorted(counter.items(), key=_sort_key) # Sort by date
    ]


@router.get("/analytics/applications-received")
def applications_received(session: Session = Depends(get_session)):
    """Distribution of 'Average number of applications received' ranges."""
    app_filter = or_(*[Program.description.ilike(kw) for kw in _APPLICATION_STATS_KEYWORDS])
    programs = session.exec(
        select(Program).where(app_filter)
    ).all()

    counter: Counter[str] = Counter()
    for p in programs:
        m = re.search(
            r"Average number of applications received by our program in the last five years\s*:\s*(.+?)(?:\n|$)",
            p.description or "",
        )
        if not m:
           m = re.search(
               r"Nombre moyen de demandes soumises au programme pendant les cinq dernières années\s*:\s*(.+?)(?:\n|$)",
               p.description or "",
           )
        if m:
            raw = m.group(1).strip().rstrip("  ")
            # Map to canonical bucket
            for bucket in _APP_COUNT_ORDER:
                if bucket in raw:
                    counter[bucket] += 1
                    break
            else:
                counter[raw] += 1  # keep as-is if no match

    # Return in canonical order
    return [
        {"range": bucket, "count": counter.get(bucket, 0)}
        for bucket in _APP_COUNT_ORDER
        if counter.get(bucket, 0) > 0
    ]


@router.get("/analytics/applications-received-by-discipline")
def applications_received_by_discipline(session: Session = Depends(get_session)):
    """Application-count ranges broken down by discipline."""
    app_filter = or_(*[Program.description.ilike(kw) for kw in _APPLICATION_STATS_KEYWORDS])
    programs = session.exec(
        select(Program, Discipline.name.label("discipline_name"))
        .join(Discipline)
        .where(app_filter)
    ).all()

    data: dict[str, Counter[str]] = {}
    for prog, disc_name in programs:
        m = re.search(
            r"Average number of applications received by our program in the last five years\s*:\s*(.+?)(?:\n|$)",
            prog.description or "",
        )
        if not m:
            m = re.search(
                r"Nombre moyen de demandes soumises au programme pendant les cinq dernières années\s*:\s*(.+?)(?:\n|$)",
                prog.description or "",
            )
        if not m:
            continue
        raw = m.group(1).strip().rstrip("  ")
        bucket = raw
        for b in _APP_COUNT_ORDER:
            if b in raw:
                bucket = b
                break
        data.setdefault(disc_name, Counter())[bucket] += 1

    rows = []
    for disc in sorted(data):
        for bucket in _APP_COUNT_ORDER:
            cnt = data[disc].get(bucket, 0)
            if cnt:
                rows.append({"discipline": disc, "range": bucket, "count": cnt})
    return rows

@router.get("/analytics/description-coverage")
def description_coverage(session: Session = Depends(get_session)):
    """How many programs have each structured section in their description."""
    total = session.exec(
        select(func.count(Program.program_stream_id))
    ).one()
    with_desc = session.exec(
        select(func.count(Program.program_stream_id))
        .where(Program.description.isnot(None))
    ).one()
    with_interviews = session.exec(
        select(func.count(Program.program_stream_id))
        .where(or_(*[Program.description.ilike(kw) for kw in _INTERVIEW_SECTION_KEYWORDS]))
    ).one()
    with_apps = session.exec(
        select(func.count(Program.program_stream_id))
        .where(or_(*[Program.description.ilike(kw) for kw in _APPLICATION_STATS_KEYWORDS]))
    ).one()
    with_criteria = session.exec(
        select(func.count(Program.program_stream_id))
        .where(or_(*[Program.description.ilike(kw) for kw in _EVALUATION_CRITERIA_KEYWORDS]))
    ).one()
    with_citizenship = session.exec(
        select(func.count(Program.program_stream_id))
        .where(Program.description.isnot(None))
        .where(or_(*[Program.description.ilike(kw) for kw in _CITIZENSHIP_KEYWORDS]))
    ).one()
    with_embedding = session.exec(
        select(func.count(Program.program_stream_id))
        .where(Program.embedding.isnot(None))
    ).one()

    return {
        "total_programs": total,
        "sections": [
            {"field": "Has description", "count": with_desc, "pct": round(with_desc / total * 100, 1)},
            {"field": "Interview section", "count": with_interviews, "pct": round(with_interviews / total * 100, 1)},
            {"field": "Application stats", "count": with_apps, "pct": round(with_apps / total * 100, 1)},
            {"field": "Evaluation criteria", "count": with_criteria, "pct": round(with_criteria / total * 100, 1)},
            {"field": "Citizenship mention", "count": with_citizenship, "pct": round(with_citizenship / total * 100, 1)},
            {"field": "Embedding generated", "count": with_embedding, "pct": round(with_embedding / total * 100, 1)},
        ],
    }


@router.get("/analytics/missing-section")
def missing_section(
    section: str = "interview",
    session: Session = Depends(get_session),
):
    """Return program IDs that are missing a given description section.

    Query param `section` accepts:
      interview | applications | criteria | citizenship
    """
    section_filters = {
        "interview": or_(*[Program.description.ilike(kw) for kw in _INTERVIEW_SECTION_KEYWORDS]),
        "applications": or_(*[Program.description.ilike(kw) for kw in _APPLICATION_STATS_KEYWORDS]),
        "criteria": or_(*[Program.description.ilike(kw) for kw in _EVALUATION_CRITERIA_KEYWORDS]),
        "citizenship": or_(*[Program.description.ilike(kw) for kw in _CITIZENSHIP_KEYWORDS]),
    }

    if section not in section_filters:
       
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section '{section}'. Use one of: {', '.join(section_filters)}",
        )

    has_filter = section_filters[section]

    # IDs of programs that DO have the section
    sub = select(Program.program_stream_id).where(
        Program.description.isnot(None)
    ).where(has_filter)

    # Programs NOT in that set
    missing = session.exec(
        select(
            Program.program_stream_id,
            Program.name,
            Program.site,
            Discipline.name.label("discipline"),
            School.name.label("school"),
        )
        .join(Discipline)
        .join(School)
        .where(Program.program_stream_id.notin_(sub))
        .order_by(Program.program_stream_id)
    ).all()

    return {
        "section": section,
        "missing_count": len(missing),
        "programs": [
            {
                "program_stream_id": pid,
                "name": name,
                "site": site,
                "discipline": disc,
                "school": sch,
            }
            for pid, name, site, disc, sch in missing
        ],
    }


@router.get("/analytics/interview-offer-pct")
def interview_offer_pct(session: Session = Depends(get_session)):
    """Distribution of 'Average percentage of applicants offered interviews'."""
    pct_filter = or_(*[Program.description.ilike(kw) for kw in _INTERVIEW_OFFER_PCT_KEYWORDS])
    programs = session.exec(
        select(Program).where(pct_filter)
    ).all()

    counter: Counter[str] = Counter()
    for p in programs:
        m = re.search(
            r"Average percentage of applicants offered interviews\s*:\s*(.+?)(?:\n|$)",
            p.description or "",
        )
        if not m:
            m = re.search(
                r"Pourcentage moyen de candidats invités à une entrevue\s*:\s*(.+?)(?:\n|$)",
                p.description or "",
            )
        if m:
            raw = _normalise_pct(m.group(1).strip().rstrip("  "))
            for bucket in _PCT_ORDER:
                if bucket in raw:
                    counter[bucket] += 1
                    break
            else:
                counter[raw] += 1

    total = sum(counter.values())

    return {
        "total_programs": total,
        "distribution": [
            {
                "range": bucket,
                "count": counter.get(bucket, 0),
                "percentage": round(
                    counter.get(bucket, 0) / total * 100, 2
                ) if total else 0
            }
            for bucket in _PCT_ORDER
            if counter.get(bucket, 0) > 0
        ]
    }


@router.get("/analytics/interview-offer-pct-by-discipline")
def interview_offer_pct_by_discipline(session: Session = Depends(get_session)):
    """Interview-offer percentage ranges broken down by discipline."""
    pct_filter = or_(*[Program.description.ilike(kw) for kw in _INTERVIEW_OFFER_PCT_KEYWORDS])
    programs = session.exec(
        select(Program, Discipline.name.label("discipline_name"))
        .join(Discipline)
        .where(pct_filter)
    ).all()

    data: dict[str, Counter[str]] = {}
    for prog, disc_name in programs:
        m = re.search(
            r"Average percentage of applicants offered interviews\s*:\s*(.+?)(?:\n|$)",
            prog.description or "",
        )
        if not m:
            m = re.search(
                r"Pourcentage moyen de candidats invités à une entrevue\s*:\s*(.+?)(?:\n|$)",
                prog.description or "",
            )
        if not m:
            continue
        raw = _normalise_pct(m.group(1).strip().rstrip("  "))
        bucket = raw
        for b in _PCT_ORDER:
            if b in raw:
                bucket = b
                break
        data.setdefault(disc_name, Counter())[bucket] += 1

    rows = []
    for disc in sorted(data):
        for bucket in _PCT_ORDER:
            cnt = data[disc].get(bucket, 0)
            if cnt:
                rows.append({"discipline": disc, "range": bucket, "count": cnt})
    return rows


@router.get("/analytics/interview-criteria")
def interview_criteria_counts(session: Session = Depends(get_session)):
    """How many programs evaluate each standard interview criterion."""
    criteria_filter = or_(*[Program.description.ilike(kw) for kw in _EVALUATION_CRITERIA_KEYWORDS])
    programs = session.exec(
        select(Program).where(criteria_filter)
    ).all()

    evaluated_counter: Counter[str] = Counter()
    not_evaluated_counter: Counter[str] = Counter()

    for p in programs:
        for item in _parse_interview_criteria(p.description or ""):
            if item["evaluated"]:
                evaluated_counter[item["criterion"]] += 1
            else:
                not_evaluated_counter[item["criterion"]] += 1

    return [
        {
            "criterion": crit,
            "evaluated": evaluated_counter.get(crit, 0),
            "not_evaluated": not_evaluated_counter.get(crit, 0),
        }
        for crit in _STANDARD_CRITERIA
    ]


@router.get("/analytics/interview-criteria-by-discipline")
def interview_criteria_by_discipline(session: Session = Depends(get_session)):
    """Count of programs evaluating each criterion, grouped by discipline."""
    criteria_filter = or_(*[Program.description.ilike(kw) for kw in _EVALUATION_CRITERIA_KEYWORDS])
    programs = session.exec(
        select(Program, Discipline.name.label("discipline_name"))
        .join(Discipline)
        .where(criteria_filter)
    ).all()

    # {discipline: {criterion: evaluated_count}}
    data: dict[str, Counter[str]] = {}
    for prog, disc_name in programs:
        if disc_name not in data:
            data[disc_name] = Counter()
        for item in _parse_interview_criteria(prog.description or ""):
            if item["evaluated"]:
                data[disc_name][item["criterion"]] += 1

    rows = []
    for disc, counts in sorted(data.items()):
        for crit, cnt in counts.items():
            rows.append({"discipline": disc, "criterion": crit, "count": cnt})

    return rows

@router.get("/analytics/changes-over-time")
def changes_over_time(session: Session = Depends(get_session)):
    """Description changes grouped by date."""
    

    result = session.exec(
        select(
            cast(ProgramChangeLog.changed_at, Date).label("date"),
            func.count().label("changes"),
        )
        .group_by("date")
        .order_by("date")
    ).all()

    return [
        {"date": str(d), "changes": cnt}
        for d, cnt in result
    ]


@router.get("/analytics/recent-changes")
def recent_changes(session: Session = Depends(get_session)):
    """The 50 most recent description changes."""
    logs = session.exec(
        select(ProgramChangeLog)
        .order_by(ProgramChangeLog.changed_at.desc())
        .limit(50)
    ).all()

    return [
        {
            "program_stream_id": log.program_stream_id,
            "changed_at": str(log.changed_at),
            "old_hash": log.old_hash,
            "new_hash": log.new_hash,
        }
        for log in logs
    ]


@router.get("/analytics/most-changed-programs")
def most_changed_programs(session: Session = Depends(get_session)):
    """Programs with the most description changes."""
    result = session.exec(
        select(
            ProgramChangeLog.program_stream_id,
            func.count().label("changes"),
        )
        .group_by(ProgramChangeLog.program_stream_id)
        .order_by(func.count().desc())
        .limit(30)
    ).all()

    return [
        {"program_stream_id": pid, "changes": cnt}
        for pid, cnt in result
    ]