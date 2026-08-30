from __future__ import annotations

import pytest

from registry_pr_review_demo.cli_trace import CliTraceReceipt, KiroCliTraceRecord
from registry_pr_review_demo.worker import run_kiro_trace_job


class Submitter:
    def __init__(self) -> None:
        self.record: KiroCliTraceRecord | None = None

    def submit(self, record: KiroCliTraceRecord) -> CliTraceReceipt:
        self.record = record
        return CliTraceReceipt(accepted=True, trace_id="b" * 32)


def test_kiro_trace_worker_submits_agent_and_skill_evidence_through_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAN_API_KEY", "agent-test-key")
    monkeypatch.setenv("ATLANAI_TOKEN", "agent-test-key")
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
            "semantic_version": "0.1.1",
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
    submitter = Submitter()

    result = run_kiro_trace_job(payload, submitter=submitter)

    assert result["trace_id"] == "b" * 32
    assert submitter.record is not None
    assert submitter.record.agent_id == "agent_kiro"
    assert submitter.record.tool_names == ("read", "grep")
    assert {skill_id for skill_id, _ in submitter.record.skills} == {
        "skill_secure",
        "skill_tests",
    }


def test_kiro_trace_worker_requires_rest_and_cli_agent_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAN_API_KEY", raising=False)
    monkeypatch.delenv("ATLANAI_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="REST and CLI"):
        run_kiro_trace_job({})
