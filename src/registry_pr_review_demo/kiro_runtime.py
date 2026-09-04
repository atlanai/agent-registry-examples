from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

from daytona import CreateSandboxFromImageParams, Daytona, Image

MAX_STREAM_BYTES = 4_000_000
MAX_STREAM_EVENTS = 2_000
MAX_TOOL_EVENTS = 100
ALLOWED_KIRO_TOOLS = frozenset(
    {
        "read",
        "read_file",
        "fs_read",
        "fsRead",
        "grep",
        "grep_search",
        "glob",
        "list_directory",
        "file_search",
        "disclose_context",
    }
)
KIRO_TOOL_NAMES = {
    "read_file": "read",
    "fs_read": "read",
    "fsRead": "read",
    "grep_search": "grep",
    "list_directory": "glob",
    "file_search": "glob",
}


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
    def id(self) -> str: ...

    @property
    def fs(self) -> SandboxFileSystem: ...

    @property
    def process(self) -> SandboxProcess: ...


class DaytonaClient(Protocol):
    def create(self, params: object) -> Sandbox: ...

    def delete(self, sandbox: Sandbox) -> None: ...


def parse_kiro_stream(raw: str) -> tuple[dict[str, object], tuple[str, ...]]:
    if len(raw.encode("utf-8")) > MAX_STREAM_BYTES:
        raise ValueError("Kiro stream exceeds the 4 MB limit")
    events: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if len(events) >= MAX_STREAM_EVENTS:
            raise ValueError("Kiro stream has too many events")
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("Kiro stream contains invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("Kiro stream events must be objects")
        events.append({str(key): item for key, item in cast(dict[object, object], value).items()})

    tool_names: list[str] = []
    final: object | None = None
    model: str | None = None
    kiro_tool_tokens = 0
    kiro_credits_used = 0.0
    for event in events:
        raw_model = event.get("model", event.get("model_id"))
        if isinstance(raw_model, str) and 0 < len(raw_model) <= 200:
            model = raw_model
        event_type = event.get("type")
        if event_type in {"tool_call", "tool_use", "ToolCall"}:
            raw_name = event.get("tool_name", event.get("name"))
            if isinstance(raw_name, str):
                if raw_name not in ALLOWED_KIRO_TOOLS:
                    raise ValueError(f"Kiro used disallowed tool {raw_name!r}")
                if len(tool_names) >= MAX_TOOL_EVENTS:
                    raise ValueError("Kiro stream has too many tool events")
                tool_names.append(raw_name)
        if event_type == "sessionUpdate":
            data = event.get("data")
            if isinstance(data, dict):
                update = cast(dict[str, object], data).get("update")
                if isinstance(update, dict):
                    meta = cast(dict[str, object], update).get("_meta")
                    if isinstance(meta, dict):
                        kiro = cast(dict[str, object], meta).get("kiro")
                        if isinstance(kiro, dict):
                            typed_kiro = cast(dict[str, object], kiro)
                            breakdown = typed_kiro.get("breakdown")
                            if isinstance(breakdown, dict):
                                tools = cast(dict[str, object], breakdown).get("tools")
                                if isinstance(tools, dict):
                                    raw_tokens = cast(dict[str, object], tools).get("tokens")
                                    if (
                                        isinstance(raw_tokens, int)
                                        and not isinstance(raw_tokens, bool)
                                        and raw_tokens >= 0
                                    ):
                                        kiro_tool_tokens = raw_tokens
                            summaries = typed_kiro.get("promptTurnSummaries", [])
                            if isinstance(summaries, list):
                                snapshot_credits = 0.0
                                for summary in cast(list[object], summaries):
                                    if not isinstance(summary, dict):
                                        continue
                                    typed_summary = cast(dict[str, object], summary)
                                    raw_usage = typed_summary.get("usage")
                                    if (
                                        isinstance(raw_usage, (int, float))
                                        and not isinstance(raw_usage, bool)
                                        and raw_usage >= 0
                                    ):
                                        snapshot_credits += float(raw_usage)
                                    used = typed_summary.get("usedTools", [])
                                    if isinstance(used, list):
                                        for raw_name in cast(list[object], used):
                                            if isinstance(raw_name, str):
                                                tool_names.append(raw_name)
                                if snapshot_credits > 0:
                                    kiro_credits_used = snapshot_credits
        if event_type in {"result", "assistant", "TurnEnd"}:
            final = event.get("result", event.get("content", event.get("output")))
        if event_type == "runFinished":
            data = event.get("data")
            if isinstance(data, dict):
                final = cast(dict[str, object], data).get("finalText")
    if final is None:
        raise ValueError("Kiro stream omitted a final result")
    if isinstance(final, str):
        try:
            final = json.loads(final)
        except json.JSONDecodeError:
            fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", final, re.DOTALL)
            if fence is None:
                raise ValueError("Kiro final result is not JSON") from None
            try:
                final = json.loads(fence.group(1))
            except json.JSONDecodeError as error:
                raise ValueError("Kiro final result is not JSON") from error
    result = _object(final, "Kiro final result")
    _validate_result(result)
    if model is not None:
        result["model"] = model
    result["kiro_tool_tokens"] = kiro_tool_tokens
    result["kiro_credits_used"] = kiro_credits_used
    normalized_tools: list[str] = []
    for tool_name in tool_names:
        if tool_name not in ALLOWED_KIRO_TOOLS:
            raise ValueError(f"Kiro used disallowed tool {tool_name!r}")
        normalized = KIRO_TOOL_NAMES.get(tool_name, tool_name)
        if normalized not in normalized_tools:
            normalized_tools.append(normalized)
        if len(normalized_tools) > MAX_TOOL_EVENTS:
            raise ValueError("Kiro stream has too many tool events")
    return result, tuple(normalized_tools)


def _validate_result(result: Mapping[str, object]) -> None:
    decision = result.get("decision")
    if decision not in {"approve", "comment", "changes_requested"}:
        raise ValueError("Kiro returned an unknown review decision")
    findings = result.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Kiro findings must be an array")
    for raw in cast(list[object], findings):
        finding = _object(raw, "Kiro finding")
        if not isinstance(finding.get("rule_id"), str):
            raise ValueError("Kiro finding is missing rule_id")
        if finding.get("severity") not in {"low", "medium", "high", "critical"}:
            raise ValueError("Kiro finding has an unknown severity")
        line = finding.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise ValueError("Kiro finding requires a positive diff line")
        if not isinstance(finding.get("message"), str):
            raise ValueError("Kiro finding is missing message")
    skills = result.get("skills_used")
    if not isinstance(skills, list) or not skills:
        raise ValueError("Kiro result requires verified skills_used")
    for raw in cast(list[object], skills):
        skill = _object(raw, "Kiro skill")
        if not isinstance(skill.get("id"), str) or not str(skill["id"]).startswith("skill_"):
            raise ValueError("Kiro skill has an invalid Registry id")
        version = skill.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Kiro skill has an invalid Registry version")
        digest = skill.get("source_digest")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Kiro skill has an invalid source digest")


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


class KiroDaytonaRuntime:
    """Runs a read-only Kiro review and agent-authenticated trace worker in Daytona."""

    def __init__(
        self,
        *,
        kiro_binary: Path,
        cli_binary: Path,
        worker_archive: bytes,
        sdk_wheel: Path,
        workspace_files: Mapping[str, bytes],
        secrets: Mapping[str, str],
        allowed_domains: tuple[str, ...],
        workspace_id: str,
        raw_agent_key: str | None = None,
        client_factory: Callable[[], DaytonaClient] | None = None,
    ) -> None:
        self._kiro_binary = kiro_binary
        self._cli_binary = cli_binary
        self._worker_archive = worker_archive
        self._sdk_wheel = sdk_wheel
        self._workspace_files = dict(workspace_files)
        self._secrets = dict(secrets)
        self._allowed_domains = allowed_domains
        self._workspace_id = workspace_id
        self._raw_agent_key = raw_agent_key
        self._client_factory = client_factory or cast(Callable[[], DaytonaClient], Daytona)
        expected_secrets = (
            {"KIRO_API_KEY"}
            if self._raw_agent_key
            else {"ATLAN_API_KEY", "ATLANAI_TOKEN", "KIRO_API_KEY"}
        )
        if set(self._secrets) != expected_secrets:
            raise ValueError("Kiro Daytona runtime requires REST, CLI, and Kiro secret mappings")
        if not self._workspace_id.startswith("workspace_"):
            raise ValueError("Kiro Daytona runtime requires a Registry workspace id")
        if any(not re.fullmatch(r"[a-z0-9.-]+", domain) for domain in allowed_domains):
            raise ValueError("Kiro Daytona domain allowlist contains an invalid hostname")
        for remote_path in self._workspace_files:
            path = PurePosixPath(remote_path)
            if (
                not path.is_absolute()
                or not path.is_relative_to("/workspace")
                or ".." in path.parts
            ):
                raise ValueError("Kiro workspace files must stay under /workspace")

    def run(self, trace_payload: Mapping[str, object]) -> dict[str, object]:
        client = self._client_factory()
        kiro_chat = self._kiro_binary.with_name("kiro-cli-chat")
        kiro_term = self._kiro_binary.with_name("kiro-cli-term")
        if not kiro_chat.is_file() or not kiro_term.is_file():
            raise RuntimeError("Complete Kiro three-binary runtime is required")
        wheel_remote = f"/opt/software-factory/{self._sdk_wheel.name}"
        image = (
            Image.debian_slim("3.12")
            .add_local_file(self._kiro_binary, "/usr/local/bin/kiro-cli")
            .add_local_file(kiro_chat, "/usr/local/bin/kiro-cli-chat")
            .add_local_file(kiro_term, "/usr/local/bin/kiro-cli-term")
            .add_local_file(self._cli_binary, "/usr/local/bin/atlanai")
            .add_local_file(self._sdk_wheel, wheel_remote)
            .run_commands(
                "chmod 0755 /usr/local/bin/kiro-cli",
                "chmod 0755 /usr/local/bin/kiro-cli-chat /usr/local/bin/kiro-cli-term",
                "chmod 0755 /usr/local/bin/atlanai",
                f"python -m pip install {wheel_remote}",
            )
        )
        env_vars = {
            "ATLAN_BASE_URL": "https://agentgateway.atlan.engineering",
            "ATLANAI_GATEWAY_URL": "https://agentgateway.atlan.engineering",
            "ATLAN_TRACE_CONTENT": "false",
            "ATLAN_WORKSPACE_ID": self._workspace_id,
        }
        if self._raw_agent_key:
            env_vars["ATLAN_API_KEY"] = self._raw_agent_key
            env_vars["ATLANAI_TOKEN"] = self._raw_agent_key
        params = CreateSandboxFromImageParams(
            image=image,
            language="python",
            ephemeral=True,
            auto_stop_interval=5,
            network_block_all=False,
            domain_allow_list=",".join(self._allowed_domains),
            secrets=self._secrets,
            labels={"purpose": "software-factory-kiro-review"},
            env_vars=env_vars,
        )
        sandbox = client.create(params)
        try:
            if not sandbox.id:
                raise RuntimeError("Daytona did not return a sandbox id")
            sandbox.fs.upload_file(self._worker_archive, "/workspace/agent.pyz")
            for remote_path, content in self._workspace_files.items():
                sandbox.fs.upload_file(content, remote_path)
            response = sandbox.process.exec(
                (
                    "/usr/local/bin/kiro-cli chat --agent-engine v3 --agent pr-review "
                    "--no-interactive --trust-all-tools "
                    "--output-format stream-json "
                    '"Read /workspace/review-contract.json, then review /workspace/change.diff '
                    "using every configured review skill. Return only the required JSON evidence "
                    'object with the exact Registry skill fingerprints from the contract."'
                ),
                cwd="/workspace",
                env={"KIRO_HOME": "/workspace/.kiro-home"},
                timeout=300,
            )
            if response.exit_code != 0:
                raise RuntimeError(f"Kiro review failed with exit code {response.exit_code}")
            result, tools = parse_kiro_stream(response.result or "")
            request = dict(trace_payload)
            raw_attributes = request.get("attributes", {})
            attributes = _object(raw_attributes, "trace attributes")
            attributes["daytona.sandbox.id"] = sandbox.id
            request.update({"job_type": "kiro_trace", "result": result, "tool_names": list(tools)})
            request["attributes"] = attributes
            sandbox.fs.upload_file(
                json.dumps(request, separators=(",", ":"), sort_keys=True).encode(),
                "/workspace/trace-request.json",
            )
            traced = sandbox.process.exec(
                (
                    "python /workspace/agent.pyz --request /workspace/trace-request.json "
                    "--output /workspace/result.json"
                ),
                cwd="/workspace",
                env={"PYTHONDONTWRITEBYTECODE": "1"},
                timeout=120,
            )
            if traced.exit_code != 0:
                raise RuntimeError(f"Atlan trace worker failed with exit code {traced.exit_code}")
            traced_result = json.loads(sandbox.fs.download_file("/workspace/result.json"))
            output = _object(traced_result, "Kiro traced result")
            agent_id = trace_payload.get("agent_id")
            if not isinstance(agent_id, str) or not agent_id.startswith("agent_"):
                raise RuntimeError("Kiro trace payload is missing Agent identity")
            output["agent_id"] = agent_id
            output["daytona_sandbox_id"] = sandbox.id
            output["daytona_sandbox_lifecycle"] = "deleted_after_run"
            return output
        finally:
            client.delete(sandbox)
