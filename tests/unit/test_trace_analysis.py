from __future__ import annotations

from registry_pr_review_demo.models import EvaluationCase, ReviewDecision, ReviewRule, Severity
from registry_pr_review_demo.trace_analysis import analyze_trace_gap


def test_analyzer_proposes_broader_sql_rule_from_a_real_false_negative() -> None:
    evaluation = EvaluationCase(
        id="sql-format-interpolation",
        expected_decision=ReviewDecision.CHANGES_REQUESTED,
        diff='+query = "SELECT * FROM events WHERE workspace_id = {}".format(workspace_id)',
    )
    rules = (
        ReviewRule(
            id="parameterize-sql",
            pattern=r"f[\"']SELECT\b",
            severity=Severity.HIGH,
            message="Use parameterized SQL.",
            knowledge_ids=("data-access",),
        ),
    )
    trace = {
        "trace_id": "a" * 32,
        "attributes": {
            "demo.eval.case_id": "sql-format-interpolation",
            "demo.eval.expected_decision": "changes_requested",
            "review.decision": "approve",
            "review.finding_count": 0,
        },
    }

    proposal = analyze_trace_gap(trace=trace, evaluation=evaluation, rules=rules)

    assert proposal.kind == "false_negative"
    assert proposal.trace_id == "a" * 32
    assert proposal.rule_id == "parameterize-sql"
    assert proposal.before_pattern == r"f[\"']SELECT\b"
    assert proposal.after_pattern is not None
    assert ".format" in proposal.after_pattern
    assert proposal.approved is False


def test_analyzer_returns_no_change_when_trace_matches_expectation() -> None:
    evaluation = EvaluationCase(
        id="safe-query",
        expected_decision=ReviewDecision.APPROVE,
        diff="+user = repository.find_by_id(user_id)",
    )
    trace = {
        "trace_id": "b" * 32,
        "attributes": {
            "demo.eval.case_id": "safe-query",
            "review.decision": "approve",
            "review.finding_count": 0,
        },
    }

    proposal = analyze_trace_gap(trace=trace, evaluation=evaluation, rules=())

    assert proposal.kind == "no_change"
    assert proposal.rule_id is None
