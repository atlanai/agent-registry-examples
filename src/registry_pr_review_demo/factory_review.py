from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from registry_pr_review_demo.cli_trace import CliTraceRecord, CliTraceSubmitter
from registry_pr_review_demo.models import EvaluationCase, ReviewDecision, SkillFingerprint
from registry_pr_review_demo.registration import DATA_WORKSPACE_ID
from registry_pr_review_demo.worker import run_job

MAX_DIFF_BYTES = 2_000_000


def run_factory_review(
    *,
    root: Path,
    diff_path: Path,
    output_path: Path,
    summary_path: Path,
    submit_trace_if_configured: bool = False,
    publish_github_summary: bool = False,
) -> dict[str, object]:
    diff = diff_path.read_text(encoding="utf-8")
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        raise ValueError("review diff exceeds the 2 MB factory limit")
    skill_rules = _json_object(root / "skills/secure-pr-review/rules.json")
    references = _json_object(root / "registry/skill-references.json")
    secure_reference = _object(references.get("secure-pr-review"), "secure-pr-review")
    knowledge_index = _json_object(root / "knowledge/index.json")
    document_map = _object(knowledge_index.get("documents"), "knowledge documents")
    documents = [
        {
            "id": document_id,
            "path": f"knowledge/{filename}",
            "content": (root / "knowledge" / filename).read_text(encoding="utf-8"),
        }
        for document_id, filename in _string_map(document_map).items()
    ]
    head_sha = os.environ.get("GITHUB_SHA", "0" * 40)
    if len(head_sha) != 40 or any(char not in "0123456789abcdef" for char in head_sha):
        raise ValueError("GITHUB_SHA must be a lowercase 40-character hexadecimal commit SHA")
    payload: dict[str, object] = {
        "request": {
            "repository": "atlanai/software-factory-demo",
            "pull_request_number": 101,
            "head_sha": head_sha,
            "diff": diff,
        },
        "skill": {
            "id": _string(secure_reference, "id"),
            "version": _integer(secure_reference, "version"),
            "name": "secure-pr-review",
            "semantic_version": _string(secure_reference, "semantic_version"),
            "source_digest": _string(secure_reference, "source_digest"),
            "skillmd_sha256": _string(secure_reference, "skillmd_sha256"),
            "rules": skill_rules.get("rules"),
        },
        "documents": documents,
    }
    result = run_job(payload)
    trace_id: str | None = None
    if submit_trace_if_configured and os.environ.get("ATLANAI_TOKEN"):
        matched = tuple(
            _string(_object(item, "finding"), "rule_id")
            for item in _sequence(result.get("findings"), "findings")
        )
        receipt = CliTraceSubmitter(workspace_id=DATA_WORKSPACE_ID).submit(
            CliTraceRecord(
                session_id=f"github-{os.environ.get('GITHUB_RUN_ID', head_sha[:12])}-review",
                service_name="software-factory-review-ci",
                fingerprint=SkillFingerprint(
                    name="secure-pr-review",
                    semantic_version=_string(secure_reference, "semantic_version"),
                    registry_version=_integer(secure_reference, "version"),
                    source_digest=_string(secure_reference, "source_digest"),
                    skillmd_sha256=_string(secure_reference, "skillmd_sha256"),
                ),
                evaluation=EvaluationCase(
                    id="risky-order-change",
                    expected_decision=ReviewDecision.CHANGES_REQUESTED,
                ),
                decision=_string(result, "decision"),
                finding_count=len(matched),
                matched_rule_ids=matched,
            )
        )
        trace_id = receipt.trace_id
        result["trace_id"] = trace_id
    result["runtime"] = "github-actions"
    result["trace_status"] = "submitted" if trace_id else "not_configured"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = _summary(result, diff_path, trace_id)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")
    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary and publish_github_summary:
        with Path(github_summary).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    return result


def _summary(result: Mapping[str, object], diff_path: Path, trace_id: str | None) -> str:
    findings = _sequence(result.get("findings"), "findings")
    lines = [
        "# Governed software review",
        "",
        f"- Decision: **{_string(result, 'decision')}**",
        "- Skill: `secure-pr-review` v1",
        f"- Proposed change: `{diff_path.as_posix()}`",
        f"- Findings: {len(findings)}",
        f"- Registry trace: `{trace_id or 'not submitted (ATLANAI_TOKEN unavailable)'}`",
        "",
        "## Findings",
        "",
    ]
    for raw in findings:
        finding = _object(raw, "finding")
        lines.append(
            f"- `{_string(finding, 'rule_id')}` at diff line "
            f"{_integer(finding, 'line')}: {_string(finding, 'message')}"
        )
    if not findings:
        lines.append("- No governed findings.")
    lines.extend(
        [
            "",
            "The proposed patch is review evidence only. It is never applied to the product code.",
            "",
        ]
    )
    return "\n".join(lines)


def _json_object(path: Path) -> dict[str, object]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    return _object(payload, path.name)


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return cast(list[object], value)


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _string_map(data: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(value, str):
            raise ValueError("knowledge document paths must be strings")
        result[key] = value
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the governed software-factory review")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--diff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--submit-trace-if-configured", action="store_true")
    parser.add_argument("--github-summary", action="store_true")
    args = parser.parse_args(argv)
    run_factory_review(
        root=cast(Path, args.root),
        diff_path=cast(Path, args.diff),
        output_path=cast(Path, args.output),
        summary_path=cast(Path, args.summary),
        submit_trace_if_configured=cast(bool, args.submit_trace_if_configured),
        publish_github_summary=cast(bool, args.github_summary),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
