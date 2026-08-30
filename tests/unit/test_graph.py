from __future__ import annotations

import pytest

from registry_pr_review_demo.graph import ReviewAgent
from registry_pr_review_demo.models import (
    KnowledgeDocument,
    ReviewDecision,
    ReviewRequest,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillPackage,
)


class StubRegistry:
    def __init__(self, package: SkillPackage) -> None:
        self.package = package
        self.requested: list[SkillArtifactRef] = []

    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage:
        self.requested.append(reference)
        return self.package


class StubKnowledge:
    def __init__(self, documents: tuple[KnowledgeDocument, ...]) -> None:
        self.documents = documents
        self.requested: list[tuple[str, ...]] = []

    def load_documents(self, document_ids: tuple[str, ...]) -> tuple[KnowledgeDocument, ...]:
        self.requested.append(document_ids)
        return tuple(document for document in self.documents if document.id in document_ids)


def demo_skill() -> SkillPackage:
    return SkillPackage(
        id="skill_demo",
        version=3,
        name="secure-pr-review",
        rules=(
            ReviewRule(
                id="no-dynamic-eval",
                pattern=r"\beval\s*\(",
                severity=Severity.HIGH,
                message="Do not execute dynamically supplied code.",
                knowledge_ids=("secure-coding",),
            ),
            ReviewRule(
                id="parameterize-sql",
                pattern=r"f[\"']SELECT\b",
                severity=Severity.HIGH,
                message="Use a parameterized query instead of interpolating SQL.",
                knowledge_ids=("data-access",),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("diff", "expected_rules", "expected_lines"),
    [
        (
            '+result = eval(user_input)\n+query = f"SELECT * FROM users WHERE id={user_id}"',
            ("no-dynamic-eval", "parameterize-sql"),
            (1, 2),
        ),
        ("+return repository.find_by_id(user_id)", (), ()),
    ],
    ids=["blocking_findings", "clean_change"],
)
def test_langgraph_review_is_deterministic_and_traceable(
    diff: str,
    expected_rules: tuple[str, ...],
    expected_lines: tuple[int, ...],
) -> None:
    registry = StubRegistry(demo_skill())
    knowledge = StubKnowledge(
        (
            KnowledgeDocument("secure-coding", "knowledge/secure-coding.md", "Never use eval."),
            KnowledgeDocument("data-access", "knowledge/data-access.md", "Bind SQL values."),
        )
    )
    agent = ReviewAgent(registry=registry, knowledge=knowledge)
    request = ReviewRequest(
        repository="example/platform-api",
        pull_request_number=42,
        head_sha="a" * 40,
        diff=diff,
    )

    result = agent.review(request, SkillArtifactRef(id="skill_demo", version=3))

    assert tuple(finding.rule_id for finding in result.findings) == expected_rules
    assert tuple(finding.line for finding in result.findings) == expected_lines
    assert result.decision is (
        ReviewDecision.CHANGES_REQUESTED if expected_rules else ReviewDecision.APPROVE
    )
    assert result.provenance.skill_id == "skill_demo"
    assert result.provenance.skill_version == 3
    assert result.provenance.document_paths == (
        ("knowledge/secure-coding.md", "knowledge/data-access.md") if expected_rules else ()
    )
    assert result.steps == ("load_skill", "load_knowledge", "inspect_diff", "decide")
    assert registry.requested == [SkillArtifactRef(id="skill_demo", version=3)]


def test_review_rejects_a_skill_version_mismatch() -> None:
    registry = StubRegistry(demo_skill())
    agent = ReviewAgent(registry=registry, knowledge=StubKnowledge(()))
    request = ReviewRequest("example/repo", 1, "b" * 40, "+safe = True")

    with pytest.raises(ValueError, match="version"):
        agent.review(request, SkillArtifactRef(id="skill_demo", version=2))
