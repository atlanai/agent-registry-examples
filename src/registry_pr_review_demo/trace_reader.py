from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from registry_pr_review_demo.cli_trace import CliCommandResult

SKILL_ID = re.compile(r"^skill_[0-9A-Za-z]+$")
TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def _default_runner(args: Sequence[str]) -> CliCommandResult:
    from registry_pr_review_demo.cli_trace import run_atlanai_cli

    return run_atlanai_cli(args)


@dataclass(frozen=True, slots=True)
class TraceEvidence:
    trace: dict[str, object]
    spans: tuple[dict[str, object], ...]


class AtlanCliTraceReader:
    def __init__(
        self,
        *,
        runner: Callable[[Sequence[str]], CliCommandResult] = _default_runner,
    ) -> None:
        self._runner = runner

    def fetch_case(
        self,
        *,
        skill_id: str,
        version_ordinal: int,
        case_id: str,
    ) -> TraceEvidence:
        if not SKILL_ID.fullmatch(skill_id) or version_ordinal < 1:
            raise ValueError("invalid Registry skill reference")
        trace_page = self._json_command(
            (
                "atlanai",
                "api",
                "get",
                f"skill:/skills/{skill_id}/traces",
                "-F",
                f"version_ordinal={version_ordinal}",
                "-F",
                "limit=50",
            )
        )
        raw_items = trace_page.get("items")
        if not isinstance(raw_items, list):
            raise RuntimeError("skill trace list returned an invalid items field")
        traces = tuple(_object(item, "trace") for item in cast(list[object], raw_items))
        saw_case_without_decision = False
        for trace in traces:
            trace_id = trace.get("trace_id")
            if not isinstance(trace_id, str) or not TRACE_ID.fullmatch(trace_id):
                raise RuntimeError("selected trace has an invalid trace_id")
            span_page = self._json_command(
                (
                    "atlanai",
                    "api",
                    "get",
                    f"skill:/skills/{skill_id}/traces/{trace_id}/spans",
                    "-F",
                    f"version_ordinal={version_ordinal}",
                    "-F",
                    "limit=100",
                    "-f",
                    "fields=core,attributes",
                )
            )
            raw_spans = span_page.get("items")
            if not isinstance(raw_spans, list):
                raise RuntimeError("skill span list returned an invalid items field")
            spans = tuple(_object(item, "span") for item in cast(list[object], raw_spans))
            attributes = _span_attributes(spans)
            if attributes.get("demo.eval.case_id") == case_id and isinstance(
                attributes.get("review.decision"), str
            ):
                return TraceEvidence(trace={**trace, "attributes": attributes}, spans=spans)
            if attributes.get("demo.eval.case_id") == case_id:
                saw_case_without_decision = True
        if saw_case_without_decision:
            raise LookupError(
                f"trace found for evaluation case {case_id!r}, but review.decision is unavailable"
            )
        raise LookupError(f"no trace found for evaluation case {case_id!r}")

    def _json_command(self, args: Sequence[str]) -> dict[str, object]:
        result = self._runner(args)
        if result.exit_code != 0:
            raise RuntimeError("atlanai trace read failed")
        try:
            payload: object = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("atlanai trace read returned invalid JSON") from error
        return _object(payload, "response")


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _span_attributes(spans: Sequence[Mapping[str, object]]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for span in spans:
        raw_attributes = span.get("attributes")
        if not isinstance(raw_attributes, dict):
            continue
        attributes = cast(dict[str, object], raw_attributes)
        raw_span = attributes.get("span")
        if isinstance(raw_span, dict):
            _flatten(cast(dict[str, object], raw_span), merged)
    return merged


def _flatten(source: Mapping[str, object], target: dict[str, object], prefix: str = "") -> None:
    for key, value in source.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten(cast(dict[str, object], value), target, path)
        else:
            target[path] = value
