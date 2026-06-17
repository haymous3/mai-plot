"""state_machine — exhaustive valid + invalid transitions (SCRUM-67)."""

from __future__ import annotations

import pytest

from app.services.state_machine import (
    STAGES,
    allowed_transitions,
    can_transition,
    is_terminal,
)

# The approved transition table (CLAUDE.md §7, with loan_rejected non-terminal).
_VALID: dict[str, set[str]] = {
    "offer_accepted": {"inspection_scheduled", "cancelled", "disputed"},
    "inspection_scheduled": {"inspection_completed", "cancelled", "disputed"},
    "inspection_completed": {"loan_applied", "payment_held", "cancelled", "disputed"},
    "loan_applied": {"loan_approved", "loan_rejected", "cancelled", "disputed"},
    "loan_approved": {"payment_held", "cancelled", "disputed"},
    "loan_rejected": {"payment_held", "cancelled"},
    "payment_held": {"title_held", "disputed"},
    "title_held": {"completed", "disputed"},
    "disputed": {"resolved"},
    "resolved": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def test_table_covers_every_stage() -> None:
    assert set(_VALID) == set(STAGES)


@pytest.mark.parametrize("from_stage", STAGES)
def test_every_pair_matches_the_table(from_stage: str) -> None:
    """For every (from, to) over all 12×12 pairs, can_transition agrees with the
    approved table — so every valid AND invalid transition is covered."""
    for to_stage in STAGES:
        expected = to_stage in _VALID[from_stage]
        assert can_transition(from_stage, to_stage) is expected, f"{from_stage}->{to_stage}"


def test_allowed_transitions_returns_the_set() -> None:
    assert allowed_transitions("offer_accepted") == frozenset(
        {"inspection_scheduled", "cancelled", "disputed"}
    )


def test_terminal_stages() -> None:
    assert is_terminal("completed")
    assert is_terminal("cancelled")
    assert not is_terminal("offer_accepted")
    assert not is_terminal("loan_rejected")  # now non-terminal


def test_unknown_stage_has_no_transitions() -> None:
    assert allowed_transitions("bogus") == frozenset()
    assert can_transition("bogus", "completed") is False
    assert is_terminal("bogus") is False  # unknown, not a defined terminal


def test_no_self_transitions() -> None:
    for stage in STAGES:
        assert not can_transition(stage, stage)
