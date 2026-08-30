from __future__ import annotations

import atlan_ai
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from registry_pr_review_demo.worker import run_kiro_trace_job


def test_kiro_trace_worker_emits_agent_and_multiple_skill_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAN_API_KEY", "agent-test-key")
    exporter = InMemorySpanExporter()
    client = atlan_ai.init(
        service_name="kiro-pr-review-agent-test",
        api_key="agent-test-key",
        base_url="https://agentgateway.example.com",
        workspace_id="workspace_data",
        trace_content=False,
        span_exporter=exporter,
    )
    skills = [
        {
            "id": "skill_secure",
            "name": "secure-pr-review",
            "semantic_version": "0.1.1",
            "version": 2,
            "source_digest": "a" * 64,
            "skillmd_sha256": "b" * 64,
        },
        {
            "id": "skill_tests",
            "name": "test-impact-analysis",
            "semantic_version": "0.1.0",
            "version": 1,
            "source_digest": "c" * 64,
            "skillmd_sha256": "d" * 64,
        },
    ]
    payload = {
        "agent_id": "agent_kiro",
        "session_id": "session_kiro",
        "skills": skills,
        "tool_names": ["read", "grep"],
        "attributes": {"github.repository": "atlanai/software-factory-demo"},
        "result": {
            "decision": "changes_requested",
            "findings": [{"rule_id": "parameterize-sql"}],
            "skills_used": [
                {
                    "id": skill["id"],
                    "version": skill["version"],
                    "source_digest": skill["source_digest"],
                }
                for skill in skills
            ],
        },
    }

    result = run_kiro_trace_job(payload, client=client)

    client.flush()
    client.shutdown()
    assert result["trace_id"]
    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name == "software_factory.pr_review")
    skill_spans = [span for span in spans if span.name == "review.skill"]
    assert root.attributes is not None
    assert root.attributes["atlan.agent.id"] == "agent_kiro"
    assert root.attributes["review.decision"] == "changes_requested"
    assert {span.attributes["atlan.skill.id"] for span in skill_spans if span.attributes} == {
        "skill_secure",
        "skill_tests",
    }
    assert [
        event.attributes["tool.name"]
        for event in root.events
        if event.name == "kiro.tool" and event.attributes is not None
    ] == ["read", "grep"]


def test_kiro_trace_worker_requires_agent_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAN_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="requires ATLAN_API_KEY"):
        run_kiro_trace_job({}, client=object())  # type: ignore[arg-type]
