from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from daytona import CreateSandboxFromImageParams

from registry_pr_review_demo.kiro_runtime import KiroDaytonaRuntime, parse_kiro_stream


def kiro_result() -> dict[str, object]:
    return {
        "decision": "changes_requested",
        "findings": [
            {
                "rule_id": "parameterize-sql",
                "severity": "high",
                "message": "Use a parameterized query.",
                "line": 7,
            }
        ],
        "skills_used": [{"id": "skill_review", "version": 1, "source_digest": "a" * 64}],
    }


def stream_for(result: dict[str, object]) -> str:
    return "\n".join(
        [
            json.dumps({"type": "tool_call", "tool_name": "read"}),
            json.dumps({"type": "tool_call", "tool_name": "grep"}),
            json.dumps({"type": "result", "model": "auto-selected-model", "result": result}),
        ]
    )


def test_parse_kiro_stream_returns_validated_result_and_tools() -> None:
    result, tools = parse_kiro_stream(stream_for(kiro_result()))

    assert result["decision"] == "changes_requested"
    assert result["model"] == "auto-selected-model"
    assert tools == ("read", "grep")


def test_parse_current_v3_stream_reads_fenced_result_and_sanitized_tools() -> None:
    result = kiro_result()
    stream = "\n".join(
        [
            json.dumps(
                {
                    "type": "sessionUpdate",
                    "data": {
                        "update": {
                            "_meta": {
                                "kiro": {
                                    "breakdown": {"tools": {"tokens": 5291}},
                                    "promptTurnSummaries": [
                                        {
                                            "usage": 0.3443911164179104,
                                            "usedTools": [
                                                "read_file",
                                                "file_search",
                                                "list_directory",
                                                "grep_search",
                                                "disclose_context",
                                                "read_file",
                                            ],
                                        }
                                    ],
                                }
                            }
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "type": "runFinished",
                    "data": {
                        "status": "success",
                        "finalText": f"```json\n{json.dumps(result)}\n```",
                    },
                }
            ),
        ]
    )

    parsed, tools = parse_kiro_stream(stream)

    assert parsed["decision"] == "changes_requested"
    assert parsed["kiro_tool_tokens"] == 5291
    assert parsed["kiro_credits_used"] == pytest.approx(0.3443911164179104)
    assert tools == ("read", "glob", "grep", "disclose_context")


@pytest.mark.parametrize(
    ("stream", "message"),
    [
        ('{"type":"tool_call","tool_name":"shell"}', "disallowed tool"),
        ('{"type":"result","result":{"decision":"approve"}}', "findings"),
        ("not-json", "invalid JSON"),
    ],
)
def test_parse_kiro_stream_fails_closed(stream: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_kiro_stream(stream)


@dataclass
class FakeResponse:
    exit_code: int
    result: str = ""


class FakeFileSystem:
    def __init__(self, traced_result: bytes) -> None:
        self.traced_result = traced_result
        self.uploads: list[tuple[bytes, str]] = []

    def upload_file(self, file: bytes, remote_path: str) -> None:
        self.uploads.append((file, remote_path))

    def download_file(self, remote_path: str) -> bytes:
        assert remote_path == "/workspace/result.json"
        return self.traced_result


class FakeProcess:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.commands: list[tuple[str, str | None, dict[str, str] | None, int | None]] = []

    def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> FakeResponse:
        self.commands.append((command, cwd, env, timeout))
        return self.responses.pop(0)


class FakeSandbox:
    def __init__(self, responses: list[FakeResponse], traced_result: bytes) -> None:
        self.id = "sandbox_kiro_demo"
        self.fs = FakeFileSystem(traced_result)
        self.process = FakeProcess(responses)


class FakeDaytona:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.created_with: list[object] = []
        self.deleted: list[FakeSandbox] = []

    def create(self, params: object) -> FakeSandbox:
        self.created_with.append(params)
        return self.sandbox

    def delete(self, sandbox: object) -> None:
        assert isinstance(sandbox, FakeSandbox)
        self.deleted.append(sandbox)


def test_kiro_daytona_runtime_is_read_only_traced_and_ephemeral(tmp_path: Path) -> None:
    kiro = tmp_path / "kiro-cli"
    cli = tmp_path / "atlanai"
    wheel = tmp_path / "atlan_ai-0.1.0-py3-none-any.whl"
    kiro.write_bytes(b"binary")
    kiro.with_name("kiro-cli-chat").write_bytes(b"chat")
    kiro.with_name("kiro-cli-term").write_bytes(b"term")
    cli.write_bytes(b"cli")
    wheel.write_bytes(b"wheel")
    traced = {**kiro_result(), "trace_id": "b" * 32}
    sandbox = FakeSandbox(
        [FakeResponse(0, stream_for(kiro_result())), FakeResponse(0)],
        json.dumps(traced).encode(),
    )
    daytona = FakeDaytona(sandbox)
    runtime = KiroDaytonaRuntime(
        kiro_binary=kiro,
        cli_binary=cli,
        worker_archive=b"worker",
        sdk_wheel=wheel,
        workspace_files={
            "/workspace/change.diff": b"synthetic patch",
            "/workspace/.kiro/agents/pr-review.json": b"agent",
        },
        secrets={
            "ATLAN_API_KEY": "kiro-pr-review-agent-key",
            "ATLANAI_TOKEN": "kiro-pr-review-agent-key",
            "KIRO_API_KEY": "kiro-api-key",
        },
        allowed_domains=("agentgateway.atlan.engineering", "runtime.us-east-1.kiro.dev"),
        workspace_id="workspace_demo",
        client_factory=lambda: daytona,
    )

    result = runtime.run(
        {
            "agent_id": "agent_kiro",
            "session_id": "session_kiro",
            "skills": [],
            "attributes": {},
        }
    )

    assert result["trace_id"] == "b" * 32
    assert result["agent_id"] == "agent_kiro"
    assert result["daytona_sandbox_id"] == "sandbox_kiro_demo"
    assert result["daytona_sandbox_lifecycle"] == "deleted_after_run"
    params = daytona.created_with[0]
    assert isinstance(params, CreateSandboxFromImageParams)
    assert params.ephemeral is True
    assert params.secrets == {
        "ATLAN_API_KEY": "kiro-pr-review-agent-key",
        "ATLANAI_TOKEN": "kiro-pr-review-agent-key",
        "KIRO_API_KEY": "kiro-api-key",
    }
    assert daytona.deleted == [sandbox]
    command = sandbox.process.commands[0][0]
    assert "--agent-engine v3" in command
    assert "--trust-all-tools" in command
    assert "synthetic patch" not in command
    assert {path for _, path in sandbox.fs.uploads} >= {
        "/workspace/agent.pyz",
        "/workspace/change.diff",
        "/workspace/.kiro/agents/pr-review.json",
        "/workspace/trace-request.json",
    }
    trace_request = next(
        json.loads(content)
        for content, path in sandbox.fs.uploads
        if path == "/workspace/trace-request.json"
    )
    assert trace_request["attributes"]["daytona.sandbox.id"] == "sandbox_kiro_demo"


def test_kiro_daytona_runtime_deletes_sandbox_on_kiro_failure(tmp_path: Path) -> None:
    kiro = tmp_path / "kiro-cli"
    cli = tmp_path / "atlanai"
    wheel = tmp_path / "atlan_ai.whl"
    kiro.write_bytes(b"binary")
    kiro.with_name("kiro-cli-chat").write_bytes(b"chat")
    kiro.with_name("kiro-cli-term").write_bytes(b"term")
    cli.write_bytes(b"cli")
    wheel.write_bytes(b"wheel")
    sandbox = FakeSandbox([FakeResponse(3)], b"{}")
    daytona = FakeDaytona(sandbox)
    runtime = KiroDaytonaRuntime(
        kiro_binary=kiro,
        cli_binary=cli,
        worker_archive=b"worker",
        sdk_wheel=wheel,
        workspace_files={"/workspace/change.diff": b"safe"},
        secrets={
            "ATLAN_API_KEY": "agent-key",
            "ATLANAI_TOKEN": "agent-key",
            "KIRO_API_KEY": "kiro-key",
        },
        allowed_domains=("agentgateway.atlan.engineering",),
        workspace_id="workspace_demo",
        client_factory=lambda: daytona,
    )

    with pytest.raises(RuntimeError, match="exit code 3"):
        runtime.run({"agent_id": "agent_kiro", "session_id": "session_kiro"})

    assert daytona.deleted == [sandbox]
