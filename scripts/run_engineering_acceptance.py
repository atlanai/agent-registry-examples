#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from daytona import Daytona, DaytonaConfig, SessionExecuteRequest

from registry_pr_review_demo.kiro_runtime import parse_kiro_stream
from registry_pr_review_demo.worker_bundle import build_worker_archive

ROOT = Path(__file__).resolve().parents[1]
DAYTONA_CONFIG = Path.home() / "Library/Application Support/daytona/config.json"
SANDBOX_NAME = "engineering-pr-review-live-20260904"
AGENT_ID = "agent_01m1pn4k5deggsts6h7fvfvcgx"
PROVIDER_ID = "agent_provider_01m1pn17zyfxgtdde2mwwwff4w"
ENVIRONMENT_ID = "agent_environment_01m1pn1qw6e3hr8v0emnb1b6nh"
CASES = (
    "risky-injection-regression",
    "safe-parameterized-change",
    "sql-format-regression",
)
SKILL_SPECS = {
    "skill_01m1pn0115ee19gjbzdjxdrady": ("secure-pr-review", "skills/secure-pr-review/SKILL.md"),
    "skill_01m1pn011df01a85dyc5ztjk5h": (
        "test-impact-analysis",
        "skills/test-impact-analysis/SKILL.md",
    ),
    "skill_01m1pn0110fz9b869ddyc00sh6": (
        "review-evidence-summary",
        "skills/review-evidence-summary/SKILL.md",
    ),
}


def _client() -> Daytona:
    raw = json.loads(DAYTONA_CONFIG.read_text(encoding="utf-8"))
    profile = next(item for item in raw["profiles"] if item["id"] == raw["activeProfile"])
    return Daytona(
        DaytonaConfig(
            jwt_token=profile["api"]["token"]["accessToken"],
            organization_id=profile["activeOrganizationId"],
        )
    )


def main() -> int:
    sandbox = _client().get(SANDBOX_NAME)
    sandbox.fs.upload_file(
        build_worker_archive(ROOT / "src/registry_pr_review_demo"), "/workspace/agent.pyz"
    )
    sandbox.fs.upload_file(
        (ROOT / ".kiro/agents/pr-review.json").read_bytes(),
        "/workspace/.kiro/agents/pr-review.json",
    )
    contract = json.loads(sandbox.fs.download_file("/workspace/review-contract.json"))
    skills = []
    for fingerprint in contract["skills_used"]:
        name, path = SKILL_SPECS[fingerprint["id"]]
        skill_path = ROOT / path
        skills.append(
            {
                **fingerprint,
                "name": name,
                "semantic_version": "0.1.1",
                "skillmd_sha256": hashlib.sha256(skill_path.read_bytes()).hexdigest(),
            }
        )
    summaries: list[dict[str, object]] = []
    for index, case_id in enumerate(CASES, start=1):
        source = f"/workspace/cases/{case_id}.diff"
        copied = sandbox.process.exec(f"cp {source} /workspace/change.diff", timeout=30)
        if copied.exit_code != 0:
            raise RuntimeError(f"Could not stage case {case_id}")
        prompt = (
            "Read /workspace/review-contract.json, then review /workspace/change.diff using "
            "every configured review skill. Return only the required JSON evidence object "
            "with the exact Registry skill fingerprints from the contract. Each finding must "
            "use a positive 1-based diff line number when known, or omit the line field. "
            "Perform the review directly and do not invoke sub-agents."
        )
        stream = _run_kiro(sandbox, prompt=prompt, case_id=case_id)
        result, tool_names = parse_kiro_stream(stream)
        external_session_id = f"engineering-{case_id}-{int(time.time())}-{index}"
        payload = {
            "job_type": "kiro_trace",
            "agent_id": AGENT_ID,
            "provider_id": PROVIDER_ID,
            "environment_id": ENVIRONMENT_ID,
            "session_id": external_session_id,
            "skills": skills,
            "tool_names": list(tool_names),
            "attributes": {
                "github.repository": "atlanai/software-factory-demo",
                "github.run_id": f"daytona-live-{index}",
                "github.pull_request.number": "synthetic",
                "git.commit.sha": "47796e5",
                "daytona.sandbox.id": sandbox.id,
                "review.case_id": case_id,
            },
            "result": result,
            "output_url": "https://github.com/atlanai/software-factory-demo/pull/1",
        }
        request_path = f"/workspace/trace-request-{index}.json"
        output_path = f"/workspace/trace-result-{index}.json"
        sandbox.fs.upload_file(json.dumps(payload).encode(), request_path)
        traced = sandbox.process.exec(
            f"python /workspace/agent.pyz --request {request_path} --output {output_path}",
            cwd="/workspace",
            timeout=180,
        )
        if traced.exit_code != 0:
            raise RuntimeError(f"Atlan evidence failed for case {case_id}")
        evidence = json.loads(sandbox.fs.download_file(output_path))
        summaries.append(
            {
                "case_id": case_id,
                "decision": evidence["decision"],
                "finding_count": len(evidence["findings"]),
                "trace_id": evidence["trace_id"],
                "session_id": evidence["session_id"],
                "output_id": evidence["output_id"],
                "model": evidence.get("model", "kiro-auto"),
                "tool_tokens": evidence.get("kiro_tool_tokens", 0),
                "credits_used": evidence.get("kiro_credits_used", 0.0),
                "tools": list(tool_names),
            }
        )
    print(json.dumps({"sandbox_id": sandbox.id, "runs": summaries}, indent=2, sort_keys=True))
    return 0


def _run_kiro(sandbox: Any, *, prompt: str, case_id: str) -> str:
    process = sandbox.process
    session_id = f"kiro-{case_id}-{uuid.uuid4().hex[:8]}"
    process.create_session(session_id)
    try:
        command = process.execute_session_command(
            session_id,
            SessionExecuteRequest(
                command=(
                    "/usr/local/bin/kiro-cli chat --agent-engine v3 --agent pr-review "
                    "--no-interactive --trust-all-tools "
                    f"--output-format stream-json {json.dumps(prompt)}"
                ),
                run_async=True,
                suppress_input_echo=True,
            ),
            timeout=600,
        )
        for _ in range(120):
            logs = process.get_session_command_logs(session_id, command.cmd_id)
            stdout = logs.stdout or ""
            if '"type":"runFinished"' in stdout:
                return stdout
            if '"type":"runFailed"' in stdout:
                raise RuntimeError(f"Kiro failed for case {case_id}")
            time.sleep(5)
        raise RuntimeError(f"Kiro timed out for case {case_id}")
    finally:
        process.delete_session(session_id)


if __name__ == "__main__":
    raise SystemExit(main())
