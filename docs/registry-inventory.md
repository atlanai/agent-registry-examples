# Registry inventory

Current target workspace: Engineering (`workspace_01m1dtasngfk08s4xydm62ewdw`). Historical Data
workspace evidence is retained below for provenance.

## Current Engineering registration

| Kind | Name | ID | Status |
|---|---|---|---|
| Repository | `atlanai/software-factory-demo` | `repo_01m1pmzzqae68srktaf4whqvwt` | Active, Git provenance |
| Framework | `kiro-cli` | `agent_framework_01m1pn17rvef0b8bqtf3k1v96f` | Registered |
| Provider | `daytona` | `agent_provider_01m1pn17zyfxgtdde2mwwwff4w` | Registered |
| Environment | `daytona-kiro-pr-review` | `agent_environment_01m1pn1qw6e3hr8v0emnb1b6nh` | Limited network |
| Agent | `engineering-pr-review-agent` | `agent_01m1pn4k5deggsts6h7fvfvcgx` | Active; Agent key verified |
| Skill | `secure-pr-review` | `skill_01m1pn0115ee19gjbzdjxdrady` | Active, v1 |
| Skill | `test-impact-analysis` | `skill_01m1pn011df01a85dyc5ztjk5h` | Active, v1 |
| Skill | `review-evidence-summary` | `skill_01m1pn0110fz9b869ddyc00sh6` | Active, v1 |

The Agent has exactly three active `uses_skill` relationships, one to each Skill above. The
relationships and every live trace were read back from the API after creation.

## Engineering multi-case acceptance

| Case | Decision | Findings | Trace | Session | Output |
|---|---|---:|---|---|---|
| `risky-injection-regression` | `changes_requested` | 2 | `9dd6c7487b17b23847379f21a8808e67` | `session_01m1pqe910fe8v9eptkqwnebs3` | `output_01m1pqe9nefdrvyqbrekfrgdvt` |
| `safe-parameterized-change` | `approve` | 0 | `aa8be6e221561f60ee865a7e0193e4cb` | `session_01m1pqg2mkfchb1k5m9j5bnqkd` | `output_01m1pqg3fhe8s9kfv7d3s8vfcf` |
| `sql-format-regression` | `changes_requested` | 1 | `35d5dac29416525e29e46cd4dadf11a8` | `session_01m1pqj1bffv9v3ptvy892szc3` | `output_01m1pqj1z0etsarqvqk79j6wva` |

All three are complete `software_factory.pr_review` traces with seven ordered spans, 5,063 observed
Kiro tool/context tokens, stored sanitized prompt and response content, three named Skill spans,
two Session messages, one linked Output, and successful Agent plus three-Skill facade read-back.
Credit-derived plan-equivalent costs are USD 0.013226, USD 0.012968, and USD 0.013641; the Kiro Free
plan's billed cost remains USD 0.

Live Daytona sandbox: `engineering-pr-review-live-20260904`
(`72a2018b-d1d0-4e8b-801b-da857a71a727`).

## Historical Data registration

This file records verified live state only. Planned ids remain blank until create plus authenticated
readback succeeds.

| Kind | Name | ID | Version | Status |
|---|---|---|---:|---|
| Agent framework | `langgraph` | `agent_framework_01m09v3ncvey0a4ndx008we9kr` | — | Verified existing |
| Agent provider | `daytona` | `agent_provider_01m11hdw9sewrrvy1rx0bp73q9` | 1 | Verified registered; draft |
| Environment | `daytona-sdk-pr-review` | `agent_environment_01m11hdztxfn8vm30g3z1s54h5` | 1 | Verified registered, cloud + limited network |
| Environment | `daytona-cli-skill-improver` | `agent_environment_01m11he3c9eeht12m69nsr0c6s` | 1 | Verified registered, cloud + limited network |
| Agent | `pr-review-agent-customer-demo` | `agent_01m1ejp36efnsrw6m8w20atdr3` | 1 | Final LangGraph identity; API key resolves to Agent; three active `uses_skill` edges |
| Agent | `kiro-pr-review-agent-customer-demo` | `agent_01m1ejp2w6fy0synanm0qp4akh` | 1 | Final Kiro identity; API key issued; three active `uses_skill` edges |
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
| Kiro reviewer v2 | `agent_01m1apcr8ve08r88tyh5pcsspr` | 2 + 1 + 1 | Blocked: Agent key service 503 | Kiro `sess_64f726dd-234c-419c-811b-5df163080d80` | Daytona `kiro-result.json` | Daytona run validated: `changes_requested`, 3 findings, 3 exact skill fingerprints |
| Final LangGraph acceptance | `agent_01m1ejp36efnsrw6m8w20atdr3` | 2 + 1 + 1 | Blocked: OTLP HTTP 503 | Not created | Not created | Review executed in ephemeral Daytona; Agent-authenticated trace ingest failed closed |
| Final Kiro acceptance | `agent_01m1ejp2w6fy0synanm0qp4akh` | 2 + 1 + 1 | `47fe8b2d2bc824962bb8a85c4b5e175e` | `session_01m1fp7y6det9vzcdr2esvgcte` | `output_01m1fp7z1gewhvem8kqg9xmskf` | Agent-authenticated Daytona run; ordered instruction → prompt → 3 Skills → response; 5,291 tokens; USD 0.006888 plan-equivalent cost; 2 findings |

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

- Historical Kiro sandbox: `bd9175aa-3f4f-4982-b0bf-62d4113ed5cf` (`software-factory-kiro-poc`, region `eu`); deleted after acceptance.
- Final Kiro sandbox: `56050dee-0103-43d3-82a9-5b1c73bf2d88`
  (`software-factory-kiro-acceptance-4`, region `eu`); live acceptance run with a four-hour TTL.
- Verified Kiro CLI `2.20.1` archive and complete three-binary runtime installed inside the sandbox.
- Verified Atlan CLI `0.3.53` uploaded through the Daytona filesystem API after matching SHA-256
  `2de549a7f584f748f8e082e7c88b18a0e916ef3051f06be2aeddfefa6b13ea59`.
- Kiro authenticated from the sandbox with Google device flow on the Free plan.
- Kiro v3 used only read-category tools (`read`, `grep`, and `glob`) plus the read-only
  `disclose_context` skill activator.
- Validated result: `changes_requested`, 2 findings, all 3 exact Registry skill fingerprints.
- GitHub bootstrap run: `33570899213`.
- Ordered Agent-authenticated trace `47fe8b2d2bc824962bb8a85c4b5e175e` is readable through the Agent
  facade and all three Skill facades. It stores sanitized instruction, prompt, response, named Skill
  calls, `kiro-auto`, 5,291 observed Kiro context/tool tokens, and USD 0.006888 plan-equivalent cost.
- Session `session_01m1fp7y6det9vzcdr2esvgcte` records two sanitized messages and links Output
  `output_01m1fp7z1gewhvem8kqg9xmskf`. Native Usage shows the ordered trace and content.
- The dollar value is an estimate derived from 0.344391 Kiro credits at the published Pro plan rate
  of USD 0.02 per credit. The actual billed cost on the Free plan is USD 0.
- An earlier Session remains with zero turns. The Session API is append-only and exposes no update
  or delete operation; use the newer two-turn Session in the demo.

## Governance exceptions

Both fresh skill uploads are registered but remain `pending_review`. The automated scan action
failed operationally twice for each skill (`status: error`, `gate_outcome: blocked`) and returned no
finding payload. No manual approval override was applied.
