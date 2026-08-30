from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

import atlan_ai
from atlan_ai.client import AtlanAI
from atlan_ai.langchain import CallbackHandler

from registry_pr_review_demo.agent_evidence import AgentEvidenceClient
from registry_pr_review_demo.cli_trace import (
    CliTraceReceipt,
    CliTraceSubmitter,
    KiroCliTraceRecord,
    KiroCliTraceSubmitter,
)
from registry_pr_review_demo.graph import ReviewAgent
from registry_pr_review_demo.improver import ImprovementAgent, TraceReader, TraceSubmitter
from registry_pr_review_demo.models import (
    EvaluationCase,
    KnowledgeDocument,
    ReviewDecision,
    ReviewRequest,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillFingerprint,
    SkillPackage,
)
from registry_pr_review_demo.registration import DATA_WORKSPACE_ID
from registry_pr_review_demo.sdk_trace import SdkReviewTracer
from registry_pr_review_demo.trace_reader import AtlanCliTraceReader

MAX_JOB_BYTES = 4_000_000


class KiroTraceSubmitter(Protocol):
    def submit(self, record: KiroCliTraceRecord) -> CliTraceReceipt: ...


class EmbeddedRegistry:
    def __init__(self, package: SkillPackage) -> None:
        self._package = package

    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage:
        if reference.id != self._package.id or reference.version != self._package.version:
            raise ValueError("Embedded skill reference does not match the governed package")
        return self._package


class EmbeddedKnowledge:
    def __init__(self, documents: tuple[KnowledgeDocument, ...]) -> None:
        self._documents = {document.id: document for document in documents}

    def load_documents(self, document_ids: tuple[str, ...]) -> tuple[KnowledgeDocument, ...]:
        try:
            return tuple(self._documents[document_id] for document_id in document_ids)
        except KeyError as error:
            raise ValueError("The Daytona job is missing a required knowledge document") from error


def run_job(raw_payload: Mapping[str, object]) -> dict[str, object]:
    request, package, documents, reference, _, _ = _parse_job(raw_payload)
    result = ReviewAgent(
        registry=EmbeddedRegistry(package),
        knowledge=EmbeddedKnowledge(documents),
    ).review(request, reference)
    return _result_dict(result)


def run_sdk_job(raw_payload: Mapping[str, object], *, client: AtlanAI) -> dict[str, object]:
    request, package, documents, reference, fingerprint, evaluation = _parse_job(raw_payload)
    if fingerprint is None or evaluation is None:
        raise ValueError("SDK trace mode requires skill fingerprint and evaluation metadata")
    agent = ReviewAgent(
        registry=EmbeddedRegistry(package),
        knowledge=EmbeddedKnowledge(documents),
    )
    tracer = SdkReviewTracer(client)
    with tracer.review(request, fingerprint, evaluation) as trace_run:
        result = agent.review(request, reference, callbacks=[CallbackHandler()])
        trace_run.complete(result)
    payload = _result_dict(result)
    payload["trace_id"] = trace_run.trace_id
    return payload


def run_improver_job(
    raw_payload: Mapping[str, object],
    *,
    reader: TraceReader | None = None,
    submitter: TraceSubmitter | None = None,
) -> dict[str, object]:
    target_data = _mapping(raw_payload.get("target_skill"), "target_skill")
    analyzer_data = _mapping(raw_payload.get("analyzer_skill"), "analyzer_skill")
    evaluation_data = _mapping(raw_payload.get("evaluation"), "evaluation")
    rules_data = _sequence(raw_payload.get("rules"), "rules")
    target = SkillArtifactRef(
        _string(target_data, "id"),
        _integer(target_data, "version"),
    )
    analyzer_fingerprint = SkillFingerprint(
        name=_string(analyzer_data, "name"),
        semantic_version=_string(analyzer_data, "semantic_version"),
        registry_version=_integer(analyzer_data, "registry_version"),
        source_digest=_string(analyzer_data, "source_digest"),
        skillmd_sha256=_string(analyzer_data, "skillmd_sha256"),
    )
    evaluation = EvaluationCase(
        id=_string(evaluation_data, "id"),
        expected_decision=_decision(evaluation_data),
        diff=_string(evaluation_data, "diff"),
    )
    rules = tuple(_rule(_mapping(item, "rule")) for item in rules_data)
    agent = ImprovementAgent(
        reader=reader or AtlanCliTraceReader(),
        submitter=submitter or CliTraceSubmitter(workspace_id=DATA_WORKSPACE_ID),
    )
    result = agent.run(
        target=target,
        analyzer_fingerprint=analyzer_fingerprint,
        evaluation=evaluation,
        rules=rules,
    )
    return {
        "proposal": result.proposal.as_dict(),
        "proposal_markdown": result.proposal.to_markdown(),
        "analyzer_trace_id": result.analyzer_trace_id,
    }


