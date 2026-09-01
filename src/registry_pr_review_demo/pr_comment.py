from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

MAX_RESULT_BYTES = 2_000_000
MAX_FINDINGS = 50
MAX_SKILLS = 20
IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,160}")
SHA256 = re.compile(r"[a-f0-9]{64}")


def render_pr_comment(
    result: Mapping[str, object],
    *,
    pull_request_number: int,
    head_sha: str,
    run_id: str,
    run_url: str,
) -> str:
    if pull_request_number < 1:
        raise ValueError("pull request number must be positive")
    if not re.fullmatch(r"[a-f0-9]{40}", head_sha):
        raise ValueError("head SHA must be lowercase hexadecimal")
    if not run_id.isdigit():
        raise ValueError("run id must be numeric")
    parsed_url = urllib.parse.urlparse(run_url)
    expected_path = f"/atlanai/software-factory-demo/actions/runs/{run_id}"
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or parsed_url.path != expected_path
    ):
        raise ValueError("run URL must identify the expected GitHub Actions run")
    decision = _string(result, "decision")
    if decision not in {"approve", "comment", "changes_requested"}:
        raise ValueError("review decision is invalid")
    findings = _sequence(result.get("findings"), "findings", MAX_FINDINGS)
    skills = _sequence(result.get("skills_used"), "skills_used", MAX_SKILLS)
    lines = [
        "<!-- software-factory-governed-review -->",
        "## Governed PR review",
        "",
        f"- Decision: **{decision}**",
        f"- Pull request: PR #{pull_request_number}",
        f"- Head commit: `{head_sha[:12]}`",
        f"- Workflow run: [{run_id}]({run_url})",
    ]
    for key, label in (
        ("agent_id", "Atlan Agent"),
        ("trace_id", "Trace"),
        ("session_id", "Session"),
        ("output_id", "Output"),
        ("daytona_sandbox_id", "Daytona sandbox"),
        ("daytona_sandbox_lifecycle", "Sandbox lifecycle"),
    ):
        value = result.get(key)
        if isinstance(value, str) and value:
            lines.append(f"- {label}: `{_identifier(value, key)}`")
    lines.extend(["", "### Skills used", ""])
    if not skills:
        lines.append("- No verified skill fingerprints were returned.")
    for raw in skills:
        skill = _object(raw, "skill")
        skill_id = _identifier(_string(skill, "id"), "skill id")
        version = _integer(skill, "version")
        digest = _string(skill, "source_digest")
        if not SHA256.fullmatch(digest):
            raise ValueError("skill source digest is invalid")
        lines.append(f"- `{skill_id}` v{version} — `{digest[:12]}`")
    lines.extend(["", "### Findings", ""])
    if not findings:
        lines.append("- No governed findings.")
    for raw in findings:
        finding = _object(raw, "finding")
        rule_id = _identifier(_string(finding, "rule_id"), "rule id")
        severity = _string(finding, "severity")
        if severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("finding severity is invalid")
        line = _integer(finding, "line")
        message = _safe_text(_string(finding, "message"))
        lines.append(f"- **{severity}** `{rule_id}` at diff line {line}: {message}")
    lines.extend(
        [
            "",
            "The comment contains sanitized review metadata only. The diff, file bodies, "
            "prompts, and credentials are not attached.",
            "",
        ]
    )
    return "\n".join(lines)


def _safe_text(value: str) -> str:
    return html.escape(value[:500], quote=False).replace("`", "\\`")


def _identifier(value: str, name: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _sequence(value: object, name: str, maximum: int) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array with at most {maximum} entries")
    raw = cast(list[object], value)
    if len(raw) > maximum:
        raise ValueError(f"{name} must be an array with at most {maximum} entries")
    return raw


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a sanitized governed-review PR comment")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_path = cast(Path, args.result)
    if result_path.stat().st_size > MAX_RESULT_BYTES:
        raise ValueError("review result exceeds the 2 MB limit")
    payload: object = json.loads(result_path.read_text(encoding="utf-8"))
    comment = render_pr_comment(
        _object(payload, "review result"),
        pull_request_number=cast(int, args.pr_number),
        head_sha=cast(str, args.head_sha),
        run_id=cast(str, args.run_id),
        run_url=cast(str, args.run_url),
    )
    output_path = cast(Path, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(comment, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
