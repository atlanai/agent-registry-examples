#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona

from registry_pr_review_demo.cli import KIRO_RUNTIME_DOMAINS
from registry_pr_review_demo.registration import DATA_WORKSPACE_ID


def main() -> int:
    if not os.environ.get("DAYTONA_API_KEY"):
        raise SystemExit("DAYTONA_API_KEY is required")

    sandbox = Daytona().create(
        CreateSandboxFromSnapshotParams(
            name="software-factory-kiro-acceptance-4",
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
    project_root = Path(__file__).resolve().parents[1]
    cli_binary = project_root / "vendor/atlanai/atlanai-linux-amd64"
    expected_digest = "2de549a7f584f748f8e082e7c88b18a0e916ef3051f06be2aeddfefa6b13ea59"
    if hashlib.sha256(cli_binary.read_bytes()).hexdigest() != expected_digest:
        raise RuntimeError("Pinned Atlan CLI digest mismatch")
    sandbox.fs.upload_file(cli_binary.read_bytes(), "/usr/local/bin/atlanai")
    installed = sandbox.process.exec("chmod 0755 /usr/local/bin/atlanai", timeout=30)
    if installed.exit_code != 0:
        raise RuntimeError("Atlan CLI installation failed")
    print(
        json.dumps(
            {
                "sandbox_id": sandbox.id,
                "sandbox_name": "software-factory-kiro-acceptance-4",
                "agent_secret": "kiro-pr-review-agent-key",
                "credential_mode": "daytona-secret-placeholder",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
