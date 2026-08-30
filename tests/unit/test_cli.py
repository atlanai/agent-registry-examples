from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

import registry_pr_review_demo.cli as cli
from registry_pr_review_demo.cli import main
from registry_pr_review_demo.cli_skill_loader import LoadedSkill
from registry_pr_review_demo.cli_trace import CliCommandResult
from registry_pr_review_demo.models import (
    ReviewRequest,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillPackage,
)
from registry_pr_review_demo.trace_reader import TraceEvidence


def test_build_request_writes_a_valid_bounded_job(tmp_path: Path) -> None:
    diff_path = tmp_path / "change.diff"
    output_path = tmp_path / "request.json"
    diff_path.write_text("+safe = True\n", encoding="utf-8")

    exit_code = main(
        [
            "build-request",
            "--repository",
            "example/repo",
            "--pr-number",
            "12",
            "--head-sha",
            "a" * 40,
            "--diff-file",
            str(diff_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "repository": "example/repo",
        "pull_request_number": 12,
        "head_sha": "a" * 40,
        "diff": "+safe = True\n",
    }


def test_publish_skill_uses_first_class_cli_and_writes_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAN_WORKSPACE_ID", "workspace_demo")

    def run(args: Sequence[str]) -> CliCommandResult:
        if "list" in args:
            return CliCommandResult(
                0,
                json.dumps(
                    [
                        {
                            "id": "skill_demo",
                            "name": "secure-pr-review",
                            "version_ordinal": 2,
                            "source_digest": "source123",
                        }
                    ]
                ),
                "",
            )
        return CliCommandResult(0, "", "")

    monkeypatch.setattr(cli, "run_atlanai_cli", run)
    monkeypatch.setattr(cli, "AtlanCliSkillLoader", FakeSkillLoader)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    output = tmp_path / "skill-reference.json"

    exit_code = main(
        [
            "publish-skill",
            "--skill-dir",
            str(skill_dir),
            "--name",
            "secure-pr-review",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "id": "skill_demo",
        "version": 2,
        "source_digest": "source123",
        "semantic_version": "0.1.0",
        "skillmd_sha256": "skillmd123",
    }


class FakeController:
    def __init__(self, **components: object) -> None:
        assert set(components) == {"registry", "knowledge", "runtime", "traces"}

    def run(
        self,
        request: object,
        reference: object,
        *,
        evaluation: object,
        trace_mode: str,
    ) -> dict[str, object]:
        assert cast(ReviewRequest, request).repository == "example/repo"
        assert cast(SkillArtifactRef, reference).id == "skill_demo"
        assert trace_mode == "sdk"
        return {"decision": "approve", "findings": []}


class FakeRuntime:
    def __init__(self, **kwargs: object) -> None:
        assert kwargs["worker_archive"] == b"archive"


class FakeKnowledge:
    def __init__(self, root: Path) -> None:
        assert root.name == "knowledge"


def fake_build_worker_archive(_: Path) -> bytes:
    return b"archive"


class FakeSkillLoader:
    def load(self, reference: SkillArtifactRef) -> LoadedSkill:
        enriched = SkillArtifactRef(
            reference.id,
            reference.version,
            "source123",
            "0.1.0",
            "skillmd123",
        )
        return LoadedSkill(
            reference=enriched,
            package=SkillPackage(reference.id, reference.version, "secure-pr-review", ()),
        )


def test_run_wires_registry_daytona_knowledge_and_otlp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-test-token")
    monkeypatch.setattr(cli, "AtlanCliSkillLoader", FakeSkillLoader)
    monkeypatch.setattr(cli, "ReviewController", FakeController)
    monkeypatch.setattr(cli, "DaytonaRuntime", FakeRuntime)
    monkeypatch.setattr(cli, "DirectoryKnowledgeSource", FakeKnowledge)
    monkeypatch.setattr(cli, "build_worker_archive", fake_build_worker_archive)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "repository": "example/repo",
                "pull_request_number": 1,
                "head_sha": "a" * 40,
                "diff": "+safe = True",
            }
        ),
        encoding="utf-8",
    )
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps({"id": "skill_demo", "version": 1, "source_digest": None}),
        encoding="utf-8",
    )
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    output = tmp_path / "result.json"

    exit_code = main(
        [
            "run",
            "--request",
            str(request),
            "--skill-reference",
            str(reference),
            "--knowledge-root",
            str(knowledge),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (
        cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))["decision"]
        == "approve"
    )


def test_skill_publish_failure_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_: Sequence[str]) -> CliCommandResult:
        return CliCommandResult(1, "", "validation failed")

    monkeypatch.setattr(
        cli,
        "run_atlanai_cli",
        fail,
    )

    with pytest.raises(RuntimeError, match="publication failed"):
        main(
            [
                "publish-skill",
                "--skill-dir",
                str(tmp_path),
                "--name",
                "secure-pr-review",
                "--output",
                str(tmp_path / "reference.json"),
            ]
        )


