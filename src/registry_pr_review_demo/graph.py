from __future__ import annotations

import operator
import re
from collections.abc import Callable, Sequence
from typing import Annotated, TypedDict, cast

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from registry_pr_review_demo.models import (
    Finding,
    KnowledgeDocument,
    ReviewDecision,
    ReviewProvenance,
    ReviewRequest,
    ReviewResult,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillPackage,
)
from registry_pr_review_demo.ports import KnowledgeSource, SkillRegistry


class ReviewState(TypedDict):
    request: ReviewRequest
    reference: SkillArtifactRef
    skill: SkillPackage | None
    documents: tuple[KnowledgeDocument, ...]
    findings: tuple[Finding, ...]
    decision: ReviewDecision | None
    document_paths: tuple[str, ...]
    steps: Annotated[list[str], operator.add]


class ReviewUpdate(TypedDict, total=False):
    skill: SkillPackage
    documents: tuple[KnowledgeDocument, ...]
    findings: tuple[Finding, ...]
    decision: ReviewDecision
    document_paths: tuple[str, ...]
    steps: list[str]


class ReviewAgent:
    """A deterministic LangGraph agent guided by a versioned Registry skill."""

    def __init__(self, *, registry: SkillRegistry, knowledge: KnowledgeSource) -> None:
        self._registry = registry
        self._knowledge = knowledge
        self._graph = self._build_graph()

    def _build_graph(
        self,
    ) -> Callable[[ReviewState, Sequence[BaseCallbackHandler] | None], ReviewState]:
        builder = StateGraph(ReviewState)
        # LangGraph 1.2.11 leaves CachePolicy's generic unresolved in these overloads.
        builder.add_node("load_skill", self._load_skill)  # pyright: ignore[reportUnknownMemberType]
        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            "load_knowledge", self._load_knowledge
        )
        builder.add_node(  # pyright: ignore[reportUnknownMemberType]
            "inspect_diff", self._inspect_diff
        )
        builder.add_node("decide", self._decide)  # pyright: ignore[reportUnknownMemberType]
        builder.add_edge(START, "load_skill")
        builder.add_edge("load_skill", "load_knowledge")
        builder.add_edge("load_knowledge", "inspect_diff")
        builder.add_edge("inspect_diff", "decide")
        builder.add_edge("decide", END)
        compiled = builder.compile()  # pyright: ignore[reportUnknownMemberType]

        def invoke(
            state: ReviewState,
            callbacks: Sequence[BaseCallbackHandler] | None,
        ) -> ReviewState:
            config: RunnableConfig | None = (
                {"callbacks": list(callbacks)} if callbacks is not None else None
            )
            result = compiled.invoke(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                state, config=config
            )
            return cast(ReviewState, result)

        return invoke

    def review(
        self,
        request: ReviewRequest,
        reference: SkillArtifactRef,
        *,
        callbacks: Sequence[BaseCallbackHandler] | None = None,
    ) -> ReviewResult:
        state = self._graph(
            {
                "request": request,
                "reference": reference,
                "skill": None,
                "documents": (),
                "findings": (),
                "decision": None,
                "document_paths": (),
                "steps": [],
            },
            callbacks,
        )
        skill = state["skill"]
        decision = state["decision"]
        if skill is None or decision is None:
            raise RuntimeError("LangGraph review finished without a skill or decision")
        return ReviewResult(
            decision=decision,
            findings=state["findings"],
            provenance=ReviewProvenance(
                skill_id=skill.id,
                skill_version=skill.version,
                document_paths=state["document_paths"],
            ),
            steps=tuple(state["steps"]),
        )

    def _load_skill(self, state: ReviewState) -> ReviewUpdate:
        reference = state["reference"]
        skill = self._registry.load_skill(reference)
        if skill.id != reference.id or skill.version != reference.version:
            raise ValueError("Registry returned a different skill id or version")
        return {"skill": skill, "steps": ["load_skill"]}

    def _load_knowledge(self, state: ReviewState) -> ReviewUpdate:
        skill = state["skill"]
        if skill is None:
            raise RuntimeError("load_knowledge ran before load_skill")
        ordered_ids = tuple(
            dict.fromkeys(
                knowledge_id for rule in skill.rules for knowledge_id in rule.knowledge_ids
            )
        )
        documents = self._knowledge.load_documents(ordered_ids)
        returned_ids = {document.id for document in documents}
        missing = tuple(
            document_id for document_id in ordered_ids if document_id not in returned_ids
        )
        if missing:
            raise ValueError(f"Knowledge source did not return required documents: {missing!r}")
        return {"documents": documents, "steps": ["load_knowledge"]}

    def _inspect_diff(self, state: ReviewState) -> ReviewUpdate:
        findings: list[Finding] = []
        compiled_rules: list[tuple[ReviewRule, re.Pattern[str]]] = []
        skill = state["skill"]
        if skill is None:
            raise RuntimeError("inspect_diff ran before load_skill")
        for rule in skill.rules:
            try:
                compiled_rules.append((rule, re.compile(rule.pattern)))
            except re.error as error:
                raise ValueError(f"Skill rule {rule.id!r} has an invalid pattern") from error

        for line_number, line in enumerate(state["request"].diff.splitlines(), start=1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for rule, pattern in compiled_rules:
                if pattern.search(line[1:]):
                    findings.append(
                        Finding(
                            rule_id=rule.id,
                            severity=rule.severity,
                            message=rule.message,
                            line=line_number,
                            knowledge_ids=rule.knowledge_ids,
                        )
                    )
        return {"findings": tuple(findings), "steps": ["inspect_diff"]}

    def _decide(self, state: ReviewState) -> ReviewUpdate:
        findings = state["findings"]
        blocking = {Severity.HIGH, Severity.CRITICAL}
        if any(finding.severity in blocking for finding in findings):
            decision = ReviewDecision.CHANGES_REQUESTED
        elif findings:
            decision = ReviewDecision.COMMENT
        else:
            decision = ReviewDecision.APPROVE

        used_ids = {knowledge_id for finding in findings for knowledge_id in finding.knowledge_ids}
        document_paths = tuple(
            document.path for document in state["documents"] if document.id in used_ids
        )
        return {
            "decision": decision,
            "document_paths": document_paths,
            "steps": ["decide"],
        }
