"""Versioned fail-closed semantic primitive resolver v1.1.0.

The frozen v1.0.0 implementation remains byte-for-byte unchanged.  This
module reuses its context validation helpers and changes only the priority
barrier: an ambiguous higher-priority admissible strategy blocks every
lower-priority selected strategy.  The barrier is applied both to the
single-period resolver and to the controlled cross-tag branch of the pair
resolver.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from src.data import target_candidate_v2_pit as v1


RESOLVER_ID = "semantic_primitive_resolver"
RESOLVER_VERSION = "1.1.0"

# Explicit exports used by the versioned X_t construction binding.  Any
# unchanged helper is resolved lazily through __getattr__ below.
Scope = v1.Scope
empty_selection = v1.empty_selection
parse_date = v1.parse_date
strategy_evaluations = v1.strategy_evaluations


def _blocking_ambiguities(
    evaluations: list[dict[str, Any]],
    *,
    role_priorities: dict[str, int],
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """Return ambiguous strategies that outrank the chosen role strategy."""

    blocking: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for evaluation in evaluations:
        for role, chosen_priority in role_priorities.items():
            selection = evaluation["roles"][role]
            if (
                int(evaluation["priority"]) <= int(chosen_priority)
                and selection.get("status") == "ambiguous"
            ):
                blocking.append((evaluation, role, selection))
    return blocking


def _ambiguous_priority_barrier(
    blocking: list[tuple[dict[str, Any], str, dict[str, Any]]],
) -> dict[str, Any]:
    return empty_selection(
        "ambiguous",
        "higher_priority_context_ambiguous",
        candidate_strategies=v1.semicolon(item[0]["name"] for item in blocking),
        detail_reasons=v1.semicolon(item[2].get("reason", "") for item in blocking),
        blocked_roles=v1.semicolon(item[1] for item in blocking),
        resolver_version=RESOLVER_VERSION,
    )


def select_primitive_single_period(
    primitive: str,
    policy: dict[str, Any],
    anchor: dict[str, Any],
    previous_anchor: dict[str, Any] | None,
    scope: Scope,
) -> dict[str, Any]:
    """Select one period while failing closed on higher-priority ambiguity."""

    specs = {
        "current": (
            anchor["report_end"],
            previous_anchor["report_end"] + timedelta(days=1)
            if previous_anchor
            else None,
        )
    }
    evaluations = strategy_evaluations(policy, anchor, specs, scope)
    selected = sorted(
        (
            evaluation
            for evaluation in evaluations
            if evaluation["roles"]["current"]["status"] == "selected"
        ),
        key=lambda evaluation: evaluation["priority"],
    )
    if selected:
        chosen = selected[0]
        blocking = _blocking_ambiguities(
            evaluations,
            role_priorities={"current": int(chosen["priority"])},
        )
        if blocking:
            return _ambiguous_priority_barrier(blocking)

        result = dict(chosen["roles"]["current"])
        result["strategy"] = chosen["name"]
        result["resolver_version"] = RESOLVER_VERSION
        if primitive == "revenues" and len(selected) > 1:
            tolerance = float(policy.get("material_concept_disagreement_ratio", 0.02))
            if v1.semantic_disagreement(selected, ("current",), tolerance):
                result["semantic_diagnostic"] = (
                    "lower_priority_revenue_concepts_disagree"
                )
                result["competing_strategies"] = v1.semicolon(
                    evaluation["name"]
                    for evaluation in selected
                    if evaluation is not chosen
                )
        return result

    if any(
        evaluation["roles"]["current"]["status"] == "ambiguous"
        for evaluation in evaluations
    ):
        result = empty_selection("ambiguous", "single_period_context_ambiguous")
    else:
        result = empty_selection("missing", "single_period_primitive_missing")
    result["resolver_version"] = RESOLVER_VERSION
    return result


def select_primitive_pair(
    primitive: str,
    policy: dict[str, Any],
    anchor_t1: dict[str, Any],
    anchor_t: dict[str, Any],
    anchor_tm1: dict[str, Any] | None,
    scope: Scope,
    revenue_evidence_directory: Path | None = None,
) -> dict[str, Any]:
    """Apply the v1.1 barrier to the only unguarded v1 pair branch."""

    result = v1.select_primitive_pair(
        primitive,
        policy,
        anchor_t1,
        anchor_t,
        anchor_tm1,
        scope,
        revenue_evidence_directory,
    )
    if not (
        result.get("status") == "selected"
        and result.get("reason") == "controlled_cross_tag_equivalence"
    ):
        if result.get("status") == "selected":
            result = dict(result)
            result["resolver_version"] = RESOLVER_VERSION
        return result

    period_specs = {
        "comparative_t": (
            anchor_t["report_end"],
            anchor_tm1["report_end"] + timedelta(days=1) if anchor_tm1 else None,
        ),
        "current_t1": (
            anchor_t1["report_end"],
            anchor_t["report_end"] + timedelta(days=1),
        ),
    }
    evaluations = strategy_evaluations(policy, anchor_t1, period_specs, scope)
    by_name = {evaluation["name"]: evaluation for evaluation in evaluations}
    comparative_name, current_name = str(result["strategy"]).split("->", 1)
    blocking = _blocking_ambiguities(
        evaluations,
        role_priorities={
            "comparative_t": int(by_name[comparative_name]["priority"]),
            "current_t1": int(by_name[current_name]["priority"]),
        },
    )
    if blocking:
        return _ambiguous_priority_barrier(blocking)
    result = dict(result)
    result["resolver_version"] = RESOLVER_VERSION
    return result


def __getattr__(name: str) -> Any:
    """Forward unchanged semantic helpers to the immutable v1 module."""

    return getattr(v1, name)
