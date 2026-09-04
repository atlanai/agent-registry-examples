# Customer demo: governed software factory

This walkthrough tells one story: a software change enters GitHub, two independent reviewers apply
the same governed skills inside Daytona, and Atlan ties the code, Agent identities, skill versions,
and runtime evidence together.

The repository is customer-neutral. The product under review is a synthetic order service; no
customer code, tenant names, or production data appear in the demo.

## What the customer should believe

GitHub remains the source of change. Atlan registers who and what is allowed to review that change.
Daytona provides the isolated execution boundary. LangGraph and Kiro can use different agent
implementations without drifting from the same review policy.

The proof is inspectable:

- product code and the proposed patch are separate;
- three Git-authored skills have immutable Registry IDs and digests;
- each Agent has its own machine identity and the same three `uses_skill` relationships;
- the Kiro and LangGraph runtime paths fail closed when identity or telemetry is incomplete;
- the trace-improvement Agent proposes changes but cannot publish them.

## Presenter preflight

Open these tabs before the call. Keep them in this order.

1. [Repository home](https://github.com/atlanai/software-factory-demo)
2. [Order-service code](https://github.com/atlanai/software-factory-demo/tree/main/software/order-service)
3. [Risky proposed diff](https://github.com/atlanai/software-factory-demo/blob/main/factory/fixtures/risky-order-change.diff)
4. [Shared skills](https://github.com/atlanai/software-factory-demo/tree/main/skills)
5. [LangGraph Agent](https://github.com/atlanai/software-factory-demo/tree/main/agents/pr-review-agent)
6. [Kiro Agent](https://github.com/atlanai/software-factory-demo/tree/main/agents/kiro-pr-review-agent)
7. [SkillSync workflow](https://github.com/atlanai/software-factory-demo/actions/workflows/atlan-skill-sync.yml)
8. [Daytona sandboxes](https://app.daytona.io/dashboard/sandboxes)
9. [Engineering PR Review Agent in Atlan](atlan://open/orgs/atlan-internal/brain/agent/agent_01m1pn4k5deggsts6h7fvfvcgx)
10. [Secure PR Review skill](atlan://open/orgs/atlan-internal/brain/skill/skill_01m1pn0115ee19gjbzdjxdrady)
11. [Test Impact Analysis skill](atlan://open/orgs/atlan-internal/brain/skill/skill_01m1pn011df01a85dyc5ztjk5h)
12. [Review Evidence Summary skill](atlan://open/orgs/atlan-internal/brain/skill/skill_01m1pn0110fz9b869ddyc00sh6)

## The story, one tab at a time

### 1. Start with the factory, not the Registry

Open the repository home. Point out the top-level folders before discussing Agents:

```text
software/   the product being changed
factory/    the proposed change and evaluation inputs
skills/     versioned engineering policy
agents/     independent implementations
registry/   immutable IDs and resolved fingerprints
docs/       operating model and demo evidence
```

Say: “This is an ordinary software repository with an AI review layer, not an AI showcase with
some sample code attached.”

![Software factory repository](images/demo/github-software-factory.png)

### 2. Show the safe product surface

Open `software/order-service`. The checked-in repository uses parameterized SQL and has a focused
repository test. Nothing in the demo mutates this code.

Then open `factory/fixtures/risky-order-change.diff`. The proposed patch introduces dynamic
evaluation and interpolated SQL. This is the controlled input both Agents review.

Ask the customer what they would want a reviewer to catch. Do not reveal the expected decision yet.

### 3. Show policy as code

Open the three review skills:

- `secure-pr-review` catches unsafe execution, interpolated SQL, and hardcoded credentials;
- `test-impact-analysis` maps changed behavior to focused regression coverage;
- `review-evidence-summary` defines the exact output contract shared by both Agents.

Each skill has a Registry ID, semantic version, source digest, and `SKILL.md` digest in
`registry/skill-references.json`. A runtime that reports another fingerprint fails the run.

### 4. Compare the two Agent implementations

Open the LangGraph Agent first. It is deterministic: load governed context, inspect the diff, and
decide. The Atlan SDK creates the root review span and the three skill spans.

Open the Kiro Agent next. Its custom-agent policy grants only read-only discovery through `read`,
`grep`, and `glob`, plus Kiro's internal `disclose_context` tool. It has no shell, write, Git
mutation, web, MCP, or sub-agent authority. Kiro's JSONL
events are sanitized before they become trace evidence.

The point is not that one framework wins. The point is that both implementations remain inside one
governance and evidence contract.

### 5. Show how Git publishes policy

Open the SkillSync workflow. It runs from `main`, checks out full Git history, and uses the Atlan
Agent Registry Action. The workflow is pinned to the reviewed commit on
`fix/installer-digest-v0.1.2`; it does not follow a moving branch at runtime.

The publishing token is available only to the protected sync job. Pull-request code gets a
credential-isolated preflight.

The separate Software Factory Review lane is green and publishes a governed review artifact. It
does not receive an Agent key or submit telemetry.

![Successful Software Factory Review](images/demo/github-ci-success.png)

### 6. Show the execution boundary

Open Daytona. The dashboard is the provider evidence: sandboxes are created from reviewed images,
receive a bounded synthetic workspace, and have explicit lifecycle limits.

![Daytona sandbox dashboard](images/demo/daytona-sandboxes.png)

The earlier Kiro acceptance run produced `changes_requested`, three findings, and all three exact
skill fingerprints inside Daytona:

![Kiro review proof](images/demo/kiro-review-proof.png)

That screenshot is historical acceptance evidence from 30 August 2026. Its sandbox has since been
deleted. Do not present it as a currently running sandbox.

The current acceptance sandbox is `engineering-pr-review-live-20260904`
(`72a2018b-d1d0-4e8b-801b-da857a71a727`). It contains three customer-neutral cases. Open the
sandbox inventory only; do not expose the stored JSONL stream or authentication state.

### 7. Open each Agent in Atlan

Open the PR Review Agent, then the Kiro PR Review Agent. On each profile:

1. show the immutable Agent ID;
2. open Relationships;
3. verify the three active `uses_skill` edges;
4. open Sessions and Usage;
5. open a trace only when a completed live acceptance run is present.

The final demo identities are:

| Runtime | Agent ID | Framework |
|---|---|---|
| LangGraph | `agent_01m1ejp36efnsrw6m8w20atdr3` | `agent_framework_01m09v3ncvey0a4ndx008we9kr` |
| Kiro CLI | `agent_01m1ejp2w6fy0synanm0qp4akh` | `agent_framework_01m1a5cq3hfdg88xkbwpz4w807` |
| Engineering Kiro CLI | `agent_01m1pn4k5deggsts6h7fvfvcgx` | `agent_framework_01m1pn17rvef0b8bqtf3k1v96f` |

Both API keys resolve through the Atlan CLI as the correct machine principal with
`contextplane:read` and `contextplane:write` scopes. The keys are not in GitHub Secrets or the
repository.

### 8. Close on the improvement loop

Open `agents/trace-improver` and `skills/trace-driven-skill-improvement`. The improver reads a
version-scoped trace, classifies a missed finding, and writes a bounded proposal. It cannot change
the production skill or publish a new version. A human still reviews the patch and merges it in
GitHub.

Say: “The learning loop ends in a reviewable Git change, not an autonomous policy mutation.”

## Live acceptance status

Checked on 4 September 2026:

| Check | Result | Evidence |
|---|---|---|
| Engineering Agent | Pass | Active `agent_01m1pn4k5deggsts6h7fvfvcgx` in the Engineering workspace |
| Agent machine identity | Pass | Every run authenticated with the Agent credential injected by Daytona |
| Shared skill relationships | Pass | Exactly three active `uses_skill` relationships |
| Daytona Agent-secret mount | Pass | Daytona injects an opaque placeholder; the pinned Atlan CLI exchanges it without exposing plaintext |
| Kiro 2.20.1 runtime | Pass | Complete three-binary archive and individual SHA-256 values verified |
| Kiro Free device login in Daytona | Pass | Google/AWS device flow completed after the exact OIDC and Kiro hosts were allowlisted; no paid plan required |
| Kiro review matrix | Pass | Risky: 2 findings; safe: approved; SQL format regression: 1 finding |
| Kiro Agent traces | Pass | Three complete seven-span traces verified through the Agent and all three Skill facades |
| Kiro Sessions and Outputs | Pass | Every run has two sanitized messages and one linked Output |
| Native Kiro Usage | Pass | Every run records 5,063 observed tokens and a credit-derived plan-equivalent cost |

Open the three newest Sessions. Their names identify the case, and each shows two sanitized turns
without raw code or diff content. Then use Usage to compare an approval against two blocked changes.

## Recovery checklist before a customer call

1. Open the three newest Kiro Sessions and verify that each has the sanitized request and response.
2. Open Kiro Usage and compare the newest three `software_factory.pr_review` runs.
3. Verify the three named Skill calls appear before the final response and open each fingerprint.
4. Explain that the displayed USD value is a Pro-plan-equivalent estimate; the Free-plan bill is USD 0.
5. Re-run the LangGraph lane and require `trace_id`, `session_id`, and `output_id` before adding it
   to the live walkthrough.

The Engineering Kiro lane is ready for the live walkthrough. Keep the historical LangGraph Usage
tab out until its current Agent-authenticated telemetry acceptance also passes.

## Useful links

- [Architecture](architecture.md)
- [API contracts](api-contracts.md)
- [Live runbook](runbook.md)
- [Registry inventory](registry-inventory.md)
- [Demo control room](demo-links.md)
- [Daytona Secrets behavior](https://www.daytona.io/docs/en/secrets/)
- [Kiro authentication](https://kiro.dev/docs/cli/authentication/)
- [Kiro firewall endpoints](https://kiro.dev/docs/privacy-and-security/firewalls/)
