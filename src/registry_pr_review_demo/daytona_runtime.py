from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

from daytona import CreateSandboxFromImageParams, Daytona, Image


class ExecuteResponse(Protocol):
    @property
    def exit_code(self) -> int | None: ...

    @property
    def result(self) -> str | None: ...


class SandboxFileSystem(Protocol):
    def upload_file(self, file: bytes, remote_path: str) -> None: ...

    def download_file(self, remote_path: str) -> bytes: ...


class SandboxProcess(Protocol):
    def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> ExecuteResponse: ...


class Sandbox(Protocol):
    @property
    def fs(self) -> SandboxFileSystem: ...

    @property
    def process(self) -> SandboxProcess: ...


class DaytonaClient(Protocol):
    def create(self, params: object) -> Sandbox: ...

    def delete(self, sandbox: Sandbox) -> None: ...


class DaytonaRuntime:
    """Runs a serialized review job in an isolated, ephemeral Daytona sandbox."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], DaytonaClient] | None = None,
        worker_archive: bytes,
        sdk_wheel: Path | None = None,
        cli_binary: Path | None = None,
        allowed_domains: tuple[str, ...] = (),
        secrets: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
        payload_overrides: Mapping[str, object] | None = None,
    ) -> None:
        self._client_factory = client_factory or cast(Callable[[], DaytonaClient], Daytona)
        self._worker_archive = worker_archive
        self._sdk_wheel = sdk_wheel
        self._cli_binary = cli_binary
        if any(not re.fullmatch(r"[a-z0-9.-]+", domain) for domain in allowed_domains):
            raise ValueError("Daytona domain allowlist contains an invalid hostname")
        self._allowed_domains = allowed_domains
        self._secrets = dict(secrets or {})
        self._env_vars = dict(env_vars or {})
        self._payload_overrides = dict(payload_overrides or {})

    def run(self, payload: Mapping[str, object]) -> dict[str, object]:
        client = self._client_factory()
        image = Image.debian_slim("3.12").pip_install("langgraph==1.2.11")
        if self._sdk_wheel is not None:
            wheel_name = self._sdk_wheel.name
            if not re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", wheel_name):
                raise ValueError("SDK wheel filename is invalid")
            remote_wheel = f"/opt/registry-pr-review/{wheel_name}"
            image.add_local_file(self._sdk_wheel, remote_wheel)
            image.run_commands(f"python -m pip install {remote_wheel}")
        if self._cli_binary is not None:
            image.add_local_file(self._cli_binary, "/usr/local/bin/atlanai")
            image.run_commands("chmod 0755 /usr/local/bin/atlanai")
        network_block_all = not self._allowed_domains
        params = CreateSandboxFromImageParams(
            image=image,
            language="python",
            ephemeral=True,
            auto_stop_interval=5,
            network_block_all=network_block_all,
            domain_allow_list=(",".join(self._allowed_domains) if self._allowed_domains else None),
            secrets=self._secrets or None,
            labels={"purpose": "registry-pr-review-demo"},
            env_vars=self._env_vars or None,
        )
        sandbox = client.create(params)
        try:
            job_payload = dict(payload)
            job_payload.update(self._payload_overrides)
            raw_attributes = job_payload.get("attributes", {})
            attributes: dict[str, object] = (
                {
                    str(key): value
                    for key, value in cast(dict[object, object], raw_attributes).items()
                }
                if isinstance(raw_attributes, dict)
                else {}
            )
            attributes["daytona.sandbox.id"] = getattr(sandbox, "id", "unknown")
            job_payload["attributes"] = attributes
            sandbox.fs.upload_file(self._worker_archive, "/workspace/agent.pyz")
            sandbox.fs.upload_file(
                json.dumps(job_payload, separators=(",", ":"), sort_keys=True).encode(),
                "/workspace/request.json",
            )
            response = sandbox.process.exec(
                (
                    "python /workspace/agent.pyz --request /workspace/request.json "
                    "--output /workspace/result.json"
                ),
                cwd="/workspace",
                env={"PYTHONDONTWRITEBYTECODE": "1"},
                timeout=300,
            )
            if response.exit_code != 0:
                detail = re.sub(
                    r"(?i)(api[_-]?key|token|authorization)(\s*[=:]\s*)\S+",
                    r"\1\2[REDACTED]",
                    response.result or "no worker output",
                )[-4000:]
                raise RuntimeError(
                    f"Daytona worker failed with exit code {response.exit_code}: {detail}"
                )
            raw_result = sandbox.fs.download_file("/workspace/result.json")
            result = json.loads(raw_result)
            if not isinstance(result, dict):
                raise RuntimeError("Daytona worker returned an invalid result shape")
            return cast(dict[str, object], result)
        finally:
            client.delete(sandbox)
