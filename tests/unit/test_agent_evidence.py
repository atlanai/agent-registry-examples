from __future__ import annotations

import json
import urllib.request
from typing import cast

import pytest

from registry_pr_review_demo.agent_evidence import AgentEvidenceClient


def test_agent_evidence_creates_lineage_and_verifies_both_trace_facades() -> None:
    requests: list[tuple[str, str, dict[str, object] | None]] = []

    def send(request: urllib.request.Request, timeout: float) -> bytes:
        assert timeout == 30.0
        body = json.loads(cast(bytes, request.data)) if request.data else None
        requests.append((request.get_method(), request.full_url, body))
        path = request.full_url.removeprefix("https://agentgateway.atlan.engineering")
        if path == "/agent/v1/sessions" and request.get_method() == "POST":
            return b'{"id":"session_demo"}'
        if path == "/agent/v1/outputs" and request.get_method() == "POST":
            return b'{"id":"output_demo"}'
        if path == "/agent/v1/sessions/session_demo":
            return b'{"id":"session_demo","subject_id":"agent_demo"}'
        if path == "/agent/v1/outputs/output_demo":
            return b'{"id":"output_demo","session_id":"session_demo"}'
        if "/traces/" in path:
            return b'{"trace_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
        raise AssertionError(path)

    client = AgentEvidenceClient(
        api_key="agent-secret",
        workspace_id="workspace_demo",
        send=send,
        sleep=lambda _: None,
    )

    session_id, output_id = client.record_and_verify(
        agent_id="agent_demo",
        provider_id="agent_provider_daytona",
        environment_id="agent_environment_kiro",
        external_session_id="github-123-kiro-review",
        sandbox_id="sandbox_demo",
        trace_id="a" * 32,
        skill_ids=["skill_secure", "skill_tests"],
        output_url="https://github.com/atlanai/software-factory-demo/actions/runs/123",
        model_id="auto-selected-model",
        decision="changes_requested",
    )

    assert (session_id, output_id) == ("session_demo", "output_demo")
    session_body = requests[0][2]
    output_body = requests[1][2]
    assert session_body is not None and session_body["subject_id"] == "agent_demo"
    assert session_body["external_session_id"] == "github-123-kiro-review"
    assert output_body is not None and output_body["session_id"] == "session_demo"
    trace_urls = {url for method, url, _ in requests if method == "GET" and "/traces/" in url}
    assert trace_urls == {
        "https://agentgateway.atlan.engineering/agent/v1/agents/agent_demo/traces/" + "a" * 32,
        "https://agentgateway.atlan.engineering/skill/v1/skills/skill_secure/traces/" + "a" * 32,
        "https://agentgateway.atlan.engineering/skill/v1/skills/skill_tests/traces/" + "a" * 32,
    }


def test_agent_evidence_retries_an_eventually_consistent_trace() -> None:
    attempts = 0
    sleeps: list[float] = []

    def send(_request: urllib.request.Request, _timeout: float) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("not indexed yet")
        return b'{"trace_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'

    client = AgentEvidenceClient(
        api_key="agent-secret",
        workspace_id="workspace_demo",
        send=send,
        sleep=sleeps.append,
    )

    client._verify_trace_facades(  # pyright: ignore[reportPrivateUsage]
        agent_id="agent_demo", skill_ids=[], trace_id="b" * 32
    )

    assert attempts == 2
    assert sleeps == [1.0]


def test_agent_evidence_configuration_and_response_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="approved Gateway"):
        AgentEvidenceClient(
            api_key="secret", workspace_id="workspace_demo", base_url="https://example.com"
        )

    monkeypatch.delenv("ATLAN_API_KEY", raising=False)
    monkeypatch.delenv("ATLAN_WORKSPACE_ID", raising=False)
    with pytest.raises(RuntimeError, match="requires ATLAN_API_KEY"):
        AgentEvidenceClient.from_environment()

    client = AgentEvidenceClient(
        api_key="secret",
        workspace_id="workspace_demo",
        send=lambda _request, _timeout: b"not-json",
    )
    with pytest.raises(RuntimeError, match="was not JSON"):
        client._request(  # pyright: ignore[reportPrivateUsage]
            "GET", "/agent/v1/sessions/session_demo"
        )
    with pytest.raises(ValueError, match="fixed API surface"):
        client._request(  # pyright: ignore[reportPrivateUsage]
            "DELETE", "/agent/v1/sessions/session_demo"
        )
