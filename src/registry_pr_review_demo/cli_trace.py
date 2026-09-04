from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from registry_pr_review_demo.models import EvaluationCase, SkillFingerprint


@dataclass(frozen=True, slots=True)
class CliCommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class CliTraceRecord:
    session_id: str
    service_name: str
    fingerprint: SkillFingerprint
    evaluation: EvaluationCase
    decision: str
    finding_count: int
    matched_rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CliTraceReceipt:
    accepted: bool
    trace_id: str


@dataclass(frozen=True, slots=True)
class KiroCliTraceRecord:
    session_id: str
    agent_id: str
    skills: tuple[tuple[str, SkillFingerprint], ...]
    attributes: dict[str, str]
    decision: str
    finding_count: int
    tool_names: tuple[str, ...]
    model: str
    input_tokens: int
    credits_used: float
    estimated_cost_usd: float
    assistant_response: str
    visitor_id: str | None = None
    start_time_ns: int | None = None
    end_time_ns: int | None = None


def _hex_id(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:length]


def _string_attribute(key: str, value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": value}}


def _int_attribute(key: str, value: int) -> dict[str, object]:
    return {"key": key, "value": {"intValue": str(value)}}


def _double_attribute(key: str, value: float) -> dict[str, object]:
    return {"key": key, "value": {"doubleValue": value}}


def _bool_attribute(key: str, value: bool) -> dict[str, object]:
    return {"key": key, "value": {"boolValue": value}}


def build_otlp_payload(
    record: CliTraceRecord,
    *,
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> dict[str, Any]:
    started = start_time_ns if start_time_ns is not None else time.time_ns()
    ended = end_time_ns if end_time_ns is not None else started + 1_000_000
    trace_id = _hex_id(record.session_id, 32)
    root_span_id = _hex_id(f"{record.session_id}:root", 16)
    skill_span_id = _hex_id(f"{record.session_id}:skill", 16)
    root_attributes = [
        _string_attribute("atlan.span.type", "task"),
        _string_attribute("demo.eval.case_id", record.evaluation.id),
        _string_attribute("demo.eval.expected_decision", record.evaluation.expected_decision.value),
        _string_attribute("review.decision", record.decision),
        _int_attribute("review.finding_count", record.finding_count),
    ]
    for rule_id in record.matched_rule_ids:
        root_attributes.append(_string_attribute("review.matched_rule_id", rule_id))
    skill_attributes = [
        _string_attribute("atlan.span.type", "tool"),
        _string_attribute("atlan.skill.name", record.fingerprint.name),
        _string_attribute("atlan.skill.version", record.fingerprint.semantic_version),
        _int_attribute("atlan.registry.skill.version_ordinal", record.fingerprint.registry_version),
        _string_attribute("atlan.skill.source_digest", record.fingerprint.source_digest),
        _string_attribute("atlan.skill.skillmd_sha256", record.fingerprint.skillmd_sha256),
        _string_attribute("atlan.skill.fingerprint_source", "registry"),
        _string_attribute("demo.eval.case_id", record.evaluation.id),
        _string_attribute("demo.eval.expected_decision", record.evaluation.expected_decision.value),
        _string_attribute("review.decision", record.decision),
        _int_attribute("review.finding_count", record.finding_count),
    ]
    for rule_id in record.matched_rule_ids:
        skill_attributes.append(_string_attribute("review.matched_rule_id", rule_id))
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _string_attribute("service.name", record.service_name),
                        _string_attribute("telemetry.sdk.language", "cli-json"),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "registry-pr-review-cli", "version": "0.1.0"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": root_span_id,
                                "name": "registry.skill_improvement",
                                "startTimeUnixNano": str(started),
                                "endTimeUnixNano": str(ended),
                                "attributes": root_attributes,
                            },
                            {
                                "traceId": trace_id,
                                "spanId": skill_span_id,
                                "parentSpanId": root_span_id,
                                "name": "improvement.skill",
                                "startTimeUnixNano": str(started + 1),
                                "endTimeUnixNano": str(ended - 1),
                                "attributes": skill_attributes,
                            },
                        ],
                    }
                ],
            }
        ]
    }


