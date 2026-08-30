from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from registry_pr_review_demo.cli_trace import (
    CliCommandResult,
    CliTraceRecord,
    CliTraceSubmitter,
    build_otlp_payload,
)
from registry_pr_review_demo.models import EvaluationCase, ReviewDecision, SkillFingerprint


def record() -> CliTraceRecord:
    return CliTraceRecord(
        session_id="improve-session-1",
        service_name="registry-skill-improver-cli",
        fingerprint=SkillFingerprint(
            name="trace-driven-skill-improvement",
            semantic_version="0.1.0",
            registry_version=1,
            source_digest="source123",
            skillmd_sha256="skillmd123",
        ),
        evaluation=EvaluationCase(
            id="sql-format-interpolation",
            expected_decision=ReviewDecision.CHANGES_REQUESTED,
        ),
        decision="proposal_ready",
        finding_count=1,
        matched_rule_ids=("parameterize-sql",),
    )


def test_cli_trace_payload_is_valid_otlp_json_with_skill_fingerprints() -> None:
    payload = build_otlp_payload(record(), start_time_ns=1_000, end_time_ns=2_000)

    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
    skill_attributes = {
        item["key"]: next(iter(item["value"].values())) for item in spans[1]["attributes"]
    }
    assert skill_attributes["atlan.skill.name"] == "trace-driven-skill-improvement"
    assert skill_attributes["atlan.skill.source_digest"] == "source123"
    assert skill_attributes["atlan.skill.skillmd_sha256"] == "skillmd123"
    assert skill_attributes["demo.eval.case_id"] == "sql-format-interpolation"
    assert skill_attributes["demo.eval.expected_decision"] == "changes_requested"
    assert skill_attributes["review.decision"] == "proposal_ready"
    assert skill_attributes["review.finding_count"] == "1"
    assert skill_attributes["review.matched_rule_id"] == "parameterize-sql"


def test_cli_submitter_uses_atlanai_without_putting_a_token_in_arguments(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def runner(args: Sequence[str]) -> CliCommandResult:
        observed["args"] = tuple(args)
        payload_path = Path(args[args.index("--input") + 1])
        observed["payload"] = json.loads(payload_path.read_text(encoding="utf-8"))
        return CliCommandResult(exit_code=0, stdout='{"partialSuccess":{}}', stderr="")

    submitter = CliTraceSubmitter(
        workspace_id="workspace_data",
        runner=runner,
        temp_dir=tmp_path,
    )
    receipt = submitter.submit(record())

    args = observed["args"]
    assert isinstance(args, tuple)
    typed_args = cast(tuple[str, ...], args)
    assert typed_args[:4] == ("atlanai", "api", "post", "/otel/v1/traces")
    assert "ATLANAI_TOKEN" not in " ".join(typed_args)
    assert "workspace_data" in " ".join(typed_args)
    assert receipt.accepted is True
    assert list(tmp_path.iterdir()) == []
