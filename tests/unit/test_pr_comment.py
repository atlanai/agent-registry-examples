from __future__ import annotations

import json
from pathlib import Path

import pytest

from registry_pr_review_demo.pr_comment import main, render_pr_comment


def test_pr_comment_contains_only_sanitized_receipts() -> None:
    result: dict[str, object] = {
        "decision": "changes_requested",
        "agent_id": "agent_demo",
        "trace_id": "a" * 32,
        "session_id": "session_demo",
        "output_id": "output_demo",
        "daytona_sandbox_id": "sandbox_demo",
        "daytona_sandbox_lifecycle": "deleted_after_run",
        "findings": [
            {
                "rule_id": "parameterize-sql",
                "severity": "high",
                "line": 14,
                "message": "Use <parameters> instead of `raw` SQL.",
            }
        ],
        "skills_used": [
            {
                "id": "skill_secure",
                "version": 2,
                "source_digest": "b" * 64,
            }
        ],
        "raw_prompt": "must not appear",
        "api_key": "must not appear",
    }

    comment = render_pr_comment(
        result,
        pull_request_number=42,
        head_sha="c" * 40,
        run_id="987",
        run_url="https://github.com/atlanai/software-factory-demo/actions/runs/987",
    )

    assert "<!-- software-factory-governed-review -->" in comment
    assert "PR #42" in comment
    assert "`cccccccccccc`" in comment
    assert "parameterize-sql" in comment
    assert "&lt;parameters&gt;" in comment
    assert "skill_secure" in comment
    assert "sandbox_demo" in comment
    assert "must not appear" not in comment


@pytest.mark.parametrize(
    ("decision", "head_sha"),
    [
        ("unknown", "a" * 40),
        ("approve", "not-a-sha"),
    ],
    ids=["invalid_decision", "invalid_sha"],
)
def test_pr_comment_rejects_invalid_receipts(decision: str, head_sha: str) -> None:
    with pytest.raises(ValueError):
        render_pr_comment(
            {"decision": decision, "findings": [], "skills_used": []},
            pull_request_number=42,
            head_sha=head_sha,
            run_id="987",
            run_url="https://github.com/atlanai/software-factory-demo/actions/runs/987",
        )


def test_pr_comment_cli_writes_the_sanitized_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result_path = tmp_path / "result.json"
    output_path = tmp_path / "comment.md"
    result_path.write_text(
        json.dumps({"decision": "approve", "findings": [], "skills_used": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr-comment",
            "--result",
            str(result_path),
            "--pr-number",
            "42",
            "--head-sha",
            "d" * 40,
            "--run-id",
            "987",
            "--run-url",
            "https://github.com/atlanai/software-factory-demo/actions/runs/987",
            "--output",
            str(output_path),
        ],
    )

    assert main() == 0
    comment = output_path.read_text(encoding="utf-8")
    assert "Decision: **approve**" in comment
    assert "No governed findings" in comment
