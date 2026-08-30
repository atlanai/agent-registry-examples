from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from registry_pr_review_demo.models import KnowledgeDocument

MAX_DOCUMENT_BYTES = 1_000_000


class DirectoryKnowledgeSource:
    """Loads an allowlisted set of documents from a Git-managed directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        index_path = self._root / "index.json"
        try:
            loaded: object = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Knowledge root must contain a valid index.json") from error
        if not isinstance(loaded, dict):
            raise ValueError("Knowledge index must contain a documents object")
        raw_index = cast(dict[str, object], loaded)
        raw_documents = raw_index.get("documents")
        if not isinstance(raw_documents, dict):
            raise ValueError("Knowledge index must contain a documents object")
        documents = cast(dict[object, object], raw_documents)
        if not all(
            isinstance(key, str) and isinstance(value, str) for key, value in documents.items()
        ):
            raise ValueError("Knowledge index keys and paths must be strings")
        self._documents = cast(dict[str, str], documents)

    def load_documents(self, document_ids: tuple[str, ...]) -> tuple[KnowledgeDocument, ...]:
        documents: list[KnowledgeDocument] = []
        for document_id in document_ids:
            relative = self._documents.get(document_id)
            if relative is None:
                raise ValueError(f"Knowledge document {document_id!r} is not declared")
            candidate = (self._root / relative).resolve()
            if not candidate.is_relative_to(self._root):
                raise ValueError("Knowledge documents must stay inside the knowledge root")
            try:
                size = candidate.stat().st_size
                content = candidate.read_text(encoding="utf-8")
            except OSError as error:
                raise ValueError(f"Knowledge document {document_id!r} is unavailable") from error
            if size > MAX_DOCUMENT_BYTES:
                raise ValueError(f"Knowledge document {document_id!r} exceeds the 1 MB limit")
            documents.append(KnowledgeDocument(id=document_id, path=relative, content=content))
        return tuple(documents)
