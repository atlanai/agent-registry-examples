# Demo control room

Open these surfaces in order during the customer walkthrough.

## GitHub

- [Repository](https://github.com/atlanai/software-factory-demo)
- [Product software](https://github.com/atlanai/software-factory-demo/tree/main/software/order-service)
- [PR review agent](https://github.com/atlanai/software-factory-demo/tree/main/agents/pr-review-agent)
- [Kiro PR review agent](https://github.com/atlanai/software-factory-demo/tree/main/agents/kiro-pr-review-agent)
- [Trace improver agent](https://github.com/atlanai/software-factory-demo/tree/main/agents/trace-improver)
- [Secure review skill](https://github.com/atlanai/software-factory-demo/tree/main/skills/secure-pr-review)
- [Test impact skill](https://github.com/atlanai/software-factory-demo/tree/main/skills/test-impact-analysis)
- [Review evidence skill](https://github.com/atlanai/software-factory-demo/tree/main/skills/review-evidence-summary)
- [Trace improvement skill](https://github.com/atlanai/software-factory-demo/tree/main/skills/trace-driven-skill-improvement)
- [Software Factory Review runs](https://github.com/atlanai/software-factory-demo/actions/workflows/software-factory-review.yml)
- [Atlan SkillSync runs](https://github.com/atlanai/software-factory-demo/actions/workflows/atlan-skill-sync.yml)
- [Kiro Daytona review runs](https://github.com/atlanai/software-factory-demo/actions/workflows/kiro-daytona-review.yml)
- [Customer demo walkthrough](https://github.com/atlanai/software-factory-demo/blob/main/docs/customer-demo-walkthrough.md)

## Atlan Agent Registry

Agent Registry is currently a desktop/deep-link surface. Paste these links into a browser or use
`open` on macOS; the Atlan desktop app handles the `atlan://` route.

- Secure review skill: `atlan://open/orgs/atlan/brain/skill/skill_01m11gr8cjekhb5gvqn0k4x1ny`
- Trace improvement skill: `atlan://open/orgs/atlan/brain/skill/skill_01m11gt6ncek08kcxwmqnt0bah`
- Test impact skill: `atlan://open/orgs/atlan/brain/skill/skill_01m1a58e1kfx8aq721tnwd8zgm`
- Review evidence skill: `atlan://open/orgs/atlan/brain/skill/skill_01m1a4yhyaey88ykf2ht4qrvc9`
- PR review agent: `atlan://open/orgs/atlan-prod/brain/agent/agent_01m1ejp36efnsrw6m8w20atdr3`
- Kiro PR review agent: `atlan://open/orgs/atlan-prod/brain/agent/agent_01m1ejp2w6fy0synanm0qp4akh`
- Trace improver agent: `atlan://open/orgs/atlan/brain/agent/agent_01m11hjdcmehrr4yg6jnjj8t38`
- Reviewer trace: `atlan://open/orgs/atlan/traces/06cd432f9c7c5e182c896fcc969b12d4`
- Improver trace: `atlan://open/orgs/atlan/traces/9e916c9e533d518e6a277bf7a4aa5761`
- [Agent Registry documentation](https://platform.atlan.com/)

### Current Engineering demo

- Engineering PR Review Agent: `atlan://open/orgs/atlan-internal/brain/agent/agent_01m1pn4k5deggsts6h7fvfvcgx`
- Engineering LangGraph Agent: `atlan://open/orgs/atlan-internal/brain/agent/agent_01m1q17jwzfv8b6fmg75x08z0g`
- LangGraph SDK trace: `atlan://open/orgs/atlan-internal/brain/agent/agent_01m1q17jwzfv8b6fmg75x08z0g?tab=overview&agentTab=usage&run=b56bbf54bc1d40529b9b7b4322396d02&view=trace`
- Risky regression trace: `atlan://open/orgs/atlan-internal/brain/agent/agent_01m1pn4k5deggsts6h7fvfvcgx?tab=overview&agentTab=usage&run=bfd53094fbfcacd11c1b8191f763d531&view=trace`
- Safe change trace: `atlan://open/orgs/atlan-internal/brain/agent/agent_01m1pn4k5deggsts6h7fvfvcgx?tab=overview&agentTab=usage&run=c3d5d56562cd46e1b7d23ac5a8a2c6b6&view=trace`
- SQL formatting trace: `atlan://open/orgs/atlan-internal/brain/agent/agent_01m1pn4k5deggsts6h7fvfvcgx?tab=overview&agentTab=usage&run=a483ab6431a8c8a2356cd64e17355eaf&view=trace`
- Visitor: `visitor_01m1prfbcqe0raj9mfqq88mwyd` (`Rohan Goel`, human)
- Secure review skill: `atlan://open/orgs/atlan-internal/brain/skill/skill_01m1pn0115ee19gjbzdjxdrady`
- Test impact skill: `atlan://open/orgs/atlan-internal/brain/skill/skill_01m1pn011df01a85dyc5ztjk5h`
- Evidence summary skill: `atlan://open/orgs/atlan-internal/brain/skill/skill_01m1pn0110fz9b869ddyc00sh6`

## Daytona

- [Daytona sandboxes](https://app.daytona.io/dashboard/sandboxes)

Current sandbox: `engineering-pr-review-live-20260904`
(`72a2018b-d1d0-4e8b-801b-da857a71a727`). It contains the pinned Kiro runtime, three exact Skill
bundles, three synthetic PR fixtures, and the Agent-authenticated Atlan trace worker.

LangGraph sandbox: `engineering-langgraph-pr-review-live-20260904`
(`b540ee5f-f318-4bc0-aaf8-c91c47455a1e`). It is retained for the demo and contains the pinned
Atlan SDK wheel, LangGraph runtime, worker, and Agent credential mapping.

The historical Kiro sandbox has been deleted. Use the dashboard and the walkthrough screenshot for
provider evidence; do not present the old sandbox ID as a live link.
