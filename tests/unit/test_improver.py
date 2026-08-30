from __future__ import annotations

from registry_pr_review_demo.cli_trace import CliTraceReceipt
from registry_pr_review_demo.improver import ImprovementAgent
from registry_pr_review_demo.models import (
    EvaluationCase,
    ReviewDecision,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillFingerprint,
)
from registry_pr_review_demo.trace_reader import TraceEvidence


class Reader:
    def fetch_case(self, *, skill_id: str, version_ordinal: int, case_id: str) -> TraceEvidence:
        assert (skill_id, version_ordinal, case_id) == (
            "skill_target",
            1,
            "sql-format-interpolation",
        )
        return TraceEvidence(
            trace={
                "trace_id": "a" * 32,
                "attributes": {"review.decision": "approve"},
            },
            spans=(),
        )


class Submitter:
    def __init__(self) -> None:
        self.records: list[object] = []

    def submit(self, record: object) -> CliTraceReceipt:
        self.records.append(record)
        return CliTraceReceipt(accepted=True, trace_id="b" * 32)


def test_improvement_agent_reads_target_trace_proposes_patch_and_sends_cli_trace() -> None:
    submitter = Submitter()
    agent = ImprovementAgent(reader=Reader(), submitter=submitter)
    result = agent.run(
        target=SkillArtifactRef("skill_target", 1),
        analyzer_fingerprint=SkillFingerprint(
            "trace-driven-skill-improvement",
            "0.1.0",
            1,
            "source-analyzer",
            "skillmd-analyzer",
        ),
        evaluation=EvaluationCase(
            "sql-format-interpolation",
            ReviewDecision.CHANGES_REQUESTED,
            '+query = "SELECT * FROM events WHERE id = {}".format(workspace_id)',
        ),
        rules=(
            ReviewRule(
                "parameterize-sql",
                r"f[\"']SELECT\b",
                Severity.HIGH,
                "Use parameterized SQL.",
            ),
        ),
    )

    assert result.proposal.kind == "false_negative"
    assert result.proposal.approved is False
    assert result.analyzer_trace_id == "b" * 32
    assert len(submitter.records) == 1
