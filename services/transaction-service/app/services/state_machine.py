"""Transaction state machine (SCRUM-67, CLAUDE.md §7).

The single source of truth for which stage transitions are legal. Enforced
server-side: a PATCH that violates this returns 422. Pure + dependency-free so
every valid AND invalid transition is exhaustively unit-tested.

Human-approved transition table (CLAUDE.md §11 — state machine transitions):
  offer_accepted       → inspection_scheduled, cancelled, disputed
  inspection_scheduled → inspection_completed, cancelled, disputed
  inspection_completed → loan_applied, payment_held, cancelled, disputed
  loan_applied         → loan_approved, loan_rejected, cancelled, disputed
  loan_approved        → payment_held, cancelled, disputed
  loan_rejected        → payment_held, cancelled          (cash after rejection)
  payment_held         → title_held, disputed
  title_held           → completed, disputed
  disputed             → resolved
  resolved             → completed, cancelled
  completed / cancelled → (terminal)
"""

from __future__ import annotations

# Every stage the transactions.stage column allows (migration 0001).
STAGES: tuple[str, ...] = (
    "offer_accepted",
    "inspection_scheduled",
    "inspection_completed",
    "loan_applied",
    "loan_approved",
    "loan_rejected",
    "payment_held",
    "title_held",
    "completed",
    "cancelled",
    "disputed",
    "resolved",
)

_TRANSITIONS: dict[str, frozenset[str]] = {
    "offer_accepted": frozenset({"inspection_scheduled", "cancelled", "disputed"}),
    "inspection_scheduled": frozenset({"inspection_completed", "cancelled", "disputed"}),
    "inspection_completed": frozenset({"loan_applied", "payment_held", "cancelled", "disputed"}),
    "loan_applied": frozenset({"loan_approved", "loan_rejected", "cancelled", "disputed"}),
    "loan_approved": frozenset({"payment_held", "cancelled", "disputed"}),
    "loan_rejected": frozenset({"payment_held", "cancelled"}),
    "payment_held": frozenset({"title_held", "disputed"}),
    "title_held": frozenset({"completed", "disputed"}),
    "disputed": frozenset({"resolved"}),
    "resolved": frozenset({"completed", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


def allowed_transitions(stage: str) -> frozenset[str]:
    """The stages reachable in one step from `stage` (empty if unknown/terminal)."""
    return _TRANSITIONS.get(stage, frozenset())


def can_transition(from_stage: str, to_stage: str) -> bool:
    """True iff from_stage → to_stage is a legal single transition."""
    return to_stage in allowed_transitions(from_stage)


def is_terminal(stage: str) -> bool:
    """True iff no transition leaves `stage` (completed, cancelled)."""
    return len(allowed_transitions(stage)) == 0 and stage in _TRANSITIONS
