#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from daytona import Daytona, DaytonaConfig

from registry_pr_review_demo.worker_bundle import build_worker_archive

ROOT = Path(__file__).resolve().parents[1]
DAYTONA_CONFIG = Path.home() / "Library/Application Support/daytona/config.json"
SANDBOX_NAME = "engineering-pr-review-live-20260904"
WORKSPACE_ID = "workspace_01m1dtasngfk08s4xydm62ewdw"
AGENT_ID = "agent_01m1pn4k5deggsts6h7fvfvcgx"
PROVIDER_ID = "agent_provider_01m1pn17zyfxgtdde2mwwwff4w"
ENVIRONMENT_ID = "agent_environment_01m1pn1qw6e3hr8v0emnb1b6nh"
VISITOR_ID = "visitor_01m1prfbcqe0raj9mfqq88mwyd"
SERIES_ID = "customer-demo-30d-v1"
SCHEDULE = ((28, 1), (25, 2), (22, 1), (19, 3), (16, 2), (13, 1), (10, 3), (7, 2), (4, 1))
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
CASES = (
    {
        "name": "risky-injection-regression",
        "decision": "changes_requested",
        "findings": [
            {
                "rule_id": "no-dynamic-eval",
                "severity": "critical",
                "message": "Dynamic evaluation of request-controlled input must be removed.",
                "line": 5,
            },
            {
                "rule_id": "parameterize-sql",
                "severity": "critical",
                "message": "Use a parameterized query instead of interpolating SQL.",
                "line": 6,
            },
        ],
    },
    {"name": "safe-parameterized-change", "decision": "approve", "findings": []},
    {
        "name": "sql-format-regression",
        "decision": "changes_requested",
        "findings": [
            {
                "rule_id": "parameterize-sql",
                "severity": "high",
                "message": "String formatting still exposes the query to SQL injection.",
                "line": 6,
            }
        ],
    },
)


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
    contract = json.loads(sandbox.fs.download_file("/workspace/review-contract.json"))
    skills = []
    for fingerprint in contract["skills_used"]:
        name, path = SKILL_SPECS[fingerprint["id"]]
        skills.append(
            {
                **fingerprint,
                "name": name,
                "semantic_version": "0.1.1",
                "skillmd_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
            }
        )

    now = datetime.now(UTC)
    receipts: list[dict[str, object]] = []
    run_number = 0
    for days_ago, daily_count in SCHEDULE:
        for daily_slot in range(daily_count):
            case = CASES[run_number % len(CASES)]
            source_time = (now - timedelta(days=days_ago)).replace(
                hour=14 + daily_slot, minute=15, second=0, microsecond=0
            )
            start_ns = int(source_time.timestamp() * 1_000_000_000)
            duration_ms = 1_200 + (run_number % 5) * 700
            session_key = f"backfill-{SERIES_ID}-{source_time:%Y%m%d-%H%M}-{run_number}"
            result = {
                "decision": case["decision"],
                "findings": case["findings"],
                "skills_used": contract["skills_used"],
                "model": "kiro-auto",
                "kiro_tool_tokens": 4_200 + (run_number % 6) * 310,
                "kiro_credits_used": 0.42 + (run_number % 7) * 0.037,
            }
            payload = {
                "job_type": "kiro_trace",
                "agent_id": AGENT_ID,
                "provider_id": PROVIDER_ID,
                "environment_id": ENVIRONMENT_ID,
                "visitor": {"id": VISITOR_ID},
                "session_id": session_key,
                "skills": skills,
                "tool_names": ["read", "glob"],
                "attributes": {
                    "github.repository": "atlanai/software-factory-demo",
                    "github.run_id": session_key,
                    "github.pull_request.number": "historical-replay",
                    "git.commit.sha": "0a2964c",
                    "daytona.sandbox.id": sandbox.id,
                    "review.case_id": f"historical-replay/{case['name']}",
                    "demo.backfill": "true",
                    "demo.backfill.series": SERIES_ID,
                },
                "result": result,
                "source_start_time_ns": start_ns,
                "source_end_time_ns": start_ns + duration_ms * 1_000_000,
                "source_created_at": source_time.isoformat().replace("+00:00", "Z"),
                "output_url": "https://github.com/atlanai/software-factory-demo",
            }
            request_path = f"/workspace/backfill-request-{run_number}.json"
            output_path = f"/workspace/backfill-result-{run_number}.json"
            sandbox.fs.upload_file(json.dumps(payload).encode(), request_path)
            response = sandbox.process.exec(
                f"python /workspace/agent.pyz --request {request_path} --output {output_path}",
                cwd="/workspace",
                timeout=180,
            )
            if response.exit_code != 0:
                raise RuntimeError(f"Historical replay failed at run {run_number}")
            evidence = json.loads(sandbox.fs.download_file(output_path))
            receipts.append(
                {
                    "source_date": source_time.date().isoformat(),
                    "decision": evidence["decision"],
                    "trace_id": evidence["trace_id"],
                    "session_id": evidence["session_id"],
                }
            )
            run_number += 1

    print(
        json.dumps(
            {"series": SERIES_ID, "run_count": len(receipts), "runs": receipts},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
