from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from registry_pr_review_demo.cli_trace import CliCommandResult, run_atlanai_cli

MAX_RESPONSE_BYTES = 4_000_000
GATEWAY_HOST = "agentgateway.atlan.engineering"


def _default_send(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Atlan evidence response exceeds the 4 MB limit")
    return content


class AgentEvidenceClient:
    """Create agent-scoped run lineage and fail closed on trace-facade gaps."""

    def __init__(
        self,
        *,
        api_key: str,
        workspace_id: str,
        base_url: str = "https://agentgateway.atlan.engineering",
        send: Callable[[urllib.request.Request, float], bytes] = _default_send,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https" or parsed.hostname != GATEWAY_HOST:
            raise ValueError("Atlan evidence client requires the approved Gateway host")
        if not api_key or not workspace_id:
            raise ValueError("Agent API key and workspace id are required")
        self._api_key = api_key
        self._workspace_id = workspace_id
        self._base_url = base_url.rstrip("/")
        self._send = send
        self._sleep = sleep

    @classmethod
    def from_environment(cls) -> AgentEvidenceClient:
        api_key = os.environ.get("ATLAN_API_KEY")
        workspace_id = os.environ.get("ATLAN_WORKSPACE_ID")
        if not api_key or not workspace_id:
            raise RuntimeError("Agent evidence requires ATLAN_API_KEY and ATLAN_WORKSPACE_ID")
        return cls(
            api_key=api_key,
            workspace_id=workspace_id,
            base_url=os.environ.get("ATLAN_BASE_URL", "https://agentgateway.atlan.engineering"),
        )

    def record_and_verify(
        self,
        *,
        agent_id: str,
        provider_id: str,
        environment_id: str,
        external_session_id: str,
        sandbox_id: str,
        trace_id: str,
        skill_ids: Sequence[str],
        output_url: str,
        model_id: str | None,
        decision: str,
        runtime: str = "kiro",
    ) -> tuple[str, str]:
        display_runtime = "LangGraph" if runtime == "langgraph" else "Kiro"
        session = self._request(
            "POST",
            "/agent/v1/sessions",
            {
                "name": _artifact_name(f"{runtime}-pr-review", external_session_id),
                "display_name": f"{display_runtime} PR Review",
                "description": f"Sanitized review evidence: {decision}.",
                "workspace_id": self._workspace_id,
                "subject_kind": "agent",
                "subject_id": agent_id,
                "session_status": "completed",
                "external_session_id": external_session_id,
                "remote_session_id": sandbox_id,
                "agent_provider_id": provider_id,
                "environment_id": environment_id,
                "model_id": model_id,
                "stop_reason": "final_answer",
                "title": "Synthetic risky order-service patch",
            },
        )
        session_id = _string(session, "id")
        output = self._request(
            "POST",
            "/agent/v1/outputs",
            {
                "name": _artifact_name(f"{runtime}-pr-review-result", external_session_id),
                "display_name": f"{display_runtime} PR Review Result",
                "description": "Sanitized GitHub Actions review artifact and trace lineage.",
                "workspace_id": self._workspace_id,
                "mode": "link",
                "external_url": output_url,
                "subject_kind": "agent",
                "subject_id": agent_id,
                "session_id": session_id,
            },
        )
        output_id = _string(output, "id")
        self._verify_trace_facades(agent_id=agent_id, skill_ids=skill_ids, trace_id=trace_id)
        session_readback = self._request("GET", f"/agent/v1/sessions/{session_id}")
        output_readback = self._request("GET", f"/agent/v1/outputs/{output_id}")
        if session_readback.get("subject_id") != agent_id:
            raise RuntimeError("Atlan Session readback lost Agent identity")
        if output_readback.get("session_id") != session_id:
            raise RuntimeError("Atlan Output readback lost Session lineage")
        return session_id, output_id

    def _verify_trace_facades(
        self, *, agent_id: str, skill_ids: Sequence[str], trace_id: str
    ) -> None:
        paths = [f"/agent/v1/agents/{agent_id}/traces/{trace_id}"]
        paths.extend(f"/skill/v1/skills/{skill_id}/traces/{trace_id}" for skill_id in skill_ids)
        pending = list(paths)
        for delay in (0.0, 1.0, 2.0, 4.0):
            if delay:
                self._sleep(delay)
            failures: list[str] = []
            for path in pending:
                try:
                    response = self._request("GET", path)
                    if response.get("trace_id") != trace_id:
                        failures.append(path)
                except RuntimeError:
                    failures.append(path)
            pending = failures
            if not pending:
                return
        raise RuntimeError("Atlan trace is incomplete across Agent and Skill facades")

    def _request(
        self, method: str, path: str, body: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        parsed_path = urllib.parse.urlparse(path)
        if method not in {"GET", "POST"} or parsed_path.scheme or not path.startswith("/"):
            raise ValueError("Atlan evidence request is outside the fixed API surface")
        data = (
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
            if body is not None
            else None
        )
        request = urllib.request.Request(  # noqa: S310 - fixed approved base URL
            f"{self._base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "X-Atlan-Workspace-Id": self._workspace_id,
            },
        )
        try:
            raw = self._send(request, 30.0)
        except Exception as error:
            raise RuntimeError("Atlan evidence request failed") from error
        try:
            payload: object = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Atlan evidence response was not JSON") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Atlan evidence response must be an object")
        return {str(key): value for key, value in cast(dict[object, object], payload).items()}


class CliAgentEvidenceClient(AgentEvidenceClient):
    """Use the CLI's API-key exchange path for Agent-authenticated evidence calls."""

    def __init__(
        self,
        *,
        workspace_id: str,
        runner: Callable[[Sequence[str]], CliCommandResult] = run_atlanai_cli,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(
            api_key="cli-managed-agent-credential",
            workspace_id=workspace_id,
            sleep=sleep,
        )
        self._runner = runner

    @classmethod
    def from_environment(cls) -> CliAgentEvidenceClient:
        if not os.environ.get("ATLANAI_TOKEN"):
            raise RuntimeError("Agent evidence requires ATLANAI_TOKEN")
        workspace_id = os.environ.get("ATLAN_WORKSPACE_ID")
        if not workspace_id:
            raise RuntimeError("Agent evidence requires ATLAN_WORKSPACE_ID")
        return cls(workspace_id=workspace_id)

    def _request(
        self, method: str, path: str, body: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        if method not in {"GET", "POST"} or not path.startswith("/"):
            raise ValueError("Atlan evidence request is outside the fixed API surface")
        arguments: list[str] = ["atlanai", "api", method.lower(), path]
        temporary_path: Path | None = None
        if body is not None:
            fd, raw_path = tempfile.mkstemp(prefix="agent-evidence-", suffix=".json")
            temporary_path = Path(raw_path)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(body, handle, separators=(",", ":"), sort_keys=True)
            arguments.extend(("--input", str(temporary_path)))
        arguments.extend(("-H", f"X-Atlan-Workspace-Id:{self._workspace_id}"))
        try:
            result = self._runner(tuple(arguments))
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        if result.exit_code != 0:
            raise RuntimeError("Atlan CLI evidence request failed")
        try:
            payload: object = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Atlan CLI evidence response was not JSON") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Atlan CLI evidence response must be an object")
        return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _artifact_name(prefix: str, external_session_id: str) -> str:
    safe = "".join(character if character.isalnum() else "-" for character in external_session_id)
    return f"{prefix}-{safe}"[:120].strip("-")


def _string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Atlan evidence response is missing {key}")
    return value
