from __future__ import annotations

from registry_pr_review_demo.cli_trace import CliTraceReceipt
from registry_pr_review_demo.trace_reader import TraceEvidence
from registry_pr_review_demo.worker import run_improver_job


class Reader:
    def fetch_case(self, *, skill_id: str, version_ordinal: int, case_id: str) -> TraceEvidence:
        return TraceEvidence(
            trace={
                "trace_id": "a" * 32,
                "attributes": {"review.decision": "approve"},
            },
            spans=(),
        )


class Submitter:
    def submit(self, record: object) -> CliTraceReceipt:
        return CliTraceReceipt(True, "b" * 32)


def test_worker_improvement_mode_returns_unapproved_proposal_and_trace_id() -> None:
    payload: dict[str, object] = {
        "target_skill": {"id": "skill_target", "version": 1},
        "analyzer_skill": {
            "name": "trace-driven-skill-improvement",
            "semantic_version": "0.1.0",
            "registry_version": 1,
            "source_digest": "source-analyzer",
            "skillmd_sha256": "skillmd-analyzer",
        },
        "evaluation": {
            "id": "sql-format-interpolation",
            "expected_decision": "changes_requested",
            "diff": '+query = "SELECT * FROM events WHERE id = {}".format(workspace_id)',
        },
        "rules": [
            {
                "id": "parameterize-sql",
                "pattern": "f[\\\"']SELECT\\b",
                "severity": "high",
                "message": "Use parameterized SQL.",
                "knowledge_ids": [],
            }
        ],
    }

    result = run_improver_job(payload, reader=Reader(), submitter=Submitter())

    proposal = result["proposal"]
    assert isinstance(proposal, dict)
    assert proposal["kind"] == "false_negative"
    assert proposal["approved"] is False
    assert result["analyzer_trace_id"] == "b" * 32
