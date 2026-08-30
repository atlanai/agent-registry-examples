# Registry and telemetry API contracts

The implementation was derived from the live public and private OpenAPI documents on 2026-08-27.
All calls use the installed `atlanai` CLI so credentials stay in its approved auth source or an
environment credential supplied to the process.

## Registration

| Operation | Purpose |
|---|---|
| `POST agent:/providers` | Register the catalog-only Daytona provider |
| `POST agent:/agent-frameworks` | Register the `kiro-cli` framework |
| `POST agent:/environments` | Register three governed sandbox declarations |
| `POST agent:/agents` | Register identity-bearing agents and capture create-time keys |
| `PUT registry:/workspaces/{workspace}/members/{agent}` | Grant each machine principal `member` |
| `POST registry:/artifacts/{kind}/{id}/relationships` | Link each agent to its governing skill |

An agent create response may contain `identity.api_key` once. The provisioner captures it directly
to Keychain and removes the identity block from persisted state. Existing agents are never silently
reused because their original key cannot be read back; the operator must explicitly rotate and
capture a new key.

## Skills

Repository skills are declared in `.atlan/package.json` and published with:

```bash
atlanai skill validate skills/secure-pr-review
atlanai skill validate skills/trace-driven-skill-improvement
atlanai skill publish --workspace workspace_01m0g43eb2fmgbv21dc7ygs7rc
```

The trace runner uses `atlanai skill get --version` and `atlanai skill pull --version` to resolve the
exact Registry version. It does not assemble a bundle URL or bearer header.

## Trace ingest

The SDK producer uses `atlan_ai.init()` with the Data workspace and the registered agent key. The
CLI producer submits standard OTLP JSON:

```bash
atlanai api post /otel/v1/traces \
  --input trace.json \
  -H Content-Type:application/json \
  -H X-Atlan-Workspace-Id:workspace_01m0g43eb2fmgbv21dc7ygs7rc
```

`ATLANAI_TOKEN` is inherited from the process environment and never appears in arguments.

## Trace readback

```bash
atlanai api get skill:/skills/{skill_id}/traces \
  -F version_ordinal={ordinal} -F limit=50

atlanai api get skill:/skills/{skill_id}/traces/{trace_id}/spans \
  -F version_ordinal={ordinal} -F limit=100
```

The skill facade applies access control and returns a skill-turn slice. The analyzer treats the
facade's `access` block as explanatory metadata, not an authorization decision.

## Sessions and Outputs

Each execution creates one `session` with `subject_kind=agent`, the registered agent id, status,
environment, provider, and the same `external_session_id` propagated on every span. The Kiro result
is registered as a link-mode `output` pointing to the sanitized GitHub Actions artifact and carrying
producer Agent and Session lineage. The run then reads back the Session, Output, Agent trace facade,
and every used Skill trace facade before reporting success.
