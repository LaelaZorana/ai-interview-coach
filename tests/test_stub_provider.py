"""Tests for the deterministic offline stub provider."""
from __future__ import annotations

from app.llm.stub import StubProvider
from app.rubric import AXIS_IDS, SCORE_MAX, SCORE_MIN

JD = (
    "Senior Backend Engineer. Design scalable APIs and distributed systems in "
    "Python. Own the database, testing, and stakeholder communication."
)

STRONG_ANSWER = (
    "I owned the payments API end to end. I redesigned it around idempotent "
    "endpoints and a queue, which reduced failed transactions by 38% and cut p99 "
    "latency from 1200ms to 340ms. I led the migration across three teams, added "
    "dashboards, and we shipped it with zero downtime."
)
WEAK_ANSWER = "I did some stuff with APIs and things. It was kinda good."


def test_questions_are_deterministic():
    p = StubProvider()
    a = p.generate_questions(JD, 5)
    b = p.generate_questions(JD, 5)
    assert [q.text for q in a] == [q.text for q in b]


def test_questions_are_role_specific():
    p = StubProvider()
    qs = p.generate_questions(JD, 6)
    skills = {q.skill for q in qs}
    # The JD mentions these explicitly; they should surface as targeted questions.
    assert {"api", "python", "database"} & skills


def test_question_count_is_respected_and_clamped():
    p = StubProvider()
    assert len(p.generate_questions(JD, 3)) == 3
    assert len(p.generate_questions(JD, 50)) == 10  # upper clamp
    assert len(p.generate_questions(JD, 0)) == 1  # lower clamp


def test_questions_always_filled_even_for_empty_jd():
    p = StubProvider()
    qs = p.generate_questions("", 5)
    assert len(qs) == 5
    assert all(q.text for q in qs)


def test_scores_are_within_range_and_complete():
    p = StubProvider()
    result = p.score_answer(JD, "Tell me about an API you owned.", STRONG_ANSWER)
    returned_axes = {a.axis_id for a in result.axis_scores}
    assert returned_axes == set(AXIS_IDS)
    for axis in result.axis_scores:
        assert SCORE_MIN <= axis.score <= SCORE_MAX
        assert axis.reason
    assert SCORE_MIN <= result.overall <= SCORE_MAX
    assert 0 <= result.percent <= 100


def test_strong_answer_outscores_weak_answer():
    p = StubProvider()
    q = "Tell me about an API you owned."
    strong = p.score_answer(JD, q, STRONG_ANSWER)
    weak = p.score_answer(JD, q, WEAK_ANSWER)
    assert strong.overall > weak.overall
    assert strong.percent > weak.percent


def test_scoring_is_deterministic():
    p = StubProvider()
    q = "Tell me about an API you owned."
    first = p.score_answer(JD, q, STRONG_ANSWER)
    second = p.score_answer(JD, q, STRONG_ANSWER)
    assert first.overall == second.overall
    assert first.axis_map() == second.axis_map()


def test_strong_answer_yields_feedback():
    p = StubProvider()
    result = p.score_answer(JD, "Tell me about an API you owned.", STRONG_ANSWER)
    assert result.summary
    # A quantified, owned answer should register at least one strength.
    assert result.strengths
