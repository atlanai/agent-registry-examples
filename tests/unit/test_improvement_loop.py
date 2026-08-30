from __future__ import annotations

from registry_pr_review_demo.graph import ReviewAgent
from registry_pr_review_demo.models import (
    EvaluationCase,
    KnowledgeDocument,
    ReviewDecision,
    ReviewRequest,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillPackage,
)
from registry_pr_review_demo.trace_analysis import analyze_trace_gap, apply_approved_proposal


class Registry:
    def __init__(self, package: SkillPackage) -> None:
        self.package = package

    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage:
        assert reference.id == self.package.id
        return self.package


class Knowledge:
    def load_documents(self, document_ids: tuple[str, ...]) -> tuple[KnowledgeDocument, ...]:
        assert document_ids == ()
        return ()


def test_v1_false_negative_becomes_v2_blocking_after_approved_patch() -> None:
    rule = ReviewRule(
        id="parameterize-sql",
        pattern=r"f[\"']SELECT\b",
        severity=Severity.HIGH,
        message="Use parameterized SQL.",
    )
    v1 = SkillPackage("skill_demo", 1, "secure-pr-review", (rule,))
    request = ReviewRequest(
        "example/data-service",
        17,
        "a" * 40,
        '+query = "SELECT * FROM events WHERE workspace_id = {}".format(workspace_id)',
    )
    evaluation = EvaluationCase(
        id="sql-format-interpolation",
        expected_decision=ReviewDecision.CHANGES_REQUESTED,
        diff=request.diff,
    )
    v1_result = ReviewAgent(registry=Registry(v1), knowledge=Knowledge()).review(
        request, SkillArtifactRef("skill_demo", 1)
    )
    proposal = analyze_trace_gap(
        trace={
            "trace_id": "a" * 32,
            "attributes": {"review.decision": v1_result.decision.value},
        },
        evaluation=evaluation,
        rules=v1.rules,
    )

    assert v1_result.decision is ReviewDecision.APPROVE
    proposal = proposal.with_approval()
    v2 = apply_approved_proposal(v1, proposal, version=2)
    v2_result = ReviewAgent(registry=Registry(v2), knowledge=Knowledge()).review(
        request, SkillArtifactRef("skill_demo", 2)
    )
    assert v2_result.decision is ReviewDecision.CHANGES_REQUESTED
