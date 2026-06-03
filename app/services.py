"""Application services: the glue between the LLM provider and the database.

Routes stay thin by delegating all domain logic here. Everything is synchronous
and provider-agnostic, so the same code path runs identically with the offline
stub or a real model.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.llm import LLMProvider, ScoredAnswer
from app.models import Answer, InterviewSession, User
from app.security import hash_password, verify_password

# -- demo / sample data ------------------------------------------------------
# Shared by `scripts/seed.py` (CLI) and the one-click "/demo" route so a visitor
# sees the full flow instantly, offline, with no API key.
DEMO_EMAIL = "demo@interviewcoach.dev"
DEMO_PASSWORD = "demopass123"

SAMPLE_JD = """Senior Backend Engineer (Python / Distributed Systems)

We're hiring a senior backend engineer to design and operate the APIs and data
pipelines behind our product. You'll own services end to end: system design,
implementation in Python, the database schema, performance, and on-call.

Responsibilities:
- Design scalable APIs and distributed systems with clear trade-offs.
- Model data and tune the database for production load.
- Drive testing, reliability, and observability for services you own.
- Collaborate with product and communicate decisions to stakeholders.

Requirements:
- Strong Python and API design experience.
- Solid grounding in databases and system design.
- A track record of measurable impact and ownership.
"""

# A strong, quantified answer used to pre-score the first question so the demo
# dashboard opens with a real rubric breakdown to look at. Also offered in the
# UI as a one-click "use a sample answer" so visitors can try scoring instantly.
SAMPLE_ANSWER = (
    "At my last company I owned the checkout API end to end. I redesigned it "
    "around idempotent endpoints and a durable queue, which cut failed payments "
    "by 38% and reduced p99 latency from 1.2s to 340ms. I led the rollout across "
    "three teams with zero downtime and added dashboards so we caught regressions "
    "before customers did."
)


def ensure_demo_user(db: Session, provider: LLMProvider) -> User:
    """Return the demo user, creating it (with a seeded scored session) if needed.

    Idempotent: safe to call on every visit to the one-click demo. The demo user
    always has at least one session whose first answer is already scored.
    """
    user = get_user_by_email(db, DEMO_EMAIL)
    if user is None:
        user = create_user(db, DEMO_EMAIL, DEMO_PASSWORD)
    if not list_sessions(db, user):
        session = create_session(db, user, SAMPLE_JD, provider, question_count=5)
        if session.answers:
            score_and_save_answer(db, session.answers[0], SAMPLE_ANSWER, provider)
    return user


# -- users -------------------------------------------------------------------

def create_user(db: Session, email: str, password: str) -> User:
    user = User(email=email.strip().lower(), password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.strip().lower()).first()


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(db, email)
    if user and verify_password(password, user.password_hash):
        return user
    return None


# -- interview sessions ------------------------------------------------------

def _derive_role_title(job_description: str) -> str:
    """Best-effort role title from the first meaningful line of the JD."""
    for line in job_description.splitlines():
        line = line.strip(" #-*\t")
        if len(line) >= 3:
            return line[:120]
    return "Interview practice"


def create_session(
    db: Session,
    user: User,
    job_description: str,
    provider: LLMProvider,
    question_count: int = 5,
    role_title: Optional[str] = None,
) -> InterviewSession:
    """Create a session and pre-generate its questions via the provider."""
    job_description = job_description.strip()
    session = InterviewSession(
        user_id=user.id,
        job_description=job_description,
        role_title=(role_title or _derive_role_title(job_description)),
    )
    db.add(session)
    db.flush()  # assign session.id before adding answers

    for position, q in enumerate(provider.generate_questions(job_description, question_count)):
        db.add(
            Answer(
                session_id=session.id,
                position=position,
                skill=q.skill,
                question=q.text,
            )
        )

    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, user: User, session_id: int) -> Optional[InterviewSession]:
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.id == session_id, InterviewSession.user_id == user.id)
        .first()
    )


def list_sessions(db: Session, user: User) -> List[InterviewSession]:
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user.id)
        .order_by(InterviewSession.created_at.desc())
        .all()
    )


def dashboard_stats(sessions: List[InterviewSession]) -> dict:
    """Portfolio-level aggregates for the history dashboard header."""
    total_sessions = len(sessions)
    total_questions = sum(len(s.answers) for s in sessions)
    total_answered = sum(s.answered_count for s in sessions)
    scored_percents = [
        a.percent
        for s in sessions
        for a in s.answers
        if a.percent is not None
    ]
    avg_percent = (
        int(round(sum(scored_percents) / len(scored_percents)))
        if scored_percents
        else None
    )
    best_percent = max(scored_percents) if scored_percents else None
    return {
        "total_sessions": total_sessions,
        "total_questions": total_questions,
        "total_answered": total_answered,
        "avg_percent": avg_percent,
        "best_percent": best_percent,
    }


def get_answer(db: Session, user: User, answer_id: int) -> Optional[Answer]:
    return (
        db.query(Answer)
        .join(InterviewSession)
        .filter(Answer.id == answer_id, InterviewSession.user_id == user.id)
        .first()
    )


def score_and_save_answer(
    db: Session,
    answer: Answer,
    answer_text: str,
    provider: LLMProvider,
) -> ScoredAnswer:
    """Grade an answer with the provider and persist the full result."""
    result = provider.score_answer(
        job_description=answer.session.job_description,
        question=answer.question,
        answer=answer_text,
    )

    answer.answer_text = answer_text.strip()
    answer.overall = result.overall
    answer.percent = result.percent
    answer.band = result.band
    answer.summary = result.summary
    answer.axis_json = json.dumps(
        [{"axis_id": a.axis_id, "score": a.score, "reason": a.reason} for a in result.axis_scores]
    )
    answer.strengths_json = json.dumps(result.strengths)
    answer.improvements_json = json.dumps(result.improvements)
    answer.scored_at = dt.datetime.now(dt.timezone.utc)

    db.commit()
    db.refresh(answer)
    return result


def decode_axes(answer: Answer) -> List[dict]:
    if not answer.axis_json:
        return []
    try:
        return json.loads(answer.axis_json)
    except json.JSONDecodeError:
        return []


def decode_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
