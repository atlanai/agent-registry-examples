from __future__ import annotations

from typing import Protocol

from registry_pr_review_demo.models import KnowledgeDocument, SkillArtifactRef, SkillPackage


class SkillRegistry(Protocol):
    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage: ...


class KnowledgeSource(Protocol):
    def load_documents(self, document_ids: tuple[str, ...]) -> tuple[KnowledgeDocument, ...]: ...
