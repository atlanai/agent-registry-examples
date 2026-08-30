from __future__ import annotations

import atlan_ai
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from registry_pr_review_demo.models import (
    EvaluationCase,
    ReviewDecision,
    ReviewProvenance,
    ReviewRequest,
    ReviewResult,
    SkillFingerprint,
)
from registry_pr_review_demo.sdk_trace import SdkReviewTracer


def test_sdk_trace_records_exact_skill_usage_without_raw_diff() -> None:
    exporter = InMemorySpanExporter()
    client = atlan_ai.init(
        service_name="registry-pr-review-sdk",
        api_key="sdk-test-key",
        base_url="https://agentgateway.example.com",
        workspace_id="workspace_data",
        trace_content=False,
        span_exporter=exporter,
    )
    tracer = SdkReviewTracer(client)
    request = ReviewRequest(
        "example/data-service",
        17,
        "a" * 40,
        '+query = "SELECT * FROM events WHERE workspace_id = {}".format(workspace_id)',
    )
    fingerprint = SkillFingerprint(
        name="secure-pr-review",
        semantic_version="0.1.0",
        registry_version=1,
        source_digest="abc123",
        skillmd_sha256="def456",
    )
    evaluation = EvaluationCase(
        id="sql-format-interpolation",
        expected_decision=ReviewDecision.CHANGES_REQUESTED,
    )
    result = ReviewResult(
        decision=ReviewDecision.APPROVE,
        findings=(),
        provenance=ReviewProvenance("skill_demo", 1, ()),
        steps=("load_skill", "inspect_diff", "decide"),
    )

    with tracer.review(request, fingerprint, evaluation) as run:
        run.complete(result)

    client.flush()
    client.shutdown()
    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name == "registry.pr_review")
    skill = next(span for span in spans if span.name == "review.skill")
    assert root.attributes is not None
    assert root.attributes["demo.eval.case_id"] == "sql-format-interpolation"
    assert root.attributes["demo.eval.expected_decision"] == "changes_requested"
    assert root.attributes["review.decision"] == "approve"
    assert skill.attributes is not None
    assert skill.attributes["atlan.skill.name"] == "secure-pr-review"
    assert skill.attributes["atlan.skill.version"] == "0.1.0"
    assert skill.attributes["atlan.skill.source_digest"] == "abc123"
    assert skill.attributes["atlan.skill.skillmd_sha256"] == "def456"
    assert skill.attributes["atlan.skill.fingerprint_source"] == "registry"
    serialized = repr([(span.name, span.attributes) for span in spans])
    assert "SELECT * FROM events" not in serialized
