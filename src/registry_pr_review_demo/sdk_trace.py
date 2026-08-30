from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import cast

import atlan_ai
from atlan_ai.client import AtlanAI

from registry_pr_review_demo.models import (
    EvaluationCase,
    ReviewRequest,
    ReviewResult,
    SkillFingerprint,
)


@dataclass(slots=True)
class SdkTraceRun:
    root: atlan_ai.AtlanSpan
    skill: atlan_ai.AtlanSpan
    trace_id: str

    def complete(self, result: ReviewResult) -> None:
        matched_rules = tuple(finding.rule_id for finding in result.findings)
        self.root.otel_span.set_attribute("review.decision", result.decision.value)
        self.root.otel_span.set_attribute("review.finding_count", len(result.findings))
        if matched_rules:
            self.root.otel_span.set_attribute("review.matched_rule_ids", matched_rules)
        self.root.score_trace(
            "review_decision",
            data_type="CATEGORICAL",
            string_value=result.decision.value,
        )


class SdkReviewTracer:
    def __init__(self, client: AtlanAI) -> None:
        self._client = client

    @contextmanager
    def review(
        self,
        request: ReviewRequest,
        fingerprint: SkillFingerprint,
        evaluation: EvaluationCase,
    ) -> Generator[SdkTraceRun, None, None]:
        session_id = f"pr-{request.pull_request_number}-{request.head_sha[:12]}"
        trace_id = atlan_ai.create_trace_id(seed=session_id)
        with (
            atlan_ai.propagate_attributes(
                session_id=session_id,
                tags=["registry-pr-review", "daytona"],
                trace_name=f"PR review: {evaluation.id}",
            ),
            self._client.start_as_current_span(
                "registry.pr_review",
                as_type="task",
                trace_context={"trace_id": trace_id},
            ) as root,
        ):
            root.otel_span.set_attribute("github.repository", request.repository)
            root.otel_span.set_attribute("github.pull_request.number", request.pull_request_number)
            root.otel_span.set_attribute("git.commit.sha", request.head_sha)
            root.otel_span.set_attribute("demo.eval.case_id", evaluation.id)
            root.otel_span.set_attribute(
                "demo.eval.expected_decision", evaluation.expected_decision.value
            )
            with self._client.start_as_current_span("review.skill", as_type="tool") as skill:
                skill.otel_span.set_attribute("atlan.skill.name", fingerprint.name)
                skill.otel_span.set_attribute("atlan.skill.version", fingerprint.semantic_version)
                skill.otel_span.set_attribute(
                    "atlan.registry.skill.version_ordinal", fingerprint.registry_version
                )
                skill.otel_span.set_attribute(
                    "atlan.skill.source_digest", fingerprint.source_digest
                )
                skill.otel_span.set_attribute(
                    "atlan.skill.skillmd_sha256", fingerprint.skillmd_sha256
                )
                skill.otel_span.set_attribute("atlan.skill.fingerprint_source", "registry")
                yield SdkTraceRun(root=root, skill=skill, trace_id=trace_id)


@dataclass(slots=True)
class AgentTraceRun:
    root: atlan_ai.AtlanSpan
    trace_id: str

    def complete(self, result: Mapping[str, object], tool_names: Sequence[str]) -> None:
        decision = result.get("decision")
        findings = result.get("findings")
        if not isinstance(decision, str) or not isinstance(findings, list):
            raise ValueError("review result is missing decision or findings")
        finding_values = cast(list[object], findings)
        self.root.otel_span.set_attribute("review.decision", decision)
        self.root.otel_span.set_attribute("review.finding_count", len(finding_values))
        for tool_name in tool_names:
            self.root.otel_span.add_event("kiro.tool", {"tool.name": tool_name})
        self.root.score_trace(
            "review_decision",
            data_type="CATEGORICAL",
            string_value=decision,
        )


class AgentReviewTracer:
    """Emits one agent-authenticated root and verified child span per Registry skill."""

    def __init__(self, client: AtlanAI) -> None:
        self._client = client

    @contextmanager
    def review(
        self,
        *,
        agent_id: str,
        runtime: str,
        session_id: str,
        trace_name: str,
        skills: Sequence[tuple[str, SkillFingerprint]],
        attributes: Mapping[str, str],
    ) -> Generator[AgentTraceRun, None, None]:
        trace_id = atlan_ai.create_trace_id(seed=session_id)
        with (
            atlan_ai.propagate_attributes(
                session_id=session_id,
                tags=["software-factory", runtime],
                trace_name=trace_name,
            ),
            self._client.start_as_current_span(
                "software_factory.pr_review",
                as_type="task",
                trace_context={"trace_id": trace_id},
            ) as root,
        ):
            root.otel_span.set_attribute("atlan.agent.id", agent_id)
            root.otel_span.set_attribute("agent.runtime", runtime)
            for key, value in attributes.items():
                root.otel_span.set_attribute(key, value)
            for skill_id, fingerprint in skills:
                with self._client.start_as_current_span("review.skill", as_type="tool") as span:
                    span.otel_span.set_attribute("atlan.skill.id", skill_id)
                    span.otel_span.set_attribute("atlan.skill.name", fingerprint.name)
                    span.otel_span.set_attribute(
                        "atlan.skill.version", fingerprint.semantic_version
                    )
                    span.otel_span.set_attribute(
                        "atlan.registry.skill.version_ordinal", fingerprint.registry_version
                    )
                    span.otel_span.set_attribute(
                        "atlan.skill.source_digest", fingerprint.source_digest
                    )
                    span.otel_span.set_attribute(
                        "atlan.skill.skillmd_sha256", fingerprint.skillmd_sha256
                    )
                    span.otel_span.set_attribute("atlan.skill.fingerprint_source", "registry")
            yield AgentTraceRun(root=root, trace_id=trace_id)
