from __future__ import annotations

from dataclasses import dataclass

DATA_WORKSPACE_ID = "workspace_01m0g43eb2fmgbv21dc7ygs7rc"
LANGGRAPH_FRAMEWORK_ID = "agent_framework_01m09v3ncvey0a4ndx008we9kr"
KIRO_FRAMEWORK_NAME = "kiro-cli"


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
    agent_framework_id: str | None
    agent_framework_name: str | None = None


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
            DesiredEnvironment(
                name="daytona-kiro-pr-review",
                environment_type="cloud",
                network_mode="limited",
                allowed_hosts=(
                    "agentgateway.atlan.engineering",
                    "releases.atlan.com",
                    "app.kiro.dev",
                    "assets.app.kiro.dev",
                    "cognito-identity.us-east-1.amazonaws.com",
                    "oidc.us-east-1.amazonaws.com",
                    "prod.us-east-1.auth.desktop.kiro.dev",
                    "prod.us-east-1.telemetry.desktop.kiro.dev",
                    "prod.download.desktop.kiro.dev",
                    "q.us-east-1.amazonaws.com",
                    "q.eu-central-1.amazonaws.com",
                    "runtime.us-east-1.kiro.dev",
                    "runtime.eu-central-1.kiro.dev",
                    "management.us-east-1.kiro.dev",
                    "management.eu-central-1.kiro.dev",
                    "telemetry.us-east-1.kiro.dev",
                    "telemetry.eu-central-1.kiro.dev",
                ),
            ),
        ),
        agents=(
            DesiredAgent(
                name="pr-review-agent",
                agent_framework_id=LANGGRAPH_FRAMEWORK_ID,
            ),
            DesiredAgent(
                name="registry-skill-improver-cli",
                agent_framework_id=LANGGRAPH_FRAMEWORK_ID,
            ),
            DesiredAgent(
                name="kiro-pr-review-agent-api",
                agent_framework_id=None,
                agent_framework_name=KIRO_FRAMEWORK_NAME,
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