def run_kiro_trace_job(
    raw_payload: Mapping[str, object],
    *,
    submitter: KiroTraceSubmitter | None = None,
) -> dict[str, object]:
    if not os.environ.get("ATLAN_API_KEY") or not os.environ.get("ATLANAI_TOKEN"):
        raise RuntimeError("Kiro trace mode requires Agent credentials for REST and CLI")
    result = _mapping(raw_payload.get("result"), "result")
    tool_names = tuple(
        _string_value(item, "tool name")
        for item in _sequence(raw_payload.get("tool_names", []), "tool_names")
    )
    if any(name not in {"read", "grep"} for name in tool_names):
        raise ValueError("Kiro trace contains a disallowed tool")
    configured: list[tuple[str, SkillFingerprint]] = []
    for raw in _sequence(raw_payload.get("skills"), "skills"):
        skill = _mapping(raw, "skill")
        configured.append(
            (
                _string(skill, "id"),
                SkillFingerprint(
                    name=_string(skill, "name"),
                    semantic_version=_string(skill, "semantic_version"),
                    registry_version=_integer(skill, "version"),
                    source_digest=_string(skill, "source_digest"),
                    skillmd_sha256=_string(skill, "skillmd_sha256"),
                ),
            )
        )
    observed = {
        (
            _string(_mapping(item, "skills_used item"), "id"),
            _integer(_mapping(item, "skills_used item"), "version"),
            _string(_mapping(item, "skills_used item"), "source_digest"),
        )
        for item in _sequence(result.get("skills_used"), "skills_used")
    }
    expected = {
        (skill_id, fingerprint.registry_version, fingerprint.source_digest)
        for skill_id, fingerprint in configured
    }
    if observed != expected:
        raise ValueError("Kiro reported different skill fingerprints than the configured run")
    raw_attributes = _mapping(raw_payload.get("attributes", {}), "attributes")
    allowed_attribute_names = {
        "github.repository",
        "github.run_id",
        "git.commit.sha",
        "daytona.sandbox.id",
        "review.case_id",
    }
    attributes = {
        key: _string_value(value, key)
        for key, value in raw_attributes.items()
        if key in allowed_attribute_names
    }
    findings = _sequence(result.get("findings"), "findings")
    receipt = (submitter or KiroCliTraceSubmitter(workspace_id=DATA_WORKSPACE_ID)).submit(
        KiroCliTraceRecord(
            session_id=_string(raw_payload, "session_id"),
            agent_id=_string(raw_payload, "agent_id"),
            skills=tuple(configured),
            attributes=attributes,
            decision=_string(result, "decision"),
            finding_count=len(findings),
            tool_names=tool_names,
        )
    )
    if not receipt.accepted:
        raise RuntimeError("Kiro CLI REST trace was not accepted")
    output = dict(result)
    output["trace_id"] = receipt.trace_id
    return output


def _parse_job(
    raw_payload: Mapping[str, object],
) -> tuple[
    ReviewRequest,
    SkillPackage,
    tuple[KnowledgeDocument, ...],
    SkillArtifactRef,
    SkillFingerprint | None,
    EvaluationCase | None,
]:
    request_data = _mapping(raw_payload.get("request"), "request")
    skill_data = _mapping(raw_payload.get("skill"), "skill")
    document_data = _sequence(raw_payload.get("documents"), "documents")

    request = ReviewRequest(
        repository=_string(request_data, "repository"),
        pull_request_number=_integer(request_data, "pull_request_number"),
        head_sha=_string(request_data, "head_sha"),
        diff=_string(request_data, "diff"),
    )
    skill_id = _string(skill_data, "id")
    skill_version = _integer(skill_data, "version")
    rules_data = _sequence(skill_data.get("rules"), "skill.rules")
    rules = tuple(_rule(_mapping(item, "skill rule")) for item in rules_data)
    package = SkillPackage(
        id=skill_id,
        version=skill_version,
        name=_string(skill_data, "name"),
        rules=rules,
        source_digest=_optional_string(skill_data, "source_digest"),
    )
    documents = tuple(_document(_mapping(item, "document")) for item in document_data)
    reference = SkillArtifactRef(skill_id, skill_version)
    fingerprint = _fingerprint(skill_data, skill_version)
    raw_evaluation = raw_payload.get("evaluation")
    evaluation = (
        _evaluation(_mapping(raw_evaluation, "evaluation")) if raw_evaluation is not None else None
    )
    return request, package, documents, reference, fingerprint, evaluation


