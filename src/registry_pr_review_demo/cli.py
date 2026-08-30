from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import registry_pr_review_demo
from registry_pr_review_demo.cli_skill_loader import AtlanCliSkillLoader
from registry_pr_review_demo.cli_trace import run_atlanai_cli
from registry_pr_review_demo.controller import ReviewController
from registry_pr_review_demo.daytona_runtime import DaytonaRuntime
from registry_pr_review_demo.kiro_runtime import KiroDaytonaRuntime
from registry_pr_review_demo.knowledge import DirectoryKnowledgeSource
from registry_pr_review_demo.models import (
    ReviewRequest,
    SkillArtifactRef,
    SkillPackage,
)
from registry_pr_review_demo.ports import SkillRegistry
from registry_pr_review_demo.provisioner import RegistryProvisioner
from registry_pr_review_demo.registration import DATA_WORKSPACE_ID, build_desired_registry_state
from registry_pr_review_demo.trace_analysis import analyze_trace_gap, load_evaluation, load_rules
from registry_pr_review_demo.trace_reader import AtlanCliTraceReader
from registry_pr_review_demo.worker_bundle import build_worker_archive

MAX_JSON_BYTES = 4_000_000


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    command = cast(str, args.command)
    if command == "build-request":
        return _build_request(args)
    if command == "publish-skill":
        return _publish_skill(args)
    if command == "run":
        return _run_sdk(args)
    if command == "run-sdk":
        return _run_sdk(args)
    if command == "run-kiro":
        return _run_kiro(args)
    if command == "analyze-traces":
        return _analyze_traces(args)
    if command == "run-improver-cli":
        return _run_improver_cli(args)
    if command == "registry-plan":
        return _registry_plan(args)
    if command == "registry-apply":
        return _registry_apply(args)
    if command == "registry-rekey":
        return _registry_rekey(args)
    parser.error(f"unknown command: {command}")
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="registry-pr-review",
        description="Run a Registry-governed LangGraph PR-review agent in Daytona",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-request", help="Build a bounded request from a PR diff")
    build.add_argument("--repository", required=True)
    build.add_argument("--pr-number", required=True, type=int)
    build.add_argument("--head-sha", required=True)
    build.add_argument("--diff-file", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)

    publish = subparsers.add_parser("publish-skill", help="Publish or version a skill")
    publish.add_argument("--skill-dir", required=True, type=Path)
    publish.add_argument("--name", required=True)
    publish.add_argument("--description", default="Synthetic PR-review policy")
    publish.add_argument("--output", required=True, type=Path)

    run = subparsers.add_parser("run", help="Run the governed review in Daytona")
    run.add_argument("--request", required=True, type=Path)
    run.add_argument("--skill-reference", required=True, type=Path)
    run.add_argument("--knowledge-root", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--case-id", default="sql-format-interpolation")
    run.add_argument("--evaluations", type=Path, default=Path("examples/evaluations.json"))

    run_sdk = subparsers.add_parser("run-sdk", help="Run and trace the review inside Daytona")
    run_sdk.add_argument("--request", required=True, type=Path)
    run_sdk.add_argument("--skill-reference", required=True, type=Path)
    run_sdk.add_argument("--knowledge-root", required=True, type=Path)
    run_sdk.add_argument("--output", required=True, type=Path)
    run_sdk.add_argument("--case-id", default="sql-format-interpolation")
    run_sdk.add_argument("--evaluations", type=Path, default=Path("examples/evaluations.json"))

    run_kiro = subparsers.add_parser(
        "run-kiro", help="Run the independent Kiro PR reviewer inside Daytona"
    )
    run_kiro.add_argument(
        "--diff", type=Path, default=Path("factory/fixtures/risky-order-change.diff")
    )
    run_kiro.add_argument("--references", type=Path, default=Path("registry/skill-references.json"))
    run_kiro.add_argument("--state", type=Path, default=Path("registry/state.json"))
    run_kiro.add_argument("--kiro-binary", type=Path, default=Path("work/kiro/kiro-cli"))
    run_kiro.add_argument("--output", type=Path, required=True)
    run_kiro.add_argument("--case-id", default="sql-format-interpolation")

    analyze = subparsers.add_parser(
        "analyze-traces", help="Create an approval-gated skill patch proposal"
    )
    analyze.add_argument("--skill-id", required=True)
    analyze.add_argument("--version", required=True, type=int)
    analyze.add_argument("--case-id", required=True)
    analyze.add_argument("--evaluations", required=True, type=Path)
    analyze.add_argument("--rules", required=True, type=Path)
    analyze.add_argument("--output-dir", required=True, type=Path)

    improve = subparsers.add_parser(
        "run-improver-cli", help="Run the trace-improvement agent in Daytona"
    )
    improve.add_argument("--target-skill-reference", required=True, type=Path)
    improve.add_argument("--analyzer-skill-reference", required=True, type=Path)
    improve.add_argument("--case-id", required=True)
    improve.add_argument("--evaluations", required=True, type=Path)
    improve.add_argument("--output-dir", required=True, type=Path)

    registry_plan = subparsers.add_parser(
        "registry-plan", help="Write the desired Data workspace registration plan"
    )
    registry_plan.add_argument("--output", required=True, type=Path)

    registry_apply = subparsers.add_parser(
        "registry-apply", help="Create and verify the approved Data workspace objects"
    )
    registry_apply.add_argument("--output", required=True, type=Path)

    registry_rekey = subparsers.add_parser(
        "registry-rekey", help="Rotate both agent keys and store them in Keychain"
    )
    registry_rekey.add_argument("--state", required=True, type=Path)
    return parser


def _build_request(args: argparse.Namespace) -> int:
    diff_path = cast(Path, args.diff_file)
    if diff_path.stat().st_size > 2_000_000:
        raise ValueError("diff exceeds the 2 MB demo limit")
    request = ReviewRequest(
        repository=cast(str, args.repository),
        pull_request_number=cast(int, args.pr_number),
        head_sha=cast(str, args.head_sha),
        diff=diff_path.read_text(encoding="utf-8"),
    )
    _write_json(
        cast(Path, args.output),
        {
            "repository": request.repository,
            "pull_request_number": request.pull_request_number,
            "head_sha": request.head_sha,
            "diff": request.diff,
        },
    )
    return 0


def _publish_skill(args: argparse.Namespace) -> int:
    skill_dir = cast(Path, args.skill_dir)
    expected_name = cast(str, args.name)
    workspace_id = os.environ.get("ATLAN_WORKSPACE_ID", DATA_WORKSPACE_ID)
    for command in (
        ("atlanai", "skill", "validate", str(skill_dir)),
        ("atlanai", "skill", "push", str(skill_dir), "--workspace", workspace_id),
    ):
        result = run_atlanai_cli(command)
        if result.exit_code != 0:
            raise RuntimeError("atlanai skill publication failed")
    listed = run_atlanai_cli(
        (
            "atlanai",
            "skill",
            "list",
            "--workspace",
            workspace_id,
            "--filter",
            f"name={expected_name}",
            "--json",
            "id,name,source_digest,version_ordinal",
            "--jq",
            ".",
        )
    )
    if listed.exit_code != 0:
        raise RuntimeError("atlanai skill readback failed")
    payload: object = json.loads(listed.stdout)
    if not isinstance(payload, list):
        raise RuntimeError("atlanai skill readback returned an invalid list")
    candidates: list[dict[str, object]] = []
    for item in cast(list[object], payload):
        if not isinstance(item, dict):
            continue
        candidate = cast(dict[str, object], item)
        if candidate.get("name") == expected_name:
            candidates.append(candidate)
    if not candidates:
        raise RuntimeError("published skill was not found in Registry")
    latest = max(candidates, key=lambda item: cast(int, item.get("version_ordinal", 0)))
    skill_id = latest.get("id")
    version = latest.get("version_ordinal")
    if not isinstance(skill_id, str) or isinstance(version, bool) or not isinstance(version, int):
        raise RuntimeError("published skill readback is missing id or version")
    loaded = AtlanCliSkillLoader().load(SkillArtifactRef(skill_id, version))
    _write_json(
        cast(Path, args.output),
        {
            "id": loaded.reference.id,
            "version": loaded.reference.version,
            "source_digest": loaded.reference.source_digest,
            "semantic_version": loaded.reference.semantic_version,
            "skillmd_sha256": loaded.reference.skillmd_sha256,
        },
    )
    return 0


class _FixedSkillRegistry(SkillRegistry):
    def __init__(self, reference: SkillArtifactRef, package: SkillPackage) -> None:
        self._reference = reference
        self._package = package

    def load_skill(self, reference: SkillArtifactRef) -> SkillPackage:
        if reference.id != self._reference.id or reference.version != self._reference.version:
            raise ValueError("requested skill differs from the loaded Registry version")
        return self._package


def _run_sdk(args: argparse.Namespace) -> int:
    _required_env("DAYTONA_API_KEY")
    request = _review_request(_read_json(cast(Path, args.request)))
    reference = _skill_reference(_read_json(cast(Path, args.skill_reference)))
    loaded = AtlanCliSkillLoader().load(reference)
    evaluation = load_evaluation(cast(Path, args.evaluations), cast(str, args.case_id))
    package_dir = Path(registry_pr_review_demo.__file__).parent
    project_root = package_dir.parents[1]
    sdk_wheel = project_root / "vendor/atlan-ai/atlan_ai-0.1.0-py3-none-any.whl"
    secret_name = os.environ.get("DAYTONA_SDK_AGENT_SECRET", "pr-review-agent-key")
    controller = ReviewController(
        registry=_FixedSkillRegistry(loaded.reference, loaded.package),
        knowledge=DirectoryKnowledgeSource(cast(Path, args.knowledge_root)),
        runtime=DaytonaRuntime(
            worker_archive=build_worker_archive(package_dir),
            sdk_wheel=sdk_wheel,
            allowed_domains=("agentgateway.atlan.engineering",),
            secrets={"ATLAN_API_KEY": secret_name},
            env_vars={
                "ATLAN_WORKSPACE_ID": DATA_WORKSPACE_ID,
                "ATLAN_BASE_URL": "https://agentgateway.atlan.engineering",
                "ATLAN_TRACE_CONTENT": "false",
            },
        ),
        traces=_NoopTraceRecorder(),
    )
    result = controller.run(
        request,
        loaded.reference,
        evaluation=evaluation,
        trace_mode="sdk",
    )
    _write_json(cast(Path, args.output), result)
    return 0


KIRO_REVIEW_SKILLS = (
    "secure-pr-review",
    "test-impact-analysis",
    "review-evidence-summary",
)
KIRO_RUNTIME_DOMAINS = (
    "agentgateway.atlan.engineering",
    "prod.us-east-1.auth.desktop.kiro.dev",
    "prod.us-east-1.telemetry.desktop.kiro.dev",
    "q.us-east-1.amazonaws.com",
    "runtime.us-east-1.kiro.dev",
    "management.us-east-1.kiro.dev",
    "telemetry.us-east-1.kiro.dev",
)


def _run_kiro(args: argparse.Namespace) -> int:
    _required_env("DAYTONA_API_KEY")
    project_root = Path(registry_pr_review_demo.__file__).parent.parents[1]
    references = _read_json(cast(Path, args.references))
    state = _read_json(cast(Path, args.state))
    skills = [_verified_skill(name, references, project_root) for name in KIRO_REVIEW_SKILLS]
    agent_ids = _mapping_value(state.get("agent_ids"), "agent_ids")
    agent_id = agent_ids.get("kiro-pr-review-agent")
    if not isinstance(agent_id, str) or not agent_id.startswith("agent_"):
        raise RuntimeError("Registry state is missing the Kiro Agent identity")
    provider_id = state.get("provider_id")
    environment_ids = _mapping_value(state.get("environment_ids"), "environment_ids")
    environment_id = environment_ids.get("daytona-kiro-pr-review")
    if not isinstance(provider_id, str) or not provider_id.startswith("agent_provider_"):
        raise RuntimeError("Registry state is missing the Daytona provider identity")
    if not isinstance(environment_id, str) or not environment_id.startswith("agent_environment_"):
        raise RuntimeError("Registry state is missing the Kiro environment identity")
    diff_path = cast(Path, args.diff)
    if diff_path.stat().st_size > 2_000_000:
        raise ValueError("diff exceeds the 2 MB demo limit")
    workspace_files: dict[str, bytes] = {
        "/workspace/change.diff": diff_path.read_bytes(),
        "/workspace/.kiro/agents/pr-review.md": (
            project_root / ".kiro/agents/pr-review.md"
        ).read_bytes(),
    }
    for name in KIRO_REVIEW_SKILLS:
        skill_root = project_root / "skills" / name
        for path in sorted(skill_root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(skill_root).as_posix()
                workspace_files[f"/workspace/.kiro/skills/{name}/{relative}"] = path.read_bytes()
    service_root = project_root / "software/order-service"
    for path in sorted(service_root.rglob("*")):
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts:
            relative = path.relative_to(service_root).as_posix()
            workspace_files[f"/workspace/software/order-service/{relative}"] = path.read_bytes()
    contract = {
        "decision_values": ["approve", "comment", "changes_requested"],
        "skills_used": [
            {
                "id": skill["id"],
                "version": skill["version"],
                "source_digest": skill["source_digest"],
            }
            for skill in skills
        ],
    }
    workspace_files["/workspace/review-contract.json"] = json.dumps(
        contract, separators=(",", ":"), sort_keys=True
    ).encode()
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    commit_sha = os.environ.get("GITHUB_SHA", "0" * 40)
    repository = os.environ.get("GITHUB_REPOSITORY", "atlanai/software-factory-demo")
    trace_payload: dict[str, object] = {
        "agent_id": agent_id,
        "provider_id": provider_id,
        "environment_id": environment_id,
        "session_id": f"github-{run_id}-kiro-review",
        "output_url": (
            f"https://github.com/{repository}"
            + (f"/actions/runs/{run_id}" if run_id != "local" else "")
        ),
        "skills": skills,
        "attributes": {
            "github.repository": repository,
            "github.run_id": run_id,
            "git.commit.sha": commit_sha,
            "review.case_id": cast(str, args.case_id),
        },
    }
    runtime = KiroDaytonaRuntime(
        kiro_binary=cast(Path, args.kiro_binary),
        worker_archive=build_worker_archive(Path(registry_pr_review_demo.__file__).parent),
        sdk_wheel=project_root / "vendor/atlan-ai/atlan_ai-0.1.0-py3-none-any.whl",
        workspace_files=workspace_files,
        secrets={
            "ATLAN_API_KEY": "kiro-pr-review-agent-key",
            "KIRO_API_KEY": "kiro-api-key",
        },
        allowed_domains=KIRO_RUNTIME_DOMAINS,
        workspace_id=DATA_WORKSPACE_ID,
    )
    result = runtime.run(trace_payload)
    _write_json(cast(Path, args.output), result)
    return 0


def _verified_skill(
    name: str, references: Mapping[str, object], project_root: Path
) -> dict[str, object]:
    raw = _mapping_value(references.get(name), f"skill reference {name}")
    skill_id = raw.get("id")
    version = raw.get("version")
    source_digest = raw.get("source_digest")
    semantic_version = raw.get("semantic_version")
    skillmd_sha256 = raw.get("skillmd_sha256")
    if (
        not isinstance(skill_id, str)
        or not skill_id.startswith("skill_")
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
        or not isinstance(source_digest, str)
        or len(source_digest) != 64
        or not isinstance(semantic_version, str)
        or not isinstance(skillmd_sha256, str)
        or len(skillmd_sha256) != 64
    ):
        raise RuntimeError(f"Registry fingerprint for {name} is incomplete")
    local_digest = hashlib.sha256(
        (project_root / "skills" / name / "SKILL.md").read_bytes()
    ).hexdigest()
    if local_digest != skillmd_sha256:
        raise RuntimeError(f"local {name} SKILL.md differs from the Registry fingerprint")
    return {
        "name": name,
        "id": skill_id,
        "version": version,
        "source_digest": source_digest,
        "semantic_version": semantic_version,
        "skillmd_sha256": skillmd_sha256,
    }


def _mapping_value(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


class _NoopTraceRecorder:
    def record(
        self,
        request: ReviewRequest,
        skill: SkillPackage,
        result: dict[str, object],
    ) -> None:
        del request, skill, result


def _analyze_traces(args: argparse.Namespace) -> int:
    case_id = cast(str, args.case_id)
    evaluation = load_evaluation(cast(Path, args.evaluations), case_id)
    rules = load_rules(cast(Path, args.rules))
    evidence = AtlanCliTraceReader().fetch_case(
        skill_id=cast(str, args.skill_id),
        version_ordinal=cast(int, args.version),
        case_id=case_id,
    )
    proposal = analyze_trace_gap(trace=evidence.trace, evaluation=evaluation, rules=rules)
    output_dir = cast(Path, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "proposal.json", proposal.as_dict())
    (output_dir / "proposal.md").write_text(proposal.to_markdown(), encoding="utf-8")
    return 0


def _run_improver_cli(args: argparse.Namespace) -> int:
    _required_env("DAYTONA_API_KEY")
    target_reference = _skill_reference(_read_json(cast(Path, args.target_skill_reference)))
    analyzer_reference = _skill_reference(_read_json(cast(Path, args.analyzer_skill_reference)))
    loader = AtlanCliSkillLoader()
    target = loader.load(target_reference)
    analyzer = loader.load(analyzer_reference)
    evaluation = load_evaluation(cast(Path, args.evaluations), cast(str, args.case_id))
    analyzer_fingerprint = {
        "name": analyzer.package.name,
        "semantic_version": analyzer.reference.semantic_version,
        "registry_version": analyzer.reference.version,
        "source_digest": analyzer.reference.source_digest,
        "skillmd_sha256": analyzer.reference.skillmd_sha256,
    }
    if any(value is None for value in analyzer_fingerprint.values()):
        raise RuntimeError("analyzer skill fingerprint is incomplete")
    payload: dict[str, object] = {
        "job_type": "improve",
        "target_skill": {
            "id": target.reference.id,
            "version": target.reference.version,
        },
        "analyzer_skill": analyzer_fingerprint,
        "evaluation": {
            "id": evaluation.id,
            "expected_decision": evaluation.expected_decision.value,
            "diff": evaluation.diff,
        },
        "rules": [
            {
                "id": rule.id,
                "pattern": rule.pattern,
                "severity": rule.severity.value,
                "message": rule.message,
                "knowledge_ids": list(rule.knowledge_ids),
            }
            for rule in target.package.rules
        ],
    }
    package_dir = Path(registry_pr_review_demo.__file__).parent
    project_root = package_dir.parents[1]
    secret_name = os.environ.get("DAYTONA_CLI_AGENT_SECRET", "registry-cli-agent-key")
    result = DaytonaRuntime(
        worker_archive=build_worker_archive(package_dir),
        cli_binary=project_root / "vendor/atlanai/atlanai-linux-amd64",
        allowed_domains=("agentgateway.atlan.engineering",),
        secrets={"ATLANAI_TOKEN": secret_name},
        env_vars={"ATLANAI_GATEWAY_URL": "https://agentgateway.atlan.engineering"},
    ).run(payload)
    output_dir = cast(Path, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    proposal = result.get("proposal")
    markdown = result.get("proposal_markdown")
    if not isinstance(proposal, dict) or not isinstance(markdown, str):
        raise RuntimeError("improvement worker returned an invalid proposal")
    _write_json(output_dir / "proposal.json", cast(dict[str, object], proposal))
    (output_dir / "proposal.md").write_text(markdown, encoding="utf-8")
    _write_json(output_dir / "run.json", result)
    return 0


def _registry_plan(args: argparse.Namespace) -> int:
    desired = build_desired_registry_state()
    _write_json(
        cast(Path, args.output),
        {
            "workspace_id": desired.workspace_id,
            "provider": desired.provider.name,
            "environments": [item.name for item in desired.environments],
            "agents": [item.name for item in desired.agents],
        },
    )
    return 0


def _registry_apply(args: argparse.Namespace) -> int:
    state = RegistryProvisioner().apply()
    _write_json(cast(Path, args.output), state)
    return 0


def _registry_rekey(args: argparse.Namespace) -> int:
    state = _read_json(cast(Path, args.state))
    RegistryProvisioner().rotate_and_store_agent_keys(state)
    return 0


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not configured")
    return value


def _read_json(path: Path) -> dict[str, object]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"{path.name} exceeds the 4 MB limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], payload)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _review_request(payload: Mapping[str, object]) -> ReviewRequest:
    repository = payload.get("repository")
    pr_number = payload.get("pull_request_number")
    head_sha = payload.get("head_sha")
    diff = payload.get("diff")
    if (
        not isinstance(repository, str)
        or not isinstance(head_sha, str)
        or not isinstance(diff, str)
    ):
        raise ValueError("Request repository, head_sha, and diff must be strings")
    if isinstance(pr_number, bool) or not isinstance(pr_number, int):
        raise ValueError("Request pull_request_number must be an integer")
    return ReviewRequest(repository, pr_number, head_sha, diff)


def _skill_reference(payload: Mapping[str, object]) -> SkillArtifactRef:
    skill_id = payload.get("id")
    version = payload.get("version")
    source_digest = payload.get("source_digest")
    semantic_version = payload.get("semantic_version")
    skillmd_sha256 = payload.get("skillmd_sha256")
    if not isinstance(skill_id, str) or isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("Skill reference needs a string id and integer version")
    if source_digest is not None and not isinstance(source_digest, str):
        raise ValueError("Skill source_digest must be a string or null")
    if semantic_version is not None and not isinstance(semantic_version, str):
        raise ValueError("Skill semantic_version must be a string or null")
    if skillmd_sha256 is not None and not isinstance(skillmd_sha256, str):
        raise ValueError("Skill skillmd_sha256 must be a string or null")
    return SkillArtifactRef(
        skill_id,
        version,
        source_digest,
        semantic_version,
        skillmd_sha256,
    )


if __name__ == "__main__":
    raise SystemExit(main())
