from __future__ import annotations

from collections.abc import Mapping

from registry_pr_review_demo.controller import ReviewController
from registry_pr_review_demo.models import (
    KnowledgeDocument,
    ReviewRequest,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillPackage,
)


class StubRegistry:
    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage:
        return SkillPackage(
            id=reference.id,
            version=reference.version,
            name="secure-pr-review",
            rules=(
                ReviewRule(
                    id="no-eval",
                    pattern="eval",
                    severity=Severity.HIGH,
                    message="No eval.",
                    knowledge_ids=("secure",),
                ),
            ),
        )


class StubKnowledge:
    def load_documents(self, document_ids: tuple[str, ...]) -> tuple[KnowledgeDocument, ...]:
        assert document_ids == ("secure",)
        return (KnowledgeDocument("secure", "knowledge/secure.md", "No eval."),)


class StubRuntime:
    def __init__(self) -> None:
        self.payload: Mapping[str, object] | None = None

    def run(self, payload: Mapping[str, object]) -> dict[str, object]:
        self.payload = payload
        return {
            "decision": "changes_requested",
            "findings": [{"rule_id": "no-eval", "severity": "high", "line": 1}],
            "provenance": {
                "skill_id": "skill_demo",
                "skill_version": 1,
                "document_paths": ["knowledge/secure.md"],
            },
            "steps": ["load_context", "inspect_diff", "decide"],
        }


class StubTraceRecorder:
    def __init__(self) -> None:
        self.recorded: list[tuple[ReviewRequest, SkillPackage, dict[str, object]]] = []

    def record(
        self,
        request: ReviewRequest,
        skill: SkillPackage,
        result: dict[str, object],
    ) -> None:
        self.recorded.append((request, skill, result))


def test_controller_resolves_registry_context_before_entering_daytona() -> None:
    runtime = StubRuntime()
    traces = StubTraceRecorder()
    controller = ReviewController(
        registry=StubRegistry(),
        knowledge=StubKnowledge(),
        runtime=runtime,
        traces=traces,
    )
    request = ReviewRequest("example/repo", 1, "a" * 40, "+eval(user_input)")
    reference = SkillArtifactRef("skill_demo", 1)

    result = controller.run(request, reference)

    assert result["decision"] == "changes_requested"
    assert runtime.payload is not None
    assert runtime.payload["request"] == {
        "repository": "example/repo",
        "pull_request_number": 1,
        "head_sha": "a" * 40,
        "diff": "+eval(user_input)",
    }
    assert runtime.payload["skill"] == {
        "id": "skill_demo",
        "version": 1,
        "name": "secure-pr-review",
        "rules": [
            {
                "id": "no-eval",
                "pattern": "eval",
                "severity": "high",
                "message": "No eval.",
                "knowledge_ids": ["secure"],
            }
        ],
    }
    assert traces.recorded[0][0] == request
    assert traces.recorded[0][1].id == reference.id
    assert traces.recorded[0][1].version == reference.version
    assert traces.recorded[0][2] == result