def build_kiro_otlp_payload(
    record: KiroCliTraceRecord,
    *,
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> dict[str, Any]:
    started = (
        start_time_ns
        if start_time_ns is not None
        else record.start_time_ns
        if record.start_time_ns is not None
        else time.time_ns()
    )
    ended = (
        end_time_ns
        if end_time_ns is not None
        else record.end_time_ns
        if record.end_time_ns is not None
        else started + 1_000_000
    )
    if ended <= started:
        raise ValueError("Kiro trace end time must follow its start time")
    trace_id = _hex_id(record.session_id, 32)
    root_span_id = _hex_id(f"{record.session_id}:root", 16)
    turn_span_id = _hex_id(f"{record.session_id}:turn:1", 16)
    request_chat_span_id = _hex_id(f"{record.session_id}:chat:request", 16)
    response_chat_span_id = _hex_id(f"{record.session_id}:chat:response", 16)
    root_attributes = [
        _string_attribute("atlan.span.type", "task"),
        _string_attribute("atlan.agent.id", record.agent_id),
        _string_attribute("agent.runtime", "kiro-cli-daytona"),
        _string_attribute("review.decision", record.decision),
        _int_attribute("review.finding_count", record.finding_count),
        _string_attribute("atlan.trace.content_policy", "sanitized-demo"),
        _bool_attribute("atlan.trace.content_stored", True),
        _int_attribute("atlan.event.seq", 0),
    ]
    root_attributes.extend(
        _string_attribute(key, value) for key, value in sorted(record.attributes.items())
    )
    events = [
        {
            "name": "kiro.tool",
            "timeUnixNano": str(started + index + 1),
            "attributes": [_string_attribute("tool.name", tool_name)],
        }
        for index, tool_name in enumerate(record.tool_names)
    ]
    spans: list[dict[str, object]] = [
        {
            "traceId": trace_id,
            "spanId": root_span_id,
            "name": "software_factory.pr_review",
            "startTimeUnixNano": str(started),
            "endTimeUnixNano": str(ended),
            "attributes": root_attributes,
            "events": events,
        },
        {
            "traceId": trace_id,
            "spanId": turn_span_id,
            "parentSpanId": root_span_id,
            "name": "kiro-review.turn 1",
            "startTimeUnixNano": str(started + 1),
            "endTimeUnixNano": str(ended - 1),
            "attributes": [
                _string_attribute("atlan.span.type", "task"),
                _string_attribute("gen_ai.conversation.id", record.session_id),
                _string_attribute("gen_ai.agent.id", record.agent_id),
                _string_attribute("gen_ai.agent.name", "Kiro PR Review Agent"),
                _string_attribute("gen_ai.provider.name", "kiro"),
                _int_attribute("atlan.event.seq", 1),
            ],
        },
        {
            "traceId": trace_id,
            "spanId": request_chat_span_id,
            "parentSpanId": turn_span_id,
            "name": f"chat {record.model} request",
            "kind": 3,
            "startTimeUnixNano": str(started + 2),
            "endTimeUnixNano": str(ended - 2),
            "attributes": _kiro_request_chat_attributes(record),
        },
    ]
    for index, (skill_id, fingerprint) in enumerate(record.skills, start=3):
        arguments = json.dumps(
            {
                "skill_id": skill_id,
                "name": fingerprint.name,
                "version": fingerprint.registry_version,
                "source_digest": fingerprint.source_digest,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        tool_result = json.dumps(
            {"decision": record.decision, "status": "fingerprint_verified"},
            separators=(",", ":"),
            sort_keys=True,
        )
        spans.append(
            {
                "traceId": trace_id,
                "spanId": _hex_id(f"{record.session_id}:skill:{skill_id}", 16),
                "parentSpanId": request_chat_span_id,
                "name": f"execute_tool {fingerprint.name}",
                "startTimeUnixNano": str(started + index + 1),
                "endTimeUnixNano": str(ended - index - 1),
                "attributes": [
                    _string_attribute("atlan.span.type", "tool"),
                    _string_attribute("openinference.span.kind", "TOOL"),
                    _string_attribute("gen_ai.tool.name", fingerprint.name),
                    _string_attribute("gen_ai.tool.type", "skill"),
                    _string_attribute("gen_ai.tool.call.id", f"skill-{index}"),
                    _string_attribute("gen_ai.tool.call.arguments", arguments),
                    _string_attribute("gen_ai.tool.call.result", tool_result),
                    _string_attribute("input.value", arguments),
                    _string_attribute("output.value", tool_result),
                    _string_attribute(
                        "atlan.tool.target",
                        f"{fingerprint.name}@{fingerprint.registry_version}",
                    ),
                    _string_attribute("atlan.skill.id", skill_id),
                    _string_attribute("atlan.registry.skill.id", skill_id),
                    _string_attribute("atlan.skill.name", fingerprint.name),
                    _string_attribute("atlan.skill.version", fingerprint.semantic_version),
                    _int_attribute(
                        "atlan.registry.skill.version_ordinal",
                        fingerprint.registry_version,
                    ),
                    _string_attribute("atlan.skill.source_digest", fingerprint.source_digest),
                    _string_attribute("atlan.skill.skillmd_sha256", fingerprint.skillmd_sha256),
                    _string_attribute("atlan.skill.fingerprint_source", "registry"),
                    _int_attribute("atlan.event.seq", index),
                ],
            }
        )
    response_seq = 3 + len(record.skills)
    spans.append(
        {
            "traceId": trace_id,
            "spanId": response_chat_span_id,
            "parentSpanId": turn_span_id,
            "name": f"chat {record.model} final",
            "kind": 3,
            "startTimeUnixNano": str(started + response_seq + 1),
            "endTimeUnixNano": str(ended - response_seq - 1),
            "attributes": _kiro_response_chat_attributes(record, seq=response_seq),
        }
    )
    if record.visitor_id is not None:
        for span in spans:
            span_attributes = span.get("attributes")
            if isinstance(span_attributes, list):
                cast(list[object], span_attributes).append(
                    _string_attribute("atlan.visitor.id", record.visitor_id)
                )
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _string_attribute("service.name", "kiro-pr-review-agent"),
                        _string_attribute("telemetry.sdk.language", "atlanai-cli-rest"),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "software-factory-kiro-cli-enriched",
                            "version": "0.2.0",
                        },
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def _kiro_common_chat_attributes(record: KiroCliTraceRecord) -> list[dict[str, object]]:
    return [
        _string_attribute("atlan.span.type", "llm"),
        _string_attribute("openinference.span.kind", "LLM"),
        _string_attribute("gen_ai.request.model", record.model),
        _string_attribute("gen_ai.response.model", record.model),
        _string_attribute("llm.model_name", record.model),
        _string_attribute("gen_ai.provider.name", "kiro"),
    ]


def _kiro_request_chat_attributes(record: KiroCliTraceRecord) -> list[dict[str, object]]:
    system_text = (
        "You are a read-only Kiro PR review agent running in Daytona. Use only read, grep, glob, "
        "and disclose_context. Apply all Registry-governed skills directly. Do not delegate, "
        "execute or modify code, mutate Git, call the web, or store secrets."
    )
    prompt_text = (
        "Review the bounded synthetic order-service change using all Registry-governed skills. "
        "Return a validated decision with evidence. Raw source and diff content are intentionally "
        "omitted from telemetry."
    )
    input_messages = [
        {"role": "system", "parts": [{"type": "text", "content": system_text}]},
        {"role": "user", "parts": [{"type": "text", "content": prompt_text}]},
    ]
    return [
        *_kiro_common_chat_attributes(record),
        _string_attribute("input.value", json.dumps(input_messages, separators=(",", ":"))),
        _string_attribute("input.mime_type", "application/json"),
        _int_attribute("atlan.event.seq", 2),
    ]


def _kiro_response_chat_attributes(
    record: KiroCliTraceRecord, *, seq: int
) -> list[dict[str, object]]:
    output_messages = [
        {
            "role": "assistant",
            "parts": [{"type": "text", "content": record.assistant_response}],
        }
    ]
    return [
        *_kiro_common_chat_attributes(record),
        _string_attribute("output.value", json.dumps(output_messages, separators=(",", ":"))),
        _string_attribute("output.mime_type", "application/json"),
        _int_attribute("gen_ai.usage.input_tokens", record.input_tokens),
        _int_attribute("gen_ai.usage.output_tokens", 0),
        _int_attribute("llm.token_count.prompt", record.input_tokens),
        _int_attribute("llm.token_count.completion", 0),
        _int_attribute("llm.token_count.total", record.input_tokens),
        _double_attribute("llm.cost.total", record.estimated_cost_usd),
        _double_attribute("gen_ai.usage.cost", record.estimated_cost_usd),
        _double_attribute("atlan.kiro.credits_used", record.credits_used),
        _double_attribute("atlan.cost.billed_usd", 0.0),
        _double_attribute("atlan.cost.plan_equivalent_usd", record.estimated_cost_usd),
        _string_attribute(
            "atlan.cost.basis",
            "Kiro Pro plan-equivalent at USD 0.02 per credit; "
            "actual Free-plan billed cost is USD 0",
        ),
        _string_attribute("atlan.usage.input_token_basis", "kiro.breakdown.tools.tokens"),
        _bool_attribute("atlan.model.actual_provider_reported", False),
        _int_attribute("atlan.chat.text_parts", 1),
        _int_attribute("atlan.chat.reasoning_parts", 0),
        _int_attribute("atlan.event.seq", seq),
    ]


SDK_ALLOWED_ATTRIBUTE_NAMES = {
    "agent.runtime",
    "atlan.agent.environment_id",
    "atlan.agent.id",
    "atlan.agent.provider_id",
    "atlan.registry.skill.id",
    "atlan.registry.skill.version_ordinal",
    "atlan.skill.fingerprint_source",
    "atlan.skill.id",
    "atlan.skill.name",
    "atlan.skill.skillmd_sha256",
    "atlan.skill.source_digest",
    "atlan.skill.version",
    "atlan.span.type",
    "daytona.sandbox.id",
    "demo.eval.case_id",
    "demo.eval.expected_decision",
    "git.commit.sha",
    "github.pull_request.number",
    "github.repository",
    "review.decision",
    "review.finding_count",
    "review.matched_rule_ids",
}


def _otlp_value(value: object) -> dict[str, object] | None:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, (tuple, list)):
        values = [_otlp_value(item) for item in cast(Sequence[object], value)]
        return {"arrayValue": {"values": [item for item in values if item is not None]}}
    return None


def build_sdk_otlp_payload(spans: Sequence[object]) -> dict[str, Any]:
    """Serialize only governed SDK span metadata; raw prompts and diffs are excluded."""
    serialized: list[dict[str, object]] = []
    for raw in spans:
        span = cast(Any, raw)
        context = span.context
        attributes: list[dict[str, object]] = []
        for key, value in cast(Mapping[str, object], span.attributes or {}).items():
            if key not in SDK_ALLOWED_ATTRIBUTE_NAMES:
                continue
            otlp_value = _otlp_value(value)
            if otlp_value is not None:
                attributes.append({"key": key, "value": otlp_value})
        item: dict[str, object] = {
            "traceId": f"{context.trace_id:032x}",
            "spanId": f"{context.span_id:016x}",
            "name": str(span.name),
            "startTimeUnixNano": str(span.start_time),
            "endTimeUnixNano": str(span.end_time),
            "attributes": attributes,
        }
        if span.parent is not None:
            item["parentSpanId"] = f"{span.parent.span_id:016x}"
        serialized.append(item)
    if not serialized:
        raise ValueError("SDK trace export requires finished spans")
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _string_attribute("service.name", "pr-review-agent"),
                        _string_attribute("telemetry.sdk.language", "atlan-ai-python-sdk"),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "software-factory-langgraph-sdk", "version": "0.1.0"},
                        "spans": serialized,
                    }
                ],
            }
        ]
    }


