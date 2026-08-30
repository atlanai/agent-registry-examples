# Architecture

The demo proves one mechanism: a Git-authored skill is versioned in Agent Registry, executed by a
LangGraph agent inside Daytona, observed through the Atlan SDK or CLI, and improved from its own
version-scoped trace evidence.

![Registry PR-review topology](images/registry-topology.svg)

## Trust boundaries

The local checkout is the source of truth for both skills, the evaluation cases, and the synthetic
knowledge documents. Registry is the source of truth for published skill versions, agent identity,
sandbox declarations, sessions, outputs, relationships, and trace readback. Daytona executes the
two agents but owns none of those definitions.

Secrets cross only two boundaries:

- The host Daytona API key lives in macOS Keychain and is consumed by the Daytona SDK.
- Each Registry agent API key lives in macOS Keychain and in one host-restricted Daytona Secret.

The repository, command arguments, result files, documentation, and Registry state file contain no
credential values.

## Registered objects

All objects live in the Data workspace `workspace_01m0g43eb2fmgbv21dc7ygs7rc`.

| Kind | Stable name | Purpose |
|---|---|---|
| Agent framework | `langgraph` | Existing seeded framework; reused, not recreated |
| Agent provider | `daytona` | Catalog entry for the external sandbox service |
| Environment | `daytona-sdk-pr-review` | LangGraph plus internal `atlan_ai` wheel |
| Environment | `daytona-cli-skill-improver` | LangGraph plus checksum-pinned Linux `atlanai` |
| Agent | `registry-pr-review-sdk` | Reviews synthetic PR diffs and exports through `atlan_ai` |
| Agent | `registry-skill-improver-cli` | Reads Registry traces, proposes a patch, exports through CLI |
| Skill | `secure-pr-review` | Versioned review policy and deterministic rules |
| Skill | `trace-driven-skill-improvement` | Evidence analysis and approval-gated improvement workflow |

The agents are peers. Neither is registered as the other's sub-agent. Each has one `uses_skill`
relationship to its governing skill.

## Execution packages

The SDK agent image installs:

- Python 3.12;
- `langgraph==1.2.11`;
- the checksum-verified internal `atlan_ai==0.1.0` wheel;
- the review worker zipapp.

The CLI agent image installs Python and LangGraph, then embeds `atlanai` 0.3.53 for Linux AMD64.
The binary is downloaded from Atlan's signed preview manifest and checked against
`2de549a7f584f748f8e082e7c88b18a0e916ef3051f06be2aeddfefa6b13ea59` before use.

Both sandboxes are ephemeral. Runtime egress is limited to `agentgateway.atlan.engineering` and
every cleanup path deletes the sandbox.

## Attribution

The SDK reviewer uses its Registry agent key as `ATLAN_API_KEY`. The CLI improver uses its own key
as `ATLANAI_TOKEN`. Gateway-authenticated identity therefore scopes each agent trace; an arbitrary
payload attribute cannot claim another agent.

The skill invocation span carries the exact Registry fingerprints:

```text
atlan.skill.name
atlan.skill.version
atlan.skill.source_digest
atlan.skill.skillmd_sha256
atlan.skill.fingerprint_source=registry
atlan.registry.skill.version_ordinal
```

Raw diffs and knowledge contents are not stored in the trace. The evaluation case id, expected
decision, actual decision, finding count, and matched rule ids are enough to diagnose the synthetic
failure.

## Storage and readback

OTLP ingest acknowledges durable handoff before asynchronous ClickHouse projection. Verification
therefore distinguishes three states: ingest accepted, projected trace found, and subject/skill
facade attribution confirmed. A two-minute bounded poll handles projection lag; expiry is reported
as partial verification rather than silently retried forever.

