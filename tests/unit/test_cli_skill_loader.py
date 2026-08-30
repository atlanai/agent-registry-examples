from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from registry_pr_review_demo.cli_skill_loader import AtlanCliSkillLoader, SkillCommandResult
from registry_pr_review_demo.models import Severity, SkillArtifactRef


def test_cli_skill_loader_pulls_exact_version_and_builds_fingerprint(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def runner(args: Sequence[str]) -> SkillCommandResult:
        command = tuple(args)
        commands.append(command)
        if command[1:3] == ("skill", "get"):
            return SkillCommandResult(
                0,
                json.dumps(
                    {
                        "id": "skill_demo",
                        "name": "secure-pr-review",
                        "source_digest": "source123",
                        "version_ordinal": 1,
                        "metadata": {
                            "skill_version": "0.1.0",
                            "files": [{"path": "SKILL.md", "source_digest": "skillmd123"}],
                        },
                    }
                ),
                "",
            )
        destination = Path(command[4])
        destination.mkdir(parents=True)
        (destination / "SKILL.md").write_text("# Secure PR review\n", encoding="utf-8")
        (destination / "rules.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "id": "parameterize-sql",
                            "pattern": "f[\\\"']SELECT\\b",
                            "severity": "high",
                            "message": "Use parameterized SQL.",
                            "knowledge_ids": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return SkillCommandResult(0, "", "")

    loaded = AtlanCliSkillLoader(runner=runner, temp_root=tmp_path).load(
        SkillArtifactRef("skill_demo", 1)
    )

    assert loaded.reference.source_digest == "source123"
    assert loaded.reference.semantic_version == "0.1.0"
    assert loaded.reference.skillmd_sha256 == "skillmd123"
    assert loaded.package.rules[0].severity is Severity.HIGH
    assert any("--version" in command for command in commands)
    assert all("TOKEN" not in " ".join(command) for command in commands)
    assert list(tmp_path.iterdir()) == []
