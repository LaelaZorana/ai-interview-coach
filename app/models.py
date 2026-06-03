"""ORM models: users, interview sessions, and graded answers."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="InterviewSession.created_at.desc()"
    )


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), default="Interview practice")
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Answer.position"
    )

    @property
    def average_percent(self) -> int | None:
        scored = [a.percent for a in self.answers if a.percent is not None]
        if not scored:
            return None
        return int(round(sum(scored) / len(scored)))

    @property
    def answered_count(self) -> int:
        return sum(1 for a in self.answers if a.percent is not None)


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    skill: Mapped[str] = mapped_column(String(120), default="general")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, default="")

    # Scoring results (null until the answer is submitted).
    overall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    band: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON-encoded per-axis detail and strengths/improvements lists.
    axis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strengths_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    improvements_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scored_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

    session: Mapped["InterviewSession"] = relationship(back_populates="answers")
