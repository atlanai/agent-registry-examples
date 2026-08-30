from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import registry_pr_review_demo.factory_review as factory_review
from registry_pr_review_demo.cli_trace import (
    CliTraceReceipt,
    CliTraceRecord,
)
from registry_pr_review_demo.factory_review import main, run_factory_review


def test_factory_review_uses_the_registry_skill_and_keeps_patch_as_evidence(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    output = tmp_path / "review.json"
    summary = tmp_path / "review.md"

    result = run_factory_review(
        root=root,
        diff_path=root / "factory/fixtures/risky-order-change.diff",
        output_path=output,
        summary_path=summary,
    )

    assert result["decision"] == "changes_requested"
    findings = cast(list[dict[str, object]], result["findings"])
    assert {finding["rule_id"] for finding in findings} == {
        "no-dynamic-eval",
        "parameterize-sql",
    }
    assert result["trace_status"] == "not_configured"
    assert "eval(customer_filter)" not in output.read_text(encoding="utf-8")
    assert "proposed patch is review evidence only" in summary.read_text(encoding="utf-8")


def test_factory_review_writes_machine_readable_output(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    output = tmp_path / "review.json"
    summary = tmp_path / "review.md"

    run_factory_review(
        root=root,
        diff_path=root / "factory/fixtures/risky-order-change.diff",
        output_path=output,
        summary_path=summary,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provenance"]["skill_id"] == "skill_01m11gr8cjekhb5gvqn0k4x1ny"


def test_factory_review_submits_trace_when_ci_credential_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeSubmitter:
        def __init__(self, *, workspace_id: str) -> None:
            assert workspace_id.startswith("workspace_")

        def submit(self, record: CliTraceRecord) -> CliTraceReceipt:
            assert record.fingerprint.name == "secure-pr-review"
            assert set(record.matched_rule_ids) == {"no-dynamic-eval", "parameterize-sql"}
            return CliTraceReceipt(accepted=True, trace_id="b" * 32)

    root = Path(__file__).parents[2]
    monkeypatch.setenv("ATLANAI_TOKEN", "configured-for-test")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(factory_review, "CliTraceSubmitter", FakeSubmitter)

    result = run_factory_review(
        root=root,
        diff_path=root / "factory/fixtures/risky-order-change.diff",
        output_path=tmp_path / "review.json",
        summary_path=tmp_path / "review.md",
        submit_trace_if_configured=True,
    )

    assert result["trace_id"] == "b" * 32
    assert result["trace_status"] == "submitted"


def test_factory_review_command_entrypoint(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    output = tmp_path / "review.json"
    summary = tmp_path / "review.md"

    exit_code = main(
        [
            "--root",
            str(root),
            "--diff",
            str(root / "factory/fixtures/risky-order-change.diff"),
            "--output",
            str(output),
            "--summary",
            str(summary),
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    assert summary.is_file()
