from __future__ import annotations

import json
from collections.abc import Sequence

from registry_pr_review_demo.provisioner import (
    ApiCommandResult,
    RegistryProvisioner,
)


class SecretStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def put(self, *, service: str, account: str, secret: bytes) -> None:
        assert account == "registry-pr-review"
        self.values[service] = secret


def test_provisioner_captures_agent_keys_without_persisting_them() -> None:
    commands: list[tuple[tuple[str, ...], bytes | None]] = []
    counters = {"framework": 0, "provider": 0, "environment": 0, "agent": 0}

    def runner(args: Sequence[str], input_bytes: bytes | None) -> ApiCommandResult:
        command = tuple(args)
        commands.append((command, input_bytes))
        method, path = command[2], command[3]
        if method == "get" and path.endswith(
            ("/agent-frameworks", "/providers", "/environments", "/agents")
        ):
            return ApiCommandResult(0, b'{"items":[]}', b"")
        if method == "post" and path == "agent:/agent-frameworks":
            counters["framework"] += 1
            return ApiCommandResult(0, b'{"id":"agent_framework_kiro","name":"kiro-cli"}', b"")
        if method == "post" and path == "agent:/providers":
            counters["provider"] += 1
            return ApiCommandResult(0, b'{"id":"agent_provider_daytona","name":"daytona"}', b"")
        if method == "post" and path == "agent:/environments":
            counters["environment"] += 1
            name = json.loads(input_bytes or b"{}")["name"]
            return ApiCommandResult(
                0,
                json.dumps({"id": f"agent_environment_{name}", "name": name}).encode(),
                b"",
            )
        if method == "post" and path == "agent:/agents":
            counters["agent"] += 1
            name = json.loads(input_bytes or b"{}")["name"]
            return ApiCommandResult(
                0,
                json.dumps(
                    {
                        "id": f"agent_{name}",
                        "name": name,
                        "identity": {"api_key": f"secret-{name}"},
                    }
                ).encode(),
                b"",
            )
        if method == "post" and path.endswith("/identity/rotate"):
            return ApiCommandResult(0, b'{"api_key":"rotated-key"}', b"")
        if method == "put" and "members" in path:
            return ApiCommandResult(0, b'{"role":"member"}', b"")
        if method == "get":
            identifier = path.rsplit("/", 1)[-1]
            return ApiCommandResult(0, json.dumps({"id": identifier}).encode(), b"")
        raise AssertionError(command)

    secrets = SecretStore()
    state = RegistryProvisioner(runner=runner, secret_store=secrets).apply()

    assert counters == {"framework": 1, "provider": 1, "environment": 3, "agent": 3}
    assert set(secrets.values) == {
        "atlan/pr-review-agent",
        "atlan/registry-skill-improver-cli-agent",
        "atlan/kiro-pr-review-agent-api",
    }
    serialized_state = json.dumps(state)
    assert "secret-registry" not in serialized_state
    assert all("secret-registry" not in " ".join(command) for command, _ in commands)
    assert state["provider_id"] == "agent_provider_daytona"

    secrets.values.clear()
    RegistryProvisioner(runner=runner, secret_store=secrets).rotate_and_store_agent_keys(state)
    assert secrets.values == {
        "atlan/pr-review-agent": b"rotated-key",
        "atlan/registry-skill-improver-cli-agent": b"rotated-key",
        "atlan/kiro-pr-review-agent-api": b"rotated-key",
    }
