from __future__ import annotations

from dataclasses import dataclass

DATA_WORKSPACE_ID = "workspace_01m0g43eb2fmgbv21dc7ygs7rc"
LANGGRAPH_FRAMEWORK_ID = "agent_framework_01m09v3ncvey0a4ndx008we9kr"


@dataclass(frozen=True, slots=True)
class DesiredProvider:
    name: str
    provider_type: str


@dataclass(frozen=True, slots=True)
class DesiredEnvironment:
    name: str
    environment_type: str
    network_mode: str
    allowed_hosts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DesiredAgent:
    name: str
    agent_framework_id: str


@dataclass(frozen=True, slots=True)
class DesiredRegistryState:
    workspace_id: str
    provider: DesiredProvider
    environments: tuple[DesiredEnvironment, ...]
    agents: tuple[DesiredAgent, ...]


@dataclass(frozen=True, slots=True)
class RegistryInventory:
    providers: dict[str, str]
    environments: dict[str, str]
    agents: dict[str, str]


@dataclass(frozen=True, slots=True)
class RegistrationAction:
    kind: str
    name: str


def build_desired_registry_state() -> DesiredRegistryState:
    return DesiredRegistryState(
        workspace_id=DATA_WORKSPACE_ID,
        provider=DesiredProvider(name="daytona", provider_type="custom"),
        environments=(
            DesiredEnvironment(
                name="daytona-sdk-pr-review",
                environment_type="cloud",
                network_mode="limited",
                allowed_hosts=("agentgateway.atlan.engineering",),
            ),
            DesiredEnvironment(
                name="daytona-cli-skill-improver",
                environment_type="cloud",
                network_mode="limited",
                allowed_hosts=("agentgateway.atlan.engineering",),
            ),
        ),
        agents=(
            DesiredAgent(
                name="registry-pr-review-sdk",
                agent_framework_id=LANGGRAPH_FRAMEWORK_ID,
            ),
            DesiredAgent(
                name="registry-skill-improver-cli",
                agent_framework_id=LANGGRAPH_FRAMEWORK_ID,
            ),
        ),
    )


def plan_registrations(
    desired: DesiredRegistryState,
    inventory: RegistryInventory,
) -> tuple[RegistrationAction, ...]:
    actions: list[RegistrationAction] = []
    if desired.provider.name not in inventory.providers:
        actions.append(RegistrationAction("agent_provider", desired.provider.name))
    actions.extend(
        RegistrationAction("agent_environment", environment.name)
        for environment in desired.environments
        if environment.name not in inventory.environments
    )
    actions.extend(
        RegistrationAction("agent", agent.name)
        for agent in desired.agents
        if agent.name not in inventory.agents
    )
    return tuple(actions)