def run_atlanai_cli(args: Sequence[str]) -> CliCommandResult:
    executable = shutil.which("atlanai")
    if executable is None or not args or args[0] != "atlanai":
        raise RuntimeError("atlanai CLI is unavailable")
    command = (executable, *args[1:])
    completed = subprocess.run(  # noqa: S603 - fixed executable, no shell
        command, check=False, capture_output=True, text=True
    )
    return CliCommandResult(completed.returncode, completed.stdout, completed.stderr)


def _run_cli_with_retry(
    runner: Callable[[Sequence[str]], CliCommandResult], args: Sequence[str]
) -> CliCommandResult:
    result = runner(args)
    for delay in (1.0, 2.0, 4.0):
        if result.exit_code == 0:
            return result
        detail = f"{result.stdout}\n{result.stderr}".lower()
        if "503" not in detail and "service is temporarily unavailable" not in detail:
            return result
        time.sleep(delay)
        result = runner(args)
    return result


class CliTraceSubmitter:
    def __init__(
        self,
        *,
        workspace_id: str,
        runner: Callable[[Sequence[str]], CliCommandResult] = run_atlanai_cli,
        temp_dir: Path | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._runner = runner
        self._temp_dir = temp_dir

    def submit(self, record: CliTraceRecord) -> CliTraceReceipt:
        payload = build_otlp_payload(record)
        trace_id = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
        fd, raw_path = tempfile.mkstemp(
            prefix="registry-trace-", suffix=".json", dir=self._temp_dir
        )
        path = Path(raw_path)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            result = _run_cli_with_retry(
                self._runner,
                (
                    "atlanai",
                    "api",
                    "post",
                    "/otel/v1/traces",
                    "--input",
                    str(path),
                    "-H",
                    "Content-Type:application/json",
                    "-H",
                    f"X-Atlan-Workspace-Id:{self._workspace_id}",
                ),
            )
            if result.exit_code != 0:
                raise RuntimeError("atlanai CLI trace submission failed")
            return CliTraceReceipt(accepted=True, trace_id=str(trace_id))
        finally:
            path.unlink(missing_ok=True)


class KiroCliTraceSubmitter:
    def __init__(
        self,
        *,
        workspace_id: str,
        runner: Callable[[Sequence[str]], CliCommandResult] = run_atlanai_cli,
        temp_dir: Path | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._runner = runner
        self._temp_dir = temp_dir

    def submit(self, record: KiroCliTraceRecord) -> CliTraceReceipt:
        payload = build_kiro_otlp_payload(record)
        root = cast(dict[str, Any], payload["resourceSpans"][0])
        trace_id = root["scopeSpans"][0]["spans"][0]["traceId"]
        fd, raw_path = tempfile.mkstemp(prefix="kiro-trace-", suffix=".json", dir=self._temp_dir)
        path = Path(raw_path)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            result = _run_cli_with_retry(
                self._runner,
                (
                    "atlanai",
                    "api",
                    "post",
                    "/otel/v1/traces",
                    "--input",
                    str(path),
                    "-H",
                    "Content-Type:application/json",
                    "-H",
                    f"X-Atlan-Workspace-Id:{self._workspace_id}",
                ),
            )
            if result.exit_code != 0:
                raise RuntimeError("Kiro CLI REST trace submission failed")
            return CliTraceReceipt(accepted=True, trace_id=str(trace_id))
        finally:
            path.unlink(missing_ok=True)


class OtlpPayloadSubmitter:
    def __init__(
        self,
        *,
        workspace_id: str,
        runner: Callable[[Sequence[str]], CliCommandResult] = run_atlanai_cli,
        temp_dir: Path | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._runner = runner
        self._temp_dir = temp_dir

    def submit(self, payload: Mapping[str, object]) -> CliTraceReceipt:
        resource_spans = cast(list[dict[str, Any]], payload["resourceSpans"])
        trace_id = resource_spans[0]["scopeSpans"][0]["spans"][0]["traceId"]
        fd, raw_path = tempfile.mkstemp(prefix="sdk-trace-", suffix=".json", dir=self._temp_dir)
        path = Path(raw_path)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            result = _run_cli_with_retry(
                self._runner,
                (
                    "atlanai",
                    "api",
                    "post",
                    "/otel/v1/traces",
                    "--input",
                    str(path),
                    "-H",
                    "Content-Type:application/json",
                    "-H",
                    f"X-Atlan-Workspace-Id:{self._workspace_id}",
                ),
            )
            if result.exit_code != 0:
                detail = re.sub(
                    r"(?i)(api[_-]?key|token|authorization)(\s*[=:]\s*)\S+",
                    r"\1\2[REDACTED]",
                    result.stderr or result.stdout or "no CLI output",
                )[-2000:]
                raise RuntimeError(f"SDK CLI transport failed: {detail}")
            return CliTraceReceipt(accepted=True, trace_id=str(trace_id))
        finally:
            path.unlink(missing_ok=True)
