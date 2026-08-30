from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from registry_pr_review_demo.cli_trace import (
    CliTraceReceipt,
    CliTraceRecord,
)
from registry_pr_review_demo.models import (
    EvaluationCase,
    ReviewRule,
    SkillArtifactRef,
    SkillFingerprint,
)
from registry_pr_review_demo.trace_analysis import ImprovementProposal, analyze_trace_gap
from registry_pr_review_demo.trace_reader import TraceEvidence


class TraceReader(Protocol):
    def fetch_case(self, *, skill_id: str, version_ordinal: int, case_id: str) -> TraceEvidence: ...


class TraceSubmitter(Protocol):
    def submit(self, record: CliTraceRecord) -> CliTraceReceipt: ...


@dataclass(frozen=True, slots=True)
class ImprovementRunResult:
    proposal: ImprovementProposal
    analyzer_trace_id: str


class ImprovementAgent:
    def __init__(self, *, reader: TraceReader, submitter: TraceSubmitter) -> None:
        self._reader = reader
        self._submitter = submitter

    def run(
        self,
        *,
        target: SkillArtifactRef,
        analyzer_fingerprint: SkillFingerprint,
        evaluation: EvaluationCase,
        rules: tuple[ReviewRule, ...],
    ) -> ImprovementRunResult:
        evidence = self._reader.fetch_case(
            skill_id=target.id,
            version_ordinal=target.version,
            case_id=evaluation.id,
        )
        proposal = analyze_trace_gap(
            trace=evidence.trace,
            evaluation=evaluation,
            rules=rules,
        )
        record = CliTraceRecord(
            session_id=f"improve-{target.id}-v{target.version}-{evaluation.id}",
            service_name="registry-skill-improver-cli",
            fingerprint=analyzer_fingerprint,
            evaluation=evaluation,
            decision="proposal_ready" if proposal.kind == "false_negative" else proposal.kind,
            finding_count=1 if proposal.rule_id is not None else 0,
            matched_rule_ids=((proposal.rule_id,) if proposal.rule_id is not None else ()),
        )
        receipt = self._submitter.submit(record)
        if not receipt.accepted:
            raise RuntimeError("CLI analyzer trace was not accepted")
        return ImprovementRunResult(
            proposal=proposal,
            analyzer_trace_id=receipt.trace_id,
        )
