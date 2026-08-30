# Registry inventory

Target workspace: Data (`workspace_01m0g43eb2fmgbv21dc7ygs7rc`).

This file records verified live state only. Planned ids remain blank until create plus authenticated
readback succeeds.

| Kind | Name | ID | Version | Status |
|---|---|---|---:|---|
| Agent framework | `langgraph` | `agent_framework_01m09v3ncvey0a4ndx008we9kr` | — | Verified existing |
| Agent provider | `daytona` | `agent_provider_01m11hdw9sewrrvy1rx0bp73q9` | 1 | Verified registered; draft |
| Environment | `daytona-sdk-pr-review` | `agent_environment_01m11hdztxfn8vm30g3z1s54h5` | 1 | Verified registered, cloud + limited network |
| Environment | `daytona-cli-skill-improver` | `agent_environment_01m11he3c9eeht12m69nsr0c6s` | 1 | Verified registered, cloud + limited network |
| Agent | `registry-pr-review-sdk` | `agent_01m11he6zdf88b5z381489b3xe` | 1 | Verified registered; LangGraph + three active `uses_skill` edges |
| Agent | `kiro-pr-review-agent-v2` | `agent_01m1afk4evfvrtgc2yp2kex50g` | 1 | Replacement registered; Kiro CLI + three active `uses_skill` edges |
| Agent | `registry-skill-improver-cli` | `agent_01m11hjdcmehrr4yg6jnjj8t38` | 1 | Verified registered; LangGraph + active `uses_skill` edge |
| Agent framework | `kiro-cli` | `agent_framework_01m1a5cq3hfdg88xkbwpz4w807` | 1 | Verified registered |
| Environment | `daytona-kiro-pr-review` | `agent_environment_01m1a5cqfdfz1vh7hga5qmpx9d` | 1 | Verified registered with restricted egress |
| Skill | `test-impact-analysis` | `skill_01m1a58e1kfx8aq721tnwd8zgm` | 1 | Git source; semantic version 0.1.1 |
| Skill | `review-evidence-summary` | `skill_01m1a4yhyaey88ykf2ht4qrvc9` | 1 | Git source; semantic version 0.1.1 |
| Skill | `secure-pr-review` | `skill_01m11gr8cjekhb5gvqn0k4x1ny` | 1 | Registered; `pending_review` after two operational scan errors |
| Skill | `trace-driven-skill-improvement` | `skill_01m11gt6ncek08kcxwmqnt0bah` | 1 | Registered; `pending_review` after two operational scan errors |

## Evidence runs

| Run | Agent | Skill version | Trace | Session | Output | Status |
|---|---|---:|---|---|---|---|
| Reviewer v1 | `agent_01m11he6zdf88b5z381489b3xe` | 1 | `06cd432f9c7c5e182c896fcc969b12d4` | `daytona-ceeffd99-d723-4d88-89bd-b1052b025bf7-review-v1-contract2` | `output_01m11hsqegem09jfatqr5w5p45` | Daytona + LangGraph run; trace accepted and readable via skill facade |
| Improvement analysis | `agent_01m11hjdcmehrr4yg6jnjj8t38` | 1 | `9e916c9e533d518e6a277bf7a4aa5761` | `daytona-ceeffd99-d723-4d88-89bd-b1052b025bf7-improver-v1` | `output_01m11hsqegem09jfatqr5w5p45` | Daytona + LangGraph run; CLI trace accepted, projection pending |
| Kiro reviewer v2 | `agent_01m1afk4evfvrtgc2yp2kex50g` | 2 + 1 + 1 | Blocked: Agent key service 503 | Kiro `sess_64f726dd-234c-419c-811b-5df163080d80` | Daytona `kiro-result.json` | Daytona run validated: `changes_requested`, 3 findings, 3 exact skill fingerprints |

## Durable outputs

| Output | ID | File | Status |
|---|---|---|---|
| Registry PR Review Demo Documentation | `output_01m1185rybe18ty8gffx0h0rac` | `file_01m1185d65e20sh8pw8gepwr8x` v1 | Previously registered; current authenticated readback returned 404 |
| Registry PR Review Demo Source | `output_01m11fve5ke5stdezmfgycx17f` | `file_01m11fs4v9fc98rf2ms84d01cd` v1 | Verified registered; draft |
| Registry PR Review Demo Evidence | `output_01m11hsqegem09jfatqr5w5p45` | `file_01m11hsaakes0rz8kw2wm7kyek` v1 | Verified registered; draft; improver-agent lineage |
| Registry PR Review Demo Source Final | `output_01m11hwbd5eqg8kz4mhhd1cp3w` | `file_01m11hvndre2hayarwy5zxx2kp` v1 | Verified registered; draft; SHA-256 `fe347b96899df3de4e3058a4cb82f4bbe88720325e6286f499ac31fd22147d82` |

The source output pins the exact 8.9 MB ZIP uploaded through the documented presigned-file flow.
The older CLI multipart upload path returned HTTP 403; the presigned path succeeded without
changing the archive.

## Daytona evidence

- Live Kiro sandbox: `bd9175aa-3f4f-4982-b0bf-62d4113ed5cf` (`software-factory-kiro-poc`, region `eu`).
- Verified Kiro CLI `2.20.1` archive and complete three-binary runtime installed inside the sandbox.
- Kiro authenticated from the sandbox with Google device flow on the Free plan.
- Kiro v3 used only `read`, `grep`, and the read-only `disclose_context` skill activator.
- Validated result: `changes_requested`, 3 findings, all 3 exact Registry skill fingerprints.
- Sanitized result SHA-256: `d494ded4255f7e0440fe91cff78dd158a3e8abdc6dd031a6ac15a58c00cad3f8`.
- Registry trace, Session, and Output publication remains fail-closed because the Agent identity
  endpoint returns HTTP 503 and has not issued a reveal-once key for the replacement Agent.

## Governance exceptions

Both fresh skill uploads are registered but remain `pending_review`. The automated scan action
failed operationally twice for each skill (`status: error`, `gate_outcome: blocked`) and returned no
finding payload. No manual approval override was applied.
