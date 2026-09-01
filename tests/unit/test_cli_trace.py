from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import registry_pr_review_demo.cli_trace as cli_trace
from registry_pr_review_demo.cli_trace import (
    CliCommandResult,
    CliTraceRecord,
    CliTraceSubmitter,
    KiroCliTraceRecord,
    KiroCliTraceSubmitter,
    OtlpPayloadSubmitter,
    build_kiro_otlp_payload,
    build_otlp_payload,
    build_sdk_otlp_payload,
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


def test_kiro_cli_trace_uses_rest_with_agent_skills_and_sanitized_tools(
    tmp_path: Path,
) -> None:
    fingerprint = SkillFingerprint(
        name="secure-pr-review",
        semantic_version="0.1.1",
        registry_version=2,
        source_digest="a" * 64,
        skillmd_sha256="b" * 64,
    )
    record = KiroCliTraceRecord(
        session_id="kiro-session",
        agent_id="agent_kiro",
        skills=(("skill_secure", fingerprint),),
        attributes={"daytona.sandbox.id": "sandbox_demo"},
        decision="changes_requested",
        finding_count=1,
        tool_names=("read", "grep"),
        model="kiro-auto",
        input_tokens=5291,
        credits_used=0.3443911164179104,
        estimated_cost_usd=0.006887822328358208,
        assistant_response="Changes requested with one verified finding.",
    )
    payload = build_kiro_otlp_payload(record, start_time_ns=1_000, end_time_ns=2_000)
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 5
    root_attributes = {
        item["key"]: next(iter(item["value"].values())) for item in spans[0]["attributes"]
    }
    request_attributes = {
        item["key"]: next(iter(item["value"].values())) for item in spans[2]["attributes"]
    }
    skill_attributes = {
        item["key"]: next(iter(item["value"].values())) for item in spans[3]["attributes"]
    }
    response_attributes = {
        item["key"]: next(iter(item["value"].values())) for item in spans[4]["attributes"]
    }
    assert spans[0]["name"] == "software_factory.pr_review"
    assert spans[1]["name"] == "kiro-review.turn 1"
    assert spans[2]["name"] == "chat kiro-auto request"
    assert spans[3]["name"] == "execute_tool secure-pr-review"
    assert spans[4]["name"] == "chat kiro-auto final"
    assert root_attributes["atlan.agent.id"] == "agent_kiro"
    assert root_attributes["daytona.sandbox.id"] == "sandbox_demo"
    assert request_attributes["atlan.span.type"] == "llm"
    assert request_attributes["gen_ai.request.model"] == "kiro-auto"
    assert "Registry-governed skills" in request_attributes["input.value"]
    assert "output.value" not in request_attributes
    assert response_attributes["gen_ai.usage.input_tokens"] == "5291"
    assert response_attributes["llm.cost.total"] == 0.006887822328358208
    assert "Changes requested" in response_attributes["output.value"]
    assert "input.value" not in response_attributes
    assert skill_attributes["atlan.skill.id"] == "skill_secure"
    assert skill_attributes["gen_ai.tool.name"] == "secure-pr-review"
    assert skill_attributes["gen_ai.tool.type"] == "skill"
    assert [event["attributes"][0]["value"]["stringValue"] for event in spans[0]["events"]] == [
        "read",
        "grep",
    ]

    observed: dict[str, object] = {}

    def runner(args: Sequence[str]) -> CliCommandResult:
        observed["args"] = tuple(args)
        return CliCommandResult(0, '{"partialSuccess":{}}', "")

    receipt = KiroCliTraceSubmitter(
        workspace_id="workspace_data", runner=runner, temp_dir=tmp_path
    ).submit(record)
    args = cast(tuple[str, ...], observed["args"])
    assert args[:4] == ("atlanai", "api", "post", "/otel/v1/traces")
    assert receipt.trace_id
    assert list(tmp_path.iterdir()) == []


def test_sdk_payload_keeps_governed_metadata_and_drops_raw_content(tmp_path: Path) -> None:
    context = SimpleNamespace(trace_id=int("a" * 32, 16), span_id=int("b" * 16, 16))
    parent = SimpleNamespace(span_id=int("c" * 16, 16))
    spans = [
        SimpleNamespace(
            context=context,
            parent=parent,
            name="review.skill",
            start_time=1_000,
            end_time=2_000,
            attributes={
                "atlan.skill.id": "skill_demo",
                "review.finding_count": 1,
                "review.raw_diff": "must-not-ship",
                "untrusted.input": "SELECT secret",
            },
        )
    ]
    payload = build_sdk_otlp_payload(spans)
    serialized = json.dumps(payload)
    assert "skill_demo" in serialized
    assert "must-not-ship" not in serialized
    assert "SELECT secret" not in serialized

    calls = 0

    def runner(_args: Sequence[str]) -> CliCommandResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return CliCommandResult(1, "", "HTTP 503 service is temporarily unavailable")
        return CliCommandResult(0, '{"partialSuccess":{}}', "")

    receipt = OtlpPayloadSubmitter(
        workspace_id="workspace_data", runner=runner, temp_dir=tmp_path
    ).submit(payload)
    assert receipt.trace_id == "a" * 32
    assert calls == 2


def test_sdk_otlp_value_validation() -> None:
    assert cli_trace._otlp_value(True) == {"boolValue": True}  # pyright: ignore[reportPrivateUsage]
    assert cli_trace._otlp_value(1.5) == {"doubleValue": 1.5}  # pyright: ignore[reportPrivateUsage]
    assert cli_trace._otlp_value("value") == {  # pyright: ignore[reportPrivateUsage]
        "stringValue": "value"
    }
    assert cli_trace._otlp_value(["x", 2, None]) == {  # pyright: ignore[reportPrivateUsage]
        "arrayValue": {"values": [{"stringValue": "x"}, {"intValue": "2"}]}
    }
    assert cli_trace._otlp_value(object()) is None  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="requires finished spans"):
        build_sdk_otlp_payload([])
