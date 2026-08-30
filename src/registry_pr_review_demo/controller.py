from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from registry_pr_review_demo.models import (
    EvaluationCase,
    ReviewRequest,
    SkillArtifactRef,
    SkillPackage,
)
from registry_pr_review_demo.ports import KnowledgeSource, SkillRegistry


class SandboxRuntime(Protocol):
    def run(self, payload: Mapping[str, object]) -> dict[str, object]: ...


class TraceRecorder(Protocol):
    def record(
        self,
        request: ReviewRequest,
        skill: SkillPackage,
        result: dict[str, object],
    ) -> None: ...


class ReviewController:
    """Resolves governed context, sends only the job payload to Daytona, and records the result."""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        knowledge: KnowledgeSource,
        runtime: SandboxRuntime,
        traces: TraceRecorder,
    ) -> None:
        self._registry = registry
        self._knowledge = knowledge
        self._runtime = runtime
        self._traces = traces

    def run(
        self,
        request: ReviewRequest,
        reference: SkillArtifactRef,
        *,
        evaluation: EvaluationCase | None = None,
        trace_mode: str | None = None,
    ) -> dict[str, object]:
        skill = self._registry.load_skill(reference)
        if skill.id != reference.id or skill.version != reference.version:
            raise ValueError("Registry returned a different skill id or version")
        document_ids = tuple(
            dict.fromkeys(document_id for rule in skill.rules for document_id in rule.knowledge_ids)
        )
        documents = self._knowledge.load_documents(document_ids)
        skill_payload: dict[str, object] = {
            "id": skill.id,
            "version": skill.version,
            "name": skill.name,
            "rules": [
                {
                    "id": rule.id,
                    "pattern": rule.pattern,
                    "severity": rule.severity.value,
                    "message": rule.message,
                    "knowledge_ids": list(rule.knowledge_ids),
                }
                for rule in skill.rules
            ],
        }
        for key, value in (
            ("semantic_version", reference.semantic_version),
            ("source_digest", reference.source_digest),
            ("skillmd_sha256", reference.skillmd_sha256),
        ):
            if value is not None:
                skill_payload[key] = value
        payload: dict[str, object] = {
            "request": {
                "repository": request.repository,
                "pull_request_number": request.pull_request_number,
                "head_sha": request.head_sha,
                "diff": request.diff,
            },
            "skill": skill_payload,
            "documents": [
                {"id": document.id, "path": document.path, "content": document.content}
                for document in documents
            ],
        }
        if evaluation is not None:
            payload["evaluation"] = {
                "id": evaluation.id,
                "expected_decision": evaluation.expected_decision.value,
            }
        if trace_mode is not None:
            payload["trace_mode"] = trace_mode
        result = self._runtime.run(payload)
        self._traces.record(request, skill, result)
        return result
