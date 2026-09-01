#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from daytona import CreateSandboxFromSnapshotParams, Daytona

from registry_pr_review_demo.cli import KIRO_RUNTIME_DOMAINS
from registry_pr_review_demo.registration import DATA_WORKSPACE_ID


def main() -> int:
    if not os.environ.get("DAYTONA_API_KEY"):
        raise SystemExit("DAYTONA_API_KEY is required")

    sandbox = Daytona().create(
        CreateSandboxFromSnapshotParams(
            name="software-factory-kiro-acceptance-3",
            snapshot="software-factory-kiro-runtime-2-20-1",
            language="python",
            auto_stop_interval=30,
            auto_archive_interval=240,
            ttl_minutes=240,
            secrets={
                "ATLAN_API_KEY": "kiro-pr-review-agent-key",
                "ATLANAI_TOKEN": "kiro-pr-review-agent-key",
            },
            domain_allow_list=",".join(KIRO_RUNTIME_DOMAINS),
            env_vars={
                "ATLAN_BASE_URL": "https://agentgateway.atlan.engineering",
                "ATLANAI_GATEWAY_URL": "https://agentgateway.atlan.engineering",
                "ATLAN_TRACE_CONTENT": "false",
                "ATLAN_WORKSPACE_ID": DATA_WORKSPACE_ID,
                "KIRO_HOME": "/workspace/.kiro-home",
            },
            labels={"purpose": "software-factory-kiro-device-acceptance"},
        ),
        timeout=180,
    )
    print(
        json.dumps(
            {
                "sandbox_id": sandbox.id,
                "sandbox_name": "software-factory-kiro-acceptance-3",
                "agent_secret": "kiro-pr-review-agent-key",
                "credential_mode": "daytona-secret-placeholder",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
