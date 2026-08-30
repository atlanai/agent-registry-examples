from __future__ import annotations

from typing import cast

import pytest

from registry_pr_review_demo.worker import run_job


def payload(diff: str) -> dict[str, object]:
    return {
        "request": {
            "repository": "example/platform-api",
            "pull_request_number": 42,
            "head_sha": "a" * 40,
            "diff": diff,
        },
        "skill": {
            "id": "skill_demo",
            "version": 3,
            "name": "secure-pr-review",
            "rules": [
                {
                    "id": "no-dynamic-eval",
                    "pattern": r"\beval\s*\(",
                    "severity": "high",
                    "message": "Do not execute dynamically supplied code.",
                    "knowledge_ids": ["secure-coding"],
                }
            ],
        },
        "documents": [
            {
                "id": "secure-coding",
                "path": "knowledge/secure-coding.md",
                "content": "Never use eval.",
            }
        ],
    }


@pytest.mark.parametrize(
    ("diff", "decision", "finding_count", "document_paths"),
    [
        (
            "+result = eval(user_input)",
            "changes_requested",
            1,
            ["knowledge/secure-coding.md"],
        ),
        ("+return service.find(user_id)", "approve", 0, []),
    ],
    ids=["blocking", "clean"],
)
def test_worker_runs_the_review_as_a_langgraph(
    diff: str,
    decision: str,
    finding_count: int,
    document_paths: list[str],
) -> None:
    result = run_job(payload(diff))

    assert result["decision"] == decision
    findings = result["findings"]
    assert isinstance(findings, list)
    assert len(cast(list[object], findings)) == finding_count
    assert result["provenance"] == {
        "skill_id": "skill_demo",
        "skill_version": 3,
        "document_paths": document_paths,
    }
    assert result["steps"] == ["load_context", "inspect_diff", "decide"]


def test_worker_rejects_an_invalid_payload_without_executing_content() -> None:
    with pytest.raises(ValueError, match="request"):
        run_job({"request": "not-an-object"})
