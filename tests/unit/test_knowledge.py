from __future__ import annotations

import json
from pathlib import Path

import pytest

from registry_pr_review_demo.knowledge import DirectoryKnowledgeSource


def test_directory_knowledge_source_loads_only_declared_documents(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "secure.md").write_text("Never execute input.", encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps({"documents": {"secure-coding": "docs/secure.md"}}),
        encoding="utf-8",
    )
    source = DirectoryKnowledgeSource(tmp_path)

    documents = source.load_documents(("secure-coding",))

    assert documents[0].id == "secure-coding"
    assert documents[0].path == "docs/secure.md"
    assert documents[0].content == "Never execute input."


def test_directory_knowledge_source_rejects_paths_outside_the_root(tmp_path: Path) -> None:
    (tmp_path / "index.json").write_text(
        json.dumps({"documents": {"escape": "../outside.md"}}),
        encoding="utf-8",
    )
    source = DirectoryKnowledgeSource(tmp_path)

    with pytest.raises(ValueError, match="inside the knowledge root"):
        source.load_documents(("escape",))
