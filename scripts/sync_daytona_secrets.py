#!/usr/bin/env python3
from __future__ import annotations

from daytona import CreateSecretParams, Daytona, DaytonaConfig, UpdateSecretParams

from registry_pr_review_demo.secret_store import KeychainSecretStore

ACCOUNT = "registry-pr-review"
GATEWAY_HOSTS = ["agentgateway.atlan.engineering"]


def main() -> int:
    keychain = KeychainSecretStore()
    daytona_key = keychain.get(service="daytona/api-key", account=ACCOUNT).decode()
    client = Daytona(DaytonaConfig(api_key=daytona_key))
    mappings = (
        (
            "registry-sdk-agent-key",
            keychain.get(service="atlan/registry-pr-review-sdk-agent", account=ACCOUNT).decode(),
        ),
        (
            "registry-cli-agent-key",
            keychain.get(
                service="atlan/registry-skill-improver-cli-agent", account=ACCOUNT
            ).decode(),
        ),
    )
    for name, value in mappings:
        page = client.secret.list(name=name, limit=20)
        existing = next((item for item in page.items if item.name == name), None)
        if existing is None:
            client.secret.create(
                CreateSecretParams(
                    name=name,
                    value=value,
                    description="Registry PR-review demo agent identity",
                    hosts=GATEWAY_HOSTS,
                )
            )
            action = "created"
        else:
            client.secret.update(
                existing.id,
                UpdateSecretParams(value=value, hosts=GATEWAY_HOSTS),
            )
            action = "updated"
        print(f"{action} Daytona Secret {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
