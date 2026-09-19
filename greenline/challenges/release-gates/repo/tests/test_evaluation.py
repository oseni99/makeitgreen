"""Extension contract for deterministic release-gate evaluation."""
from __future__ import annotations

from copy import deepcopy

import pytest

from flags.models import GateDefinition, Rule
from flags.service import GateService
from flags.store import GateStore


def evaluator_cls():
    # A missing extension must be an ordinary failed test, not collection failure.
    from evaluation.evaluator import GateEvaluator

    return GateEvaluator


def service_for(gate: GateDefinition) -> GateService:
    store = GateStore()
    store.save(gate)
    return GateService(store, evaluator=evaluator_cls()())


def evaluate(gate: GateDefinition, context: dict):
    return service_for(gate).evaluate(gate.key, gate.environment, context)


def test_emergency_disable_wins_over_every_other_match() -> None:
    gate = GateDefinition(
        "agent-mode",
        "production",
        default=True,
        disabled=True,
        allowlist=frozenset({"workspace-a"}),
        rules=(Rule("enterprise", "plan", "equals", "enterprise", True),),
        rollout_percentage=100,
    )
    result = evaluate(gate, {"workspace_id": "workspace-a", "plan": "enterprise"})
    assert result.value is False
    assert result.reason == "disabled"
    assert result.rule_id is None


def test_allowlist_precedes_a_matching_deny_rule() -> None:
    gate = GateDefinition(
        "bulk-export",
        "production",
        rules=(Rule("deny-free", "plan", "equals", "free", False),),
        allowlist=frozenset({"workspace-a"}),
    )
    result = evaluate(gate, {"workspace_id": "workspace-a", "plan": "free"})
    assert result.value is True
    assert result.reason == "allowlist"


def test_rules_use_first_match_and_support_equals_and_membership() -> None:
    gate = GateDefinition(
        "regional-routing",
        "production",
        default=False,
        rules=(
            Rule("pause-us", "region", "equals", "us", False),
            Rule("paid-plan", "plan", "in", ("team", "enterprise"), True),
            Rule("later-us", "region", "equals", "us", True),
        ),
    )
    first = evaluate(
        gate, {"workspace_id": "workspace-a", "region": "us", "plan": "enterprise"}
    )
    member = evaluate(
        gate, {"workspace_id": "workspace-b", "region": "eu", "plan": "team"}
    )
    assert (first.value, first.reason, first.rule_id) == (False, "rule", "pause-us")
    assert (member.value, member.reason, member.rule_id) == (True, "rule", "paid-plan")


def test_percentage_assignment_is_repeatable_across_evaluators() -> None:
    gate = GateDefinition("smart-summary", "production", rollout_percentage=37)
    context = {"workspace_id": "workspace-42"}
    first = evaluate(gate, context)
    second = evaluate(gate, context)
    assert first == second
    assert first.reason in {"percentage", "default"}


def test_growing_rollout_never_removes_an_existing_workspace() -> None:
    contexts = [{"workspace_id": f"workspace-{index}"} for index in range(300)]
    small = GateDefinition("new-editor", "production", rollout_percentage=20)
    large = GateDefinition("new-editor", "production", rollout_percentage=40)

    small_cohort = {ctx["workspace_id"] for ctx in contexts if evaluate(small, ctx).value}
    large_cohort = {ctx["workspace_id"] for ctx in contexts if evaluate(large, ctx).value}

    assert small_cohort
    assert small_cohort < large_cohort


def test_gate_key_salts_equal_percentage_cohorts() -> None:
    contexts = [{"workspace_id": f"workspace-{index}"} for index in range(300)]
    alpha = GateDefinition("alpha-gate", "production", rollout_percentage=30)
    beta = GateDefinition("beta-gate", "production", rollout_percentage=30)
    alpha_cohort = {ctx["workspace_id"] for ctx in contexts if evaluate(alpha, ctx).value}
    beta_cohort = {ctx["workspace_id"] for ctx in contexts if evaluate(beta, ctx).value}
    assert alpha_cohort != beta_cohort


def test_missing_targeting_key_and_no_match_return_explainable_defaults() -> None:
    rollout = GateDefinition("rollout", "production", default=False, rollout_percentage=50)
    missing = evaluate(rollout, {"plan": "team"})
    assert (missing.value, missing.reason) == (False, "missing_context")

    rules_only = GateDefinition(
        "rules", "production", default=True,
        rules=(Rule("enterprise", "plan", "equals", "enterprise", False),),
    )
    no_match = evaluate(rules_only, {"workspace_id": "workspace-a", "plan": "team"})
    assert (no_match.value, no_match.reason) == (True, "default")


def test_evaluation_does_not_mutate_definition_or_context() -> None:
    gate = GateDefinition(
        "immutable", "production", rollout_percentage=50,
        rules=(Rule("region", "region", "equals", "eu", True),),
    )
    context = {"workspace_id": "workspace-a", "region": "us", "labels": ["pilot"]}
    gate_before = deepcopy(gate)
    context_before = deepcopy(context)
    evaluate(gate, context)
    assert gate == gate_before
    assert context == context_before


def test_zero_and_full_rollout_percentages_are_exact_boundaries() -> None:
    context = {"workspace_id": "workspace-a"}
    disabled = GateDefinition("zero", "production", rollout_percentage=0)
    enabled = GateDefinition("full", "production", rollout_percentage=100)
    assert evaluate(disabled, context).value is False
    assert evaluate(enabled, context).value is True


def test_allowlist_requires_only_workspace_identity() -> None:
    gate = GateDefinition(
        "pilot", "production", allowlist=frozenset({"workspace-a"})
    )
    result = evaluate(gate, {"workspace_id": "workspace-a"})
    assert (result.value, result.reason) == (True, "allowlist")


def test_unsupported_rule_operator_is_rejected() -> None:
    gate = GateDefinition(
        "bad-rule",
        "production",
        rules=(Rule("bad", "plan", "contains", "team", True),),
    )
    with pytest.raises(ValueError, match="unsupported"):
        evaluate(gate, {"workspace_id": "workspace-a", "plan": "team"})


@pytest.mark.parametrize("expected", ["team", {"team": True}])
def test_membership_rule_rejects_string_and_mapping_collections(expected: object) -> None:
    gate = GateDefinition(
        "membership",
        "production",
        rules=(Rule("member", "plan", "in", expected, True),),
    )
    result = evaluate(gate, {"workspace_id": "workspace-a", "plan": "team"})
    assert (result.value, result.reason) == (False, "default")
