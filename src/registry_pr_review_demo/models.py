from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    COMMENT = "comment"
    CHANGES_REQUESTED = "changes_requested"


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    expected_decision: ReviewDecision
    diff: str = ""


@dataclass(frozen=True, slots=True)
class SkillFingerprint:
    name: str
    semantic_version: str
    registry_version: int
    source_digest: str
    skillmd_sha256: str


@dataclass(frozen=True, slots=True)
class SkillArtifactRef:
    id: str
    version: int
    source_digest: str | None = None
    semantic_version: str | None = None
    skillmd_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.id or self.version < 1:
            raise ValueError("A skill reference needs a non-empty id and a positive version")


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    repository: str
    pull_request_number: int
    head_sha: str
    diff: str

    def __post_init__(self) -> None:
        if not self.repository or "/" not in self.repository:
            raise ValueError("repository must use the owner/name form")
        if self.pull_request_number < 1:
            raise ValueError("pull_request_number must be positive")
        if len(self.head_sha) != 40 or any(
            char not in "0123456789abcdef" for char in self.head_sha
        ):
            raise ValueError("head_sha must be a lowercase 40-character hexadecimal commit SHA")
        if len(self.diff.encode("utf-8")) > 2_000_000:
            raise ValueError("diff exceeds the 2 MB demo limit")


@dataclass(frozen=True, slots=True)
class ReviewRule:
    id: str
    pattern: str
    severity: Severity
    message: str
    knowledge_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillPackage:
    id: str
    version: int
    name: str
    rules: tuple[ReviewRule, ...]
    source_digest: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: str
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    severity: Severity
    message: str
    line: int
    knowledge_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewProvenance:
    skill_id: str
    skill_version: int
    document_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewResult:
    decision: ReviewDecision
    findings: tuple[Finding, ...]
    provenance: ReviewProvenance
    steps: tuple[str, ...]
