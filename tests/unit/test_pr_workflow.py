from __future__ import annotations

from pathlib import Path


def test_pr_workflow_is_same_repository_and_keeps_agent_key_out_of_github() -> None:
    root = Path(__file__).parents[2]
    workflow = (root / ".github/workflows/governed-pr-review.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "pull_request_target" not in workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "secrets.DAYTONA_API_KEY" in workflow
    assert "ATLAN_API_KEY" not in workflow
    assert "ATLANAI_TOKEN" not in workflow
    assert "persist-credentials: false" in workflow
    assert "pull-requests: write" in workflow
    assert "registry-pr-review run-kiro" in workflow
    assert "registry_pr_review_demo.pr_comment" in workflow
    assert "gh pr comment" in workflow
