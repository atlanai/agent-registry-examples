from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from registry_pr_review_demo.models import (
    EvaluationCase,
    ReviewDecision,
    ReviewRule,
    Severity,
    SkillPackage,
)

SQL_FORMAT_PATTERN = r"(?:f[\"']SELECT\b|[\"']SELECT[^\"']*[\"']\.format\s*\()"


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    kind: str
    trace_id: str
    rule_id: str | None = None
    before_pattern: str | None = None
    after_pattern: str | None = None
    rationale: str = ""
    approved: bool = False

    def with_approval(self) -> ImprovementProposal:
        return replace(self, approved=True)

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "trace_id": self.trace_id,
            "rule_id": self.rule_id,
            "before_pattern": self.before_pattern,
            "after_pattern": self.after_pattern,
            "rationale": self.rationale,
            "approved": self.approved,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Trace-driven skill improvement proposal",
            "",
            f"- Classification: `{self.kind}`",
            f"- Evidence trace: `{self.trace_id}`",
            f"- Target rule: `{self.rule_id or 'none'}`",
            "- Status: **Human approval required**",
            "",
            "## Evidence",
            "",
            self.rationale
            or "The trace matches the checked-in expectation; no change is proposed.",
        ]
        if self.after_pattern is not None:
            lines.extend(
                [
                    "",
                    "## Candidate patch",
                    "",
                    "```text",
                    f"before: {self.before_pattern}",
                    f"after:  {self.after_pattern}",
                    "```",
                ]
            )
        return "\n".join(lines) + "\n"


def analyze_trace_gap(
    *,
    trace: Mapping[str, object],
    evaluation: EvaluationCase,
    rules: tuple[ReviewRule, ...],
) -> ImprovementProposal:
    trace_id = trace.get("trace_id")
    if not isinstance(trace_id, str):
        raise ValueError("trace evidence must contain a trace_id")
    raw_attributes = trace.get("attributes")
    attributes = cast(dict[str, object], raw_attributes) if isinstance(raw_attributes, dict) else {}
    actual = attributes.get("review.decision")
    if actual == evaluation.expected_decision.value:
        return ImprovementProposal(kind="no_change", trace_id=trace_id)
    if (
        evaluation.expected_decision is ReviewDecision.CHANGES_REQUESTED
        and actual == ReviewDecision.APPROVE.value
        and "SELECT" in evaluation.diff
        and ".format" in evaluation.diff
    ):
        rule = next((item for item in rules if item.id == "parameterize-sql"), None)
        if rule is None:
            raise ValueError("false negative cannot be mapped to parameterize-sql")
        return ImprovementProposal(
            kind="false_negative",
            trace_id=trace_id,
            rule_id=rule.id,
            before_pattern=rule.pattern,
            after_pattern=SQL_FORMAT_PATTERN,
            rationale=(
                "The versioned trace approved a SQL string built with .format(), while the "
                "evaluation expected changes_requested. Broaden the existing SQL rule."
            ),
        )
    return ImprovementProposal(
        kind="unresolved",
        trace_id=trace_id,
        rationale=(
            "Observed and expected decisions differ, but no bounded rule change is supported."
        ),
    )


def apply_approved_proposal(
    package: SkillPackage,
    proposal: ImprovementProposal,
    *,
    version: int,
) -> SkillPackage:
    if not proposal.approved:
        raise ValueError("proposal requires human approval before application")
    if proposal.rule_id is None or proposal.after_pattern is None:
        raise ValueError("approved proposal does not contain a rule patch")
    found = False
    rules: list[ReviewRule] = []
    for rule in package.rules:
        if rule.id == proposal.rule_id:
            rules.append(replace(rule, pattern=proposal.after_pattern))
            found = True
        else:
            rules.append(rule)
    if not found:
        raise ValueError("proposal target rule is missing")
    return SkillPackage(
        id=package.id,
        version=version,
        name=package.name,
        rules=tuple(rules),
        source_digest=None,
    )


def load_evaluation(path: Path, case_id: str) -> EvaluationCase:
    payload = _json_object(path)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("evaluation manifest must contain a cases array")
    for raw in cast(list[object], raw_cases):
        if not isinstance(raw, dict):
            continue
        case = cast(dict[str, object], raw)
        if case.get("id") != case_id:
            continue
        expected = case.get("expected_decision")
        diff_value = case.get("diff")
        if not isinstance(expected, str) or not isinstance(diff_value, str):
            raise ValueError("evaluation case requires expected_decision and diff")
        diff_path = Path(diff_value)
        if not diff_path.is_absolute():
            candidates = (Path.cwd() / diff_path, path.parent / diff_path)
            diff_path = next(
                (candidate for candidate in candidates if candidate.is_file()), candidates[0]
            )
        return EvaluationCase(
            id=case_id,
            expected_decision=ReviewDecision(expected),
            diff=diff_path.read_text(encoding="utf-8"),
        )
    raise LookupError(f"evaluation case {case_id!r} is not declared")


def load_rules(path: Path) -> tuple[ReviewRule, ...]:
    payload = _json_object(path)
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("rules file must contain a rules array")
    rules: list[ReviewRule] = []
    for raw in cast(list[object], raw_rules):
        if not isinstance(raw, dict):
            raise ValueError("each rule must be an object")
        rule = cast(dict[str, object], raw)
        rule_id = rule.get("id")
        pattern = rule.get("pattern")
        severity = rule.get("severity")
        message = rule.get("message")
        knowledge = rule.get("knowledge_ids", [])
        if not all(isinstance(value, str) for value in (rule_id, pattern, severity, message)):
            raise ValueError("rule id, pattern, severity, and message must be strings")
        if not isinstance(knowledge, list):
            raise ValueError("knowledge_ids must be a string array")
        knowledge_values = cast(list[object], knowledge)
        if not all(isinstance(value, str) for value in knowledge_values):
            raise ValueError("knowledge_ids must be a string array")
        rules.append(
            ReviewRule(
                id=cast(str, rule_id),
                pattern=cast(str, pattern),
                severity=Severity(cast(str, severity)),
                message=cast(str, message),
                knowledge_ids=tuple(cast(str, value) for value in knowledge_values),
            )
        )
    return tuple(rules)


def _json_object(path: Path) -> dict[str, object]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    raw = cast(dict[object, object], payload)
    return {str(key): value for key, value in raw.items()}
