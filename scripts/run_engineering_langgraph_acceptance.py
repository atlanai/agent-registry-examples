#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from daytona import Daytona, DaytonaConfig

from registry_pr_review_demo.controller import ReviewController
from registry_pr_review_demo.daytona_runtime import DaytonaRuntime
from registry_pr_review_demo.knowledge import DirectoryKnowledgeSource
from registry_pr_review_demo.models import (
    ReviewRequest,
    ReviewRule,
    Severity,
    SkillArtifactRef,
    SkillPackage,
)
from registry_pr_review_demo.ports import SkillRegistry
from registry_pr_review_demo.trace_analysis import load_evaluation
from registry_pr_review_demo.worker_bundle import build_worker_archive

ROOT = Path(__file__).resolve().parents[1]
DAYTONA_CONFIG = Path.home() / "Library/Application Support/daytona/config.json"
WORKSPACE_ID = "workspace_01m1dtasngfk08s4xydm62ewdw"
AGENT_ID = "agent_01m1q17jwzfv8b6fmg75x08z0g"
PROVIDER_ID = "agent_provider_01m1pn17zyfxgtdde2mwwwff4w"
ENVIRONMENT_ID = "agent_environment_01m1q154b9fy0rtmyzgpd0mxtx"
VISITOR_ID = "visitor_01m1prfbcqe0raj9mfqq88mwyd"
SANDBOX_NAME = "engineering-langgraph-pr-review-live-20260904"


class FixedSkillRegistry(SkillRegistry):
    def __init__(self, package: SkillPackage) -> None:
        self._package = package

    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage:
        if reference.id != self._package.id or reference.version != self._package.version:
            raise ValueError("Requested Skill does not match the verified package")
        return self._package


class NoopTraceRecorder:
    def record(
        self, _request: ReviewRequest, _skill: SkillPackage, _result: dict[str, object]
    ) -> None:
        return None


def _daytona() -> Daytona:
    raw = json.loads(DAYTONA_CONFIG.read_text(encoding="utf-8"))
    profile = next(item for item in raw["profiles"] if item["id"] == raw["activeProfile"])
    return Daytona(
        DaytonaConfig(
            jwt_token=profile["api"]["token"]["accessToken"],
            organization_id=profile["activeOrganizationId"],
        )
    )


def _skills() -> list[dict[str, object]]:
    references = json.loads(
        (ROOT / "registry/engineering-skill-references.json").read_text(encoding="utf-8")
    )
    configured: list[dict[str, object]] = []
    for name in ("secure-pr-review", "test-impact-analysis", "review-evidence-summary"):
        fingerprint = references[name]
        skillmd = ROOT / f"skills/{name}/SKILL.md"
        if hashlib.sha256(skillmd.read_bytes()).hexdigest() != fingerprint["skillmd_sha256"]:
            raise RuntimeError(f"Local Skill digest drifted for {name}")
        configured.append({"name": name, **fingerprint})
    return configured


def _package(primary: dict[str, object]) -> SkillPackage:
    raw_rules = json.loads(
        (ROOT / "skills/secure-pr-review/rules.json").read_text(encoding="utf-8")
    )["rules"]
    rules = tuple(
        ReviewRule(
            id=item["id"],
            pattern=item["pattern"],
            severity=Severity(item["severity"]),
            message=item["message"],
            knowledge_ids=tuple(item["knowledge_ids"]),
        )
        for item in raw_rules
    )
    return SkillPackage(
        id=str(primary["id"]),
        version=int(primary["version"]),
        name="secure-pr-review",
        rules=rules,
        source_digest=str(primary["source_digest"]),
    )


def main() -> int:
    skills = _skills()
    primary = skills[0]
    package = _package(primary)
    reference = SkillArtifactRef(
        id=package.id,
        version=package.version,
        source_digest=str(primary["source_digest"]),
        semantic_version=str(primary["semantic_version"]),
        skillmd_sha256=str(primary["skillmd_sha256"]),
    )
    request = ReviewRequest(
        repository="atlanai/software-factory-demo",
        pull_request_number=1,
        head_sha="a9120100c2e4580c43e96c58123a32ff3827cbf8",
        diff=(ROOT / "examples/sql-format-gap.diff").read_text(encoding="utf-8"),
    )
    evaluation = load_evaluation(ROOT / "examples/evaluations.json", "sql-format-interpolation")
    client = _daytona()
    runtime = DaytonaRuntime(
        client_factory=lambda: client,
        worker_archive=build_worker_archive(ROOT / "src/registry_pr_review_demo"),
        sdk_wheel=ROOT / "vendor/atlan-ai/atlan_ai-0.1.0-py3-none-any.whl",
        cli_binary=ROOT / "vendor/atlanai/atlanai-linux-amd64",
        allowed_domains=("agentgateway.atlan.engineering",),
        secrets={
            "ATLAN_API_KEY": "engineering-langgraph-pr-review-agent-key",
            "ATLANAI_TOKEN": "engineering-langgraph-pr-review-agent-key",
        },
        env_vars={
            "ATLAN_WORKSPACE_ID": WORKSPACE_ID,
            "ATLAN_BASE_URL": "https://agentgateway.atlan.engineering",
            "ATLANAI_GATEWAY_URL": "https://agentgateway.atlan.engineering",
            "ATLAN_TRACE_CONTENT": "true",
        },
        payload_overrides={
            "skills": skills,
            "agent_evidence": {
                "agent_id": AGENT_ID,
                "provider_id": PROVIDER_ID,
                "environment_id": ENVIRONMENT_ID,
                "external_session_id": "engineering-langgraph-live-20260904-1",
                "output_url": "https://github.com/atlanai/software-factory-demo",
                "visitor_id": VISITOR_ID,
            },
            "attributes": {
                "github.repository": "atlanai/software-factory-demo",
                "github.run_id": "daytona-langgraph-live-1",
                "github.pull_request.number": "1",
                "git.commit.sha": request.head_sha,
                "review.case_id": evaluation.id,
            },
        },
        sandbox_name=SANDBOX_NAME,
        retain_sandbox=True,
    )
    result = ReviewController(
        registry=FixedSkillRegistry(package),
        knowledge=DirectoryKnowledgeSource(ROOT / "knowledge"),
        runtime=runtime,
        traces=NoopTraceRecorder(),
    ).run(request, reference, evaluation=evaluation, trace_mode="sdk")
    print(
        json.dumps(
            {
                "agent_id": AGENT_ID,
                "decision": result.get("decision"),
                "finding_count": len(result.get("findings", [])),
                "trace_id": result.get("trace_id"),
                "session_id": result.get("session_id"),
                "output_id": result.get("output_id"),
                "sandbox_id": result.get("daytona_sandbox_id"),
                "sandbox_lifecycle": result.get("daytona_sandbox_lifecycle"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