class FakeTraceReader:
    def fetch_case(self, *, skill_id: str, version_ordinal: int, case_id: str) -> TraceEvidence:
        assert skill_id == "skill_demo"
        assert version_ordinal == 1
        assert case_id == "sql-format-interpolation"
        return TraceEvidence(
            trace={
                "trace_id": "a" * 32,
                "attributes": {"review.decision": "approve"},
            },
            spans=(),
        )


def test_analyze_traces_writes_proposal_without_applying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluations = tmp_path / "evaluations.json"
    diff = tmp_path / "gap.diff"
    rules = tmp_path / "rules.json"
    output_dir = tmp_path / "proposal"
    diff.write_text(
        '+query = "SELECT * FROM events WHERE id = {}".format(workspace_id)',
        encoding="utf-8",
    )
    evaluations.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "sql-format-interpolation",
                        "diff": str(diff),
                        "expected_decision": "changes_requested",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "parameterize-sql",
                        "pattern": "f[\\\"']SELECT\\b",
                        "severity": "high",
                        "message": "Use parameterized SQL.",
                        "knowledge_ids": ["data-access"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "AtlanCliTraceReader", lambda: FakeTraceReader())

    exit_code = main(
        [
            "analyze-traces",
            "--skill-id",
            "skill_demo",
            "--version",
            "1",
            "--case-id",
            "sql-format-interpolation",
            "--evaluations",
            str(evaluations),
            "--rules",
            str(rules),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    proposal = json.loads((output_dir / "proposal.json").read_text(encoding="utf-8"))
    assert proposal["kind"] == "false_negative"
    assert proposal["approved"] is False
    assert not (output_dir / "rules.json").exists()
    assert "Human approval required" in (output_dir / "proposal.md").read_text(encoding="utf-8")


def test_registry_plan_and_apply_write_redacted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path = tmp_path / "plan.json"
    state_path = tmp_path / "state.json"

    class Provisioner:
        def apply(self) -> dict[str, object]:
            return {
                "workspace_id": "workspace_data",
                "provider_id": "agent_provider_daytona",
                "agent_ids": {"registry-pr-review-sdk": "agent_sdk"},
            }

    monkeypatch.setattr(cli, "RegistryProvisioner", Provisioner)

    assert main(["registry-plan", "--output", str(plan_path)]) == 0
    assert main(["registry-apply", "--output", str(state_path)]) == 0
    assert json.loads(plan_path.read_text(encoding="utf-8"))["provider"] == "daytona"
    assert "api_key" not in state_path.read_text(encoding="utf-8")


def test_run_improver_cli_writes_proposal_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-test")
    target_ref = tmp_path / "target.json"
    analyzer_ref = tmp_path / "analyzer.json"
    evaluations = tmp_path / "evaluations.json"
    output_dir = tmp_path / "output"
    target_ref.write_text('{"id":"skill_target","version":1}', encoding="utf-8")
    analyzer_ref.write_text('{"id":"skill_analyzer","version":1}', encoding="utf-8")
    diff = tmp_path / "gap.diff"
    diff.write_text('+query = "SELECT {}".format(value)', encoding="utf-8")
    evaluations.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "sql-format-interpolation",
                        "diff": str(diff),
                        "expected_decision": "changes_requested",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class Loader:
        def load(self, reference: SkillArtifactRef) -> LoadedSkill:
            enriched = SkillArtifactRef(reference.id, 1, "source", "0.1.0", "skillmd")
            rules = (
                (
                    ReviewRule(
                        "parameterize-sql",
                        r"f[\"']SELECT\b",
                        Severity.HIGH,
                        "Use parameters.",
                    ),
                )
                if reference.id == "skill_target"
                else ()
            )
            name = (
                "secure-pr-review"
                if reference.id == "skill_target"
                else "trace-driven-skill-improvement"
            )
            return LoadedSkill(enriched, SkillPackage(reference.id, 1, name, rules))

    class Runtime:
        def __init__(self, **_: object) -> None:
            pass

        def run(self, payload: object) -> dict[str, object]:
            assert isinstance(payload, dict)
            return {
                "proposal": {"kind": "false_negative", "approved": False},
                "proposal_markdown": "# Proposal\n\nHuman approval required\n",
                "analyzer_trace_id": "b" * 32,
            }

    monkeypatch.setattr(cli, "AtlanCliSkillLoader", Loader)
    monkeypatch.setattr(cli, "DaytonaRuntime", Runtime)

    exit_code = main(
        [
            "run-improver-cli",
            "--target-skill-reference",
            str(target_ref),
            "--analyzer-skill-reference",
            str(analyzer_ref),
            "--case-id",
            "sql-format-interpolation",
            "--evaluations",
            str(evaluations),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (
        json.loads((output_dir / "proposal.json").read_text(encoding="utf-8"))["approved"] is False
    )
    assert (output_dir / "run.json").is_file()
