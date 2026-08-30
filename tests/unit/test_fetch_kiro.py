from __future__ import annotations

import hashlib
import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


def load_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts/fetch_kiro.py"
    spec = importlib.util.spec_from_file_location("fetch_kiro", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_verified_kiro_launcher(tmp_path: Path) -> None:
    module = load_script()
    archive = tmp_path / "kiro.zip"
    binary = b"synthetic-kiro-launcher"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("kirocli/bin/kiro-cli", binary)
    target = tmp_path / "bin/kiro-cli"

    module.extract_verified_archive(
        archive,
        target,
        archive_digest=hashlib.sha256(archive.read_bytes()).hexdigest(),
        member="kirocli/bin/kiro-cli",
        binary_digest=hashlib.sha256(binary).hexdigest(),
    )

    assert target.read_bytes() == binary
    assert target.stat().st_mode & 0o111


def test_extract_rejects_digest_mismatch(tmp_path: Path) -> None:
    module = load_script()
    archive = tmp_path / "kiro.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("kirocli/bin/kiro-cli", b"binary")

    with pytest.raises(RuntimeError, match="archive failed"):
        module.extract_verified_archive(
            archive,
            tmp_path / "kiro-cli",
            archive_digest="0" * 64,
            member="kirocli/bin/kiro-cli",
            binary_digest="1" * 64,
        )
