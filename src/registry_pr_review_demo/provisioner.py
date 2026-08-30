from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from registry_pr_review_demo.registration import (
    DATA_WORKSPACE_ID,
    build_desired_registry_state,
)
from registry_pr_review_demo.secret_store import KeychainSecretStore

KEYCHAIN_ACCOUNT = "registry-pr-review"


@dataclass(frozen=True, slots=True)
class ApiCommandResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


class SecretStore(Protocol):
    def put(self, *, service: str, account: str, secret: bytes) -> None: ...


def _default_runner(args: Sequence[str], input_bytes: bytes | None) -> ApiCommandResult:
    executable = shutil.which("atlanai")
    if executable is None or not args or args[0] != "atlanai":
        raise RuntimeError("atlanai CLI is unavailable")
    command = (executable, *args[1:])
    completed = subprocess.run(  # noqa: S603 - fixed executable, no shell
        command,
        input=input_bytes,
        check=False,
        capture_output=True,
    )
    return ApiCommandResult(completed.returncode, completed.stdout, completed.stderr)


class RegistryProvisioner:
    def __init__(
        self,
        *,
        runner: Callable[[Sequence[str], bytes | None], ApiCommandResult] = _default_runner,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._runner = runner
        self._secrets = secret_store or KeychainSecretStore()

    def apply(self) -> dict[str, object]:
        desired = build_desired_registry_state()
        providers = self._named_inventory("providers")
        environments = self._named_inventory("environments")
        agents = self._named_inventory("agents")

        provider_id = providers.get(desired.provider.name)
        if provider_id is None:
            provider = self._post(
                "agent:/providers",
                {
                    "name": desired.provider.name,
                    "display_name": "Daytona",
                    "description": "Daytona cloud sandboxes for the Registry PR-review demo.",
                    "workspace_id": desired.workspace_id,
                    "provider_type": desired.provider.provider_type,
                    "homepage_url": "https://www.daytona.io/",
                    "docs_url": "https://www.daytona.io/docs/en/",
                },
            )
            provider_id = _string(provider, "id")
            self._readback("providers", provider_id)

        environment_ids: dict[str, str] = {}
        for environment in desired.environments:
            environment_id = environments.get(environment.name)
            if environment_id is None:
                packages: dict[str, list[str]] = {"pip": ["langgraph==1.2.11"]}
                if environment.name == "daytona-sdk-pr-review":
                    packages["wheel"] = ["atlan-ai==0.1.0"]
                else:
                    packages["binary"] = ["atlanai==0.3.53"]
                created = self._post(
                    "agent:/environments",
                    {
                        "name": environment.name,
                        "display_name": environment.name.replace("-", " ").title(),
                        "description": "Ephemeral Daytona environment with Gateway-only egress.",
                        "workspace_id": desired.workspace_id,
                        "agent_provider_id": provider_id,
                        "environment_type": environment.environment_type,
                        "network_mode": environment.network_mode,
                        "allowed_hosts": list(environment.allowed_hosts),
                        "allow_package_managers": False,
                        "allow_mcp_servers": False,
                        "packages": packages,
                    },
                )
                environment_id = _string(created, "id")
                self._readback("environments", environment_id)
            environment_ids[environment.name] = environment_id

        agent_ids: dict[str, str] = {}
        for agent in desired.agents:
            agent_id = agents.get(agent.name)
            if agent_id is None:
                instructions = (
                    "Review synthetic pull-request diffs using the pinned Registry skill."
                    if agent.name == "registry-pr-review-sdk"
                    else "Analyze version-scoped Registry traces and propose a bounded skill patch."
                )
                created = self._post(
                    "agent:/agents",
                    {
                        "name": agent.name,
                        "display_name": agent.name.replace("-", " ").title(),
                        "description": instructions,
                        "workspace_id": desired.workspace_id,
                        "agent_framework_id": agent.agent_framework_id,
                        "agent_provider_id": provider_id,
                        "instructions": instructions,
                        "max_step_count": 8,
                        "tools": [],
                    },
                )
                agent_id = _string(created, "id")
                api_key = _optional_identity_key(created)
                if api_key is not None:
                    service = (
                        "atlan/registry-pr-review-sdk-agent"
                        if agent.name == "registry-pr-review-sdk"
                        else "atlan/registry-skill-improver-cli-agent"
                    )
                    self._secrets.put(
                        service=service,
                        account=KEYCHAIN_ACCOUNT,
                        secret=api_key.encode(),
                    )
            self._readback("agents", agent_id)
            agent_ids[agent.name] = agent_id

        return {
            "workspace_id": desired.workspace_id,
            "provider_id": provider_id,
            "environment_ids": environment_ids,
            "agent_ids": agent_ids,
        }

    def rotate_and_store_agent_keys(self, state: Mapping[str, object]) -> None:
        raw_agent_ids = state.get("agent_ids")
        if not isinstance(raw_agent_ids, dict):
            raise ValueError("Registry state is missing agent_ids")
        agent_ids = cast(dict[str, object], raw_agent_ids)
        services = {
            "registry-pr-review-sdk": "atlan/registry-pr-review-sdk-agent",
            "registry-skill-improver-cli": "atlan/registry-skill-improver-cli-agent",
        }
        for name, service in services.items():
            agent_id = agent_ids.get(name)
            if not isinstance(agent_id, str):
                raise ValueError(f"Registry state is missing {name}")
            response = self._command(
                (
                    "atlanai",
                    "api",
                    "post",
                    f"agent:/agents/{agent_id}/identity/rotate",
                ),
                None,
            )
            key = response.get("api_key")
            if not isinstance(key, str) or not key:
                raise RuntimeError("agent identity rotation omitted the reveal-once API key")
            self._secrets.put(
                service=service,
                account=KEYCHAIN_ACCOUNT,
                secret=key.encode(),
            )

    def _named_inventory(self, plural: str) -> dict[str, str]:
        payload = self._command(
            (
                "atlanai",
                "api",
                "get",
                f"agent:/{plural}",
                "-f",
                f"workspace_id={DATA_WORKSPACE_ID}",
            ),
            None,
        )
        items = payload.get("items")
        if not isinstance(items, list):
            raise RuntimeError(f"{plural} inventory returned an invalid items field")
        inventory: dict[str, str] = {}
        for raw in cast(list[object], items):
            item = _object(raw)
            inventory[_string(item, "name")] = _string(item, "id")
        return inventory

    def _post(self, path: str, body: Mapping[str, object]) -> dict[str, object]:
        return self._command(
            ("atlanai", "api", "post", path, "--input", "-"),
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode(),
        )

    def _readback(self, plural: str, identifier: str) -> None:
        payload = self._command(
            ("atlanai", "api", "get", f"agent:/{plural}/{identifier}"),
            None,
        )
        if payload.get("id") != identifier:
            raise RuntimeError(f"{plural} readback returned a different id")

    def _command(self, args: Sequence[str], input_bytes: bytes | None) -> dict[str, object]:
        result = self._runner(args, input_bytes)
        if result.exit_code != 0:
            raise RuntimeError("atlanai Registry operation failed")
        if not result.stdout.strip():
            return {}
        try:
            payload: object = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("atlanai Registry operation returned invalid JSON") from error
        return _object(payload)


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("Registry response must be a JSON object")
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Registry response is missing {key}")
    return value


def _optional_identity_key(payload: Mapping[str, object]) -> str | None:
    identity = payload.get("identity")
    if identity is None:
        return None
    if not isinstance(identity, dict):
        raise RuntimeError("agent create response returned an invalid identity")
    key = cast(dict[str, object], identity).get("api_key")
    if not isinstance(key, str) or not key:
        raise RuntimeError("agent create response omitted reveal-once API key")
    return key
