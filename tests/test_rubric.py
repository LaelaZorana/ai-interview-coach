"""Unit tests for the dependency-free scoring rubric."""
from __future__ import annotations

from app.rubric import (
    AXES,
    SCORE_MAX,
    SCORE_MIN,
    band,
    clamp_score,
    to_percent,
    weighted_overall,
)


def test_clamp_score_handles_garbage_and_range():
    assert clamp_score(3) == 3
    assert clamp_score("4") == 4
    assert clamp_score(4.6) == 5
    assert clamp_score(99) == SCORE_MAX
    assert clamp_score(-5) == SCORE_MIN
    assert clamp_score(None) == SCORE_MIN
    assert clamp_score("not a number") == SCORE_MIN


def test_weighted_overall_bounds():
    all_min = {a.id: 1 for a in AXES}
    all_max = {a.id: 5 for a in AXES}
    assert weighted_overall(all_min) == 1.0
    assert weighted_overall(all_max) == 5.0


def test_weighted_overall_respects_weights():
    # Impact is weighted highest; boosting only impact must beat boosting only structure.
    base = {a.id: 2 for a in AXES}
    high_impact = dict(base, impact=5)
    high_structure = dict(base, structure=5)
    assert weighted_overall(high_impact) > weighted_overall(high_structure)


def test_weighted_overall_missing_axis_is_floored():
    # An absent axis is treated as the minimum, never silently averaged away.
    partial = {"relevance": 5}  # everything else missing
    full_min = {a.id: 1 for a in AXES}
    full_min["relevance"] = 5
    assert weighted_overall(partial) == weighted_overall(full_min)


def test_to_percent_endpoints():
    assert to_percent(1.0) == 0
    assert to_percent(5.0) == 100
    assert 40 <= to_percent(3.0) <= 60


def test_band_thresholds():
    assert band(5.0) == "Outstanding"
    assert band(4.0) == "Strong"
    assert band(3.0) == "Solid, needs polish"
    assert band(2.0) == "Needs work"
    assert band(1.0) == "Off track"
