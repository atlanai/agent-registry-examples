from __future__ import annotations

from registry_pr_review_demo.registration import (
    DATA_WORKSPACE_ID,
    LANGGRAPH_FRAMEWORK_ID,
    RegistryInventory,
    build_desired_registry_state,
    plan_registrations,
)


def test_desired_state_uses_data_workspace_and_reuses_langgraph_framework() -> None:
    desired = build_desired_registry_state()

    assert desired.workspace_id == DATA_WORKSPACE_ID
    assert desired.provider.name == "daytona"
    assert {environment.name for environment in desired.environments} == {
        "daytona-sdk-pr-review",
        "daytona-cli-skill-improver",
        "daytona-kiro-pr-review",
    }
    assert {agent.name for agent in desired.agents} == {
        "pr-review-agent",
        "registry-skill-improver-cli",
        "kiro-pr-review-agent",
    }
    assert {
        agent.name for agent in desired.agents if agent.agent_framework_id == LANGGRAPH_FRAMEWORK_ID
    } == {"pr-review-agent", "registry-skill-improver-cli"}


def test_registration_plan_creates_only_missing_objects() -> None:
    desired = build_desired_registry_state()
    inventory = RegistryInventory(
        providers={"daytona": "agent_provider_existing"},
        environments={},
        agents={"pr-review-agent": "agent_existing"},
    )

    actions = plan_registrations(desired, inventory)

    assert [(action.kind, action.name) for action in actions] == [
        ("agent_environment", "daytona-sdk-pr-review"),
        ("agent_environment", "daytona-cli-skill-improver"),
        ("agent_environment", "daytona-kiro-pr-review"),
        ("agent", "registry-skill-improver-cli"),
        ("agent", "kiro-pr-review-agent"),
    ]
