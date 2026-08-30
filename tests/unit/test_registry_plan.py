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
    }
    assert {agent.name for agent in desired.agents} == {
        "registry-pr-review-sdk",
        "registry-skill-improver-cli",
    }
    assert all(agent.agent_framework_id == LANGGRAPH_FRAMEWORK_ID for agent in desired.agents)


def test_registration_plan_creates_only_missing_objects() -> None:
    desired = build_desired_registry_state()
    inventory = RegistryInventory(
        providers={"daytona": "agent_provider_existing"},
        environments={},
        agents={"registry-pr-review-sdk": "agent_existing"},
    )

    actions = plan_registrations(desired, inventory)

    assert [(action.kind, action.name) for action in actions] == [
        ("agent_environment", "daytona-sdk-pr-review"),
        ("agent_environment", "daytona-cli-skill-improver"),
        ("agent", "registry-skill-improver-cli"),
    ]
