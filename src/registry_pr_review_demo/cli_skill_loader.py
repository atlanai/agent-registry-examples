from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from registry_pr_review_demo.models import SkillArtifactRef, SkillPackage
from registry_pr_review_demo.trace_analysis import load_rules


@dataclass(frozen=True, slots=True)
class SkillCommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    reference: SkillArtifactRef
    package: SkillPackage


def _default_runner(args: Sequence[str]) -> SkillCommandResult:
    executable = shutil.which("atlanai")
    if executable is None or not args or args[0] != "atlanai":
        raise RuntimeError("atlanai CLI is unavailable")
    command = (executable, *args[1:])
    completed = subprocess.run(  # noqa: S603 - fixed executable, no shell
        command, check=False, capture_output=True, text=True
    )
    return SkillCommandResult(completed.returncode, completed.stdout, completed.stderr)


class AtlanCliSkillLoader:
    def __init__(
        self,
        *,
        runner: Callable[[Sequence[str]], SkillCommandResult] = _default_runner,
        temp_root: Path | None = None,
    ) -> None:
        self._runner = runner
        self._temp_root = temp_root

    def load(self, reference: SkillArtifactRef) -> LoadedSkill:
        detail = self._command_json(
            (
                "atlanai",
                "skill",
                "get",
                reference.id,
                "--version",
                str(reference.version),
                "--json",
                "id,name,source_digest,version_ordinal,metadata",
                "--jq",
                ".",
            )
        )
        if _integer(detail, "version_ordinal") != reference.version:
            raise RuntimeError("Registry returned a different skill version")
        metadata = _mapping(detail.get("metadata"), "metadata")
        raw_semantic_version = metadata.get("skill_version")
        source_digest = _string(detail, "source_digest")
        skillmd_sha256 = _skillmd_digest(metadata)
        temp_dir = Path(tempfile.mkdtemp(prefix="registry-skill-", dir=self._temp_root))
        destination = temp_dir / "skill"
        try:
            result = self._runner(
                (
                    "atlanai",
                    "skill",
                    "pull",
                    reference.id,
                    str(destination),
                    "--version",
                    str(reference.version),
                )
            )
            if result.exit_code != 0:
                raise RuntimeError("atlanai skill pull failed")
            rules = load_rules(destination / "rules.json")
            semantic_version = (
                raw_semantic_version
                if isinstance(raw_semantic_version, str) and raw_semantic_version
                else _manifest_version(destination / "rules.json")
            )
            resolved_reference = SkillArtifactRef(
                reference.id,
                reference.version,
                source_digest,
                semantic_version,
                skillmd_sha256,
            )
            package = SkillPackage(
                id=reference.id,
                version=reference.version,
                name=_string(detail, "name"),
                rules=rules,
                source_digest=source_digest,
            )
            return LoadedSkill(reference=resolved_reference, package=package)
        finally:
            shutil.rmtree(temp_dir)

    def _command_json(self, args: Sequence[str]) -> dict[str, object]:
        result = self._runner(args)
        if result.exit_code != 0:
            raise RuntimeError("atlanai skill get failed")
        try:
            payload: object = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("atlanai skill get returned invalid JSON") from error
        return _mapping(payload, "skill")


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise RuntimeError(f"Registry skill is missing {key}")
    return item


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise RuntimeError(f"Registry skill is missing {key}")
    return item


def _skillmd_digest(metadata: Mapping[str, object]) -> str:
    files = metadata.get("files")
    if not isinstance(files, list):
        raise RuntimeError("Registry skill metadata is missing files")
    for raw in cast(list[object], files):
        file = _mapping(raw, "file")
        if file.get("path") == "SKILL.md":
            return _string(file, "source_digest")
    raise RuntimeError("Registry skill metadata is missing the SKILL.md digest")


def _manifest_version(path: Path) -> str:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("rules.json must be an object")
    version = cast(dict[str, object], payload).get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("skill version is missing from Registry metadata and rules.json")
    return version
