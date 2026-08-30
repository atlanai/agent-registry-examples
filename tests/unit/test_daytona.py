from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from daytona import CreateSandboxFromImageParams, Image

from registry_pr_review_demo.daytona_runtime import DaytonaRuntime, ExecuteResponse, Sandbox


@dataclass
class FakeExecResponse:
    exit_code: int
    result: str = ""


class FakeFileSystem:
    def __init__(self, result: bytes) -> None:
        self.result = result
        self.uploads: list[tuple[bytes, str]] = []

    def upload_file(self, file: bytes, remote_path: str) -> None:
        self.uploads.append((file, remote_path))

    def download_file(self, remote_path: str) -> bytes:
        assert remote_path == "/workspace/result.json"
        return self.result


class FakeProcess:
    def __init__(self, response: FakeExecResponse) -> None:
        self.response = response
        self.commands: list[tuple[str, str | None, dict[str, str] | None, int | None]] = []

    def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        self.commands.append((command, cwd, env, timeout))
        return self.response


class FakeSandbox:
    def __init__(self, result: bytes, response: FakeExecResponse) -> None:
        self.fs = FakeFileSystem(result)
        self.process = FakeProcess(response)


class FakeDaytona:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.created_with: list[object] = []
        self.deleted: list[FakeSandbox] = []

    def create(self, params: object) -> Sandbox:
        self.created_with.append(params)
        return self.sandbox

    def delete(self, sandbox: Sandbox) -> None:
        assert isinstance(sandbox, FakeSandbox)
        self.deleted.append(sandbox)


def test_daytona_runtime_uses_an_ephemeral_network_blocked_sandbox() -> None:
    expected: dict[str, object] = {"decision": "approve", "findings": []}
    sandbox = FakeSandbox(json.dumps(expected).encode(), FakeExecResponse(exit_code=0))
    client = FakeDaytona(sandbox)
    runtime = DaytonaRuntime(client_factory=lambda: client, worker_archive=b"worker archive")
    payload = {"diff": "+safe = True", "head_sha": "a" * 40}

    result = runtime.run(payload)

    assert result == expected
    params = client.created_with[0]
    assert isinstance(params, CreateSandboxFromImageParams)
    assert params.ephemeral is True
    assert params.network_block_all is True
    assert client.deleted == [sandbox]
    assert [path for _, path in sandbox.fs.uploads] == [
        "/workspace/agent.pyz",
        "/workspace/request.json",
    ]
    command, cwd, env, timeout = sandbox.process.commands[0]
    assert command == (
        "python /workspace/agent.pyz --request /workspace/request.json "
        "--output /workspace/result.json"
    )
    assert payload["diff"] not in command
    assert cwd == "/workspace"
    assert env == {"PYTHONDONTWRITEBYTECODE": "1"}
    assert timeout == 300


def test_daytona_runtime_deletes_the_sandbox_when_the_worker_fails() -> None:
    sandbox = FakeSandbox(b"{}", FakeExecResponse(exit_code=2, result="safe summary"))
    client = FakeDaytona(sandbox)
    runtime = DaytonaRuntime(client_factory=lambda: client, worker_archive=b"worker archive")

    with pytest.raises(RuntimeError, match="exit code 2"):
        runtime.run({"diff": "+unsafe"})

    assert client.deleted == [sandbox]


def test_daytona_runtime_builds_sdk_image_with_limited_gateway_access(tmp_path: Path) -> None:
    wheel = tmp_path / "atlan_ai-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    sandbox = FakeSandbox(b'{"decision":"approve"}', FakeExecResponse(exit_code=0))
    client = FakeDaytona(sandbox)
    runtime = DaytonaRuntime(
        client_factory=lambda: client,
        worker_archive=b"worker archive",
        sdk_wheel=wheel,
        allowed_domains=("agentgateway.atlan.engineering",),
        secrets={"ATLAN_API_KEY": "registry-sdk-agent-key"},
    )

    runtime.run({"trace_mode": "sdk"})

    params = client.created_with[0]
    assert isinstance(params, CreateSandboxFromImageParams)
    assert params.network_block_all is False
    assert params.domain_allow_list == "agentgateway.atlan.engineering"
    assert params.secrets == {"ATLAN_API_KEY": "registry-sdk-agent-key"}
    assert isinstance(params.image, Image)
    assert "atlan_ai-0.1.0-py3-none-any.whl" in params.image.dockerfile()
