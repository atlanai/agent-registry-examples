from __future__ import annotations

import atlan_ai
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from registry_pr_review_demo.worker import run_sdk_job


def test_worker_sdk_mode_emits_graph_result_and_skill_trace() -> None:
    exporter = InMemorySpanExporter()
    client = atlan_ai.init(
        service_name="registry-pr-review-worker-test",
        api_key="worker-sdk-test-key",
        base_url="https://agentgateway.example.com",
        workspace_id="workspace_data",
        trace_content=False,
        span_exporter=exporter,
    )
    payload: dict[str, object] = {
        "request": {
            "repository": "example/data-service",
            "pull_request_number": 17,
            "head_sha": "a" * 40,
            "diff": '+query = "SELECT * FROM events WHERE id = {}".format(workspace_id)',
        },
        "skill": {
            "id": "skill_demo",
            "version": 1,
            "name": "secure-pr-review",
            "semantic_version": "0.1.0",
            "source_digest": "abc123",
            "skillmd_sha256": "def456",
            "rules": [],
        },
        "documents": [],
        "evaluation": {
            "id": "sql-format-interpolation",
            "expected_decision": "changes_requested",
        },
    }

    result = run_sdk_job(payload, client=client)

    client.flush()
    client.shutdown()
    assert result["decision"] == "approve"
    assert isinstance(result["trace_id"], str)
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} >= {"registry.pr_review", "review.skill"}