def _result_dict(result: object) -> dict[str, object]:
    from registry_pr_review_demo.models import ReviewResult

    if not isinstance(result, ReviewResult):
        raise TypeError("review result has an unexpected type")
    return {
        "decision": result.decision.value,
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity.value,
                "message": finding.message,
                "line": finding.line,
                "knowledge_ids": list(finding.knowledge_ids),
            }
            for finding in result.findings
        ],
        "provenance": {
            "skill_id": result.provenance.skill_id,
            "skill_version": result.provenance.skill_version,
            "document_paths": list(result.provenance.document_paths),
        },
        "steps": ["load_context", "inspect_diff", "decide"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a governed PR review job")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.request.stat().st_size > MAX_JOB_BYTES:
        raise ValueError("Daytona job exceeds the 4 MB limit")
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Daytona job must be a JSON object")
    typed_payload = cast(dict[str, object], payload)
    if typed_payload.get("job_type") == "improve":
        result = run_improver_job(typed_payload)
    elif typed_payload.get("job_type") == "kiro_trace":
        result = run_kiro_trace_job(typed_payload)
        attributes = _mapping(typed_payload.get("attributes", {}), "attributes")
        result_model = result.get("model")
        model_id = result_model if isinstance(result_model, str) else None
        session_id, output_id = AgentEvidenceClient.from_environment().record_and_verify(
            agent_id=_string(typed_payload, "agent_id"),
            provider_id=_string(typed_payload, "provider_id"),
            environment_id=_string(typed_payload, "environment_id"),
            external_session_id=_string(typed_payload, "session_id"),
            sandbox_id=_string(attributes, "daytona.sandbox.id"),
            trace_id=_string(result, "trace_id"),
            skill_ids=[
                _string(_mapping(raw, "skill"), "id")
                for raw in _sequence(typed_payload.get("skills"), "skills")
            ],
            output_url=_string(typed_payload, "output_url"),
            model_id=model_id,
            decision=_string(result, "decision"),
        )
        result["session_id"] = session_id
        result["output_id"] = output_id
    elif typed_payload.get("trace_mode") == "sdk":
        client = atlan_ai.init(
            service_name="registry-pr-review-sdk",
            trace_content=False,
        )
        try:
            result = run_sdk_job(typed_payload, client=client)
            client.flush()
        finally:
            client.shutdown()
    else:
        result = run_job(typed_payload)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    raw = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"{name} keys must be strings")
        result[key] = item
    return result


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return cast(list[object], value)


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_string(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _string_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _fingerprint(
    skill_data: Mapping[str, object], registry_version: int
) -> SkillFingerprint | None:
    keys = ("semantic_version", "source_digest", "skillmd_sha256")
    if not any(skill_data.get(key) is not None for key in keys):
        return None
    return SkillFingerprint(
        name=_string(skill_data, "name"),
        semantic_version=_string(skill_data, "semantic_version"),
        registry_version=registry_version,
        source_digest=_string(skill_data, "source_digest"),
        skillmd_sha256=_string(skill_data, "skillmd_sha256"),
    )


def _evaluation(data: Mapping[str, object]) -> EvaluationCase:
    from registry_pr_review_demo.models import ReviewDecision

    return EvaluationCase(
        id=_string(data, "id"),
        expected_decision=ReviewDecision(_string(data, "expected_decision")),
    )


def _decision(data: Mapping[str, object]) -> ReviewDecision:
    return ReviewDecision(_string(data, "expected_decision"))


def _rule(data: Mapping[str, object]) -> ReviewRule:
    knowledge = _sequence(data.get("knowledge_ids", []), "knowledge_ids")
    if not all(isinstance(value, str) for value in knowledge):
        raise ValueError("knowledge_ids must contain strings")
    return ReviewRule(
        id=_string(data, "id"),
        pattern=_string(data, "pattern"),
        severity=Severity(_string(data, "severity")),
        message=_string(data, "message"),
        knowledge_ids=tuple(cast(Sequence[str], knowledge)),
    )


def _document(data: Mapping[str, object]) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=_string(data, "id"),
        path=_string(data, "path"),
        content=_string(data, "content"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
