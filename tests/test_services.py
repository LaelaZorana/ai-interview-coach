"""Unit tests for the services layer: demo seeding and dashboard aggregates."""
from __future__ import annotations

import pytest

from app import services
from app.database import SessionLocal
from app.llm import StubProvider


@pytest.fixture()
def db(app_module):  # app_module resets the schema for isolation
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_ensure_demo_user_is_idempotent_and_seeds_a_scored_session(db):
    provider = StubProvider()

    user = services.ensure_demo_user(db, provider)
    assert user.email == services.DEMO_EMAIL

    sessions = services.list_sessions(db, user)
    assert len(sessions) == 1
    # The seeded session has a scored first answer.
    assert sessions[0].answered_count >= 1
    assert sessions[0].average_percent is not None

    # Calling again must not create a second user or a duplicate session.
    again = services.ensure_demo_user(db, provider)
    assert again.id == user.id
    assert len(services.list_sessions(db, again)) == 1


def test_dashboard_stats_empty():
    stats = services.dashboard_stats([])
    assert stats["total_sessions"] == 0
    assert stats["total_answered"] == 0
    assert stats["avg_percent"] is None
    assert stats["best_percent"] is None


def test_dashboard_stats_aggregates_scored_answers(db):
    provider = StubProvider()
    user = services.ensure_demo_user(db, provider)
    sessions = services.list_sessions(db, user)

    stats = services.dashboard_stats(sessions)
    assert stats["total_sessions"] == 1
    assert stats["total_questions"] >= stats["total_answered"] >= 1
    assert 0 <= stats["avg_percent"] <= 100
    assert stats["best_percent"] >= stats["avg_percent"]
