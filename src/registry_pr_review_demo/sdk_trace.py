from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

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
    skills: tuple[atlan_ai.AtlanSpan, ...]
    trace_id: str

    def complete(self, result: ReviewResult) -> None:
        matched_rules = tuple(finding.rule_id for finding in result.findings)
        self.root.otel_span.set_attribute("review.decision", result.decision.value)
        self.root.otel_span.set_attribute("review.finding_count", len(result.findings))
        if matched_rules:
            self.root.otel_span.set_attribute("review.matched_rule_ids", matched_rules)
        self.root.otel_span.set_attribute(
            "output.value",
            f"Decision: {result.decision.value}. Findings: {len(result.findings)}.",
        )
        self.root.otel_span.set_attribute("output.mime_type", "text/plain")
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
        fingerprints: Sequence[tuple[str, SkillFingerprint]],
        evaluation: EvaluationCase,
        *,
        agent_id: str,
        provider_id: str,
        environment_id: str,
        external_session_id: str,
        sandbox_id: str,
        visitor_id: str | None = None,
    ) -> Generator[SdkTraceRun, None, None]:
        if not fingerprints:
            raise ValueError("SDK review requires at least one verified skill")
        trace_id = atlan_ai.create_trace_id(seed=external_session_id)
        with (
            atlan_ai.propagate_attributes(
                session_id=external_session_id,
                tags=["registry-pr-review", "daytona"],
                trace_name=f"PR review: {evaluation.id}",
            ),
            self._client.start_as_current_span(
                "software_factory.pr_review",
                as_type="task",
                trace_context={"trace_id": trace_id},
            ) as root,
        ):
            root.otel_span.set_attribute("atlan.agent.id", agent_id)
            root.otel_span.set_attribute("atlan.agent.provider_id", provider_id)
            root.otel_span.set_attribute("atlan.agent.environment_id", environment_id)
            root.otel_span.set_attribute("agent.runtime", "langgraph")
            root.otel_span.set_attribute("daytona.sandbox.id", sandbox_id)
            root.otel_span.set_attribute("github.repository", request.repository)
            root.otel_span.set_attribute("github.pull_request.number", request.pull_request_number)
            root.otel_span.set_attribute("git.commit.sha", request.head_sha)
            root.otel_span.set_attribute("demo.eval.case_id", evaluation.id)
            root.otel_span.set_attribute(
                "demo.eval.expected_decision", evaluation.expected_decision.value
            )
            root.otel_span.set_attribute(
                "input.value",
                "Review the customer-neutral pull-request fixture with all three governed Skills.",
            )
            root.otel_span.set_attribute("input.mime_type", "text/plain")
            if visitor_id is not None:
                root.otel_span.set_attribute("atlan.visitor.id", visitor_id)
            spans: list[atlan_ai.AtlanSpan] = []
            for skill_id, fingerprint in fingerprints:
                with self._client.start_as_current_span(
                    f"execute_tool {fingerprint.name}", as_type="tool"
                ) as skill:
                    skill.otel_span.set_attribute("gen_ai.tool.name", fingerprint.name)
                    skill.otel_span.set_attribute("gen_ai.tool.type", "skill")
                    skill.otel_span.set_attribute("atlan.registry.skill.id", skill_id)
                    skill.otel_span.set_attribute("atlan.skill.id", skill_id)
                    skill.otel_span.set_attribute("atlan.skill.name", fingerprint.name)
                    skill.otel_span.set_attribute(
                        "atlan.skill.version", fingerprint.semantic_version
                    )
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
                    skill.otel_span.set_attribute("input.value", f"{fingerprint.name} fingerprint")
                    skill.otel_span.set_attribute("input.mime_type", "text/plain")
                    skill.otel_span.set_attribute("output.value", "fingerprint_verified")
                    skill.otel_span.set_attribute("output.mime_type", "text/plain")
                    if visitor_id is not None:
                        skill.otel_span.set_attribute("atlan.visitor.id", visitor_id)
                    spans.append(skill)
            yield SdkTraceRun(root=root, skills=tuple(spans), trace_id=trace_id)
