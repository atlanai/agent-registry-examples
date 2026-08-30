# Live demo runbook

Every step is a command or a check. Do not paste a key into a command, file, prompt, or chat.

## 1. Verify the local checkout

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

## 2. Create the Daytona account and key

1. Open Daytona and choose **Sign in with Google**.
2. Stop if the OAuth screen requests scopes beyond basic identity/email or presents unexpected
   terms.
3. Create one API key named `registry-pr-review-local`.
4. Copy the reveal-once value, then immediately run:

```bash
uv run python scripts/store_daytona_key.py
```

Check that the helper reports Keychain storage and clipboard clearing. Never print the Keychain
value to verify it.

## 3. Validate and publish the skills

```bash
atlanai auth status
atlanai context show
atlanai skill validate skills/secure-pr-review
atlanai skill validate skills/trace-driven-skill-improvement
atlanai skill publish --workspace workspace_01m0g43eb2fmgbv21dc7ygs7rc
```

Read both skills back and write their ids, version ordinals, source digests, semantic versions, and
SKILL.md digests to fresh `skill-reference.json` files. Do not infer a successful publish from the
local directory.

## 4. Register provider, environments, and agents

```bash
uv run registry-pr-review registry-plan --output /tmp/registry-plan.json
uv run registry-pr-review registry-apply --output registry/state.json
```

The apply command captures both create-time agent keys into Keychain. If an agent with either
planned name already exists, stop; do not rotate it implicitly.

## 5. Create Daytona Secrets

```bash
uv run python scripts/sync_daytona_secrets.py
```

Check in Daytona that `registry-sdk-agent-key` and `registry-cli-agent-key` allow only
`agentgateway.atlan.engineering`.

## 6. Run version 1 through the SDK agent

```bash
uv run registry-pr-review build-request \
  --repository example/data-service \
  --pr-number 17 \
  --head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --diff-file examples/sql-format-gap.diff \
  --output /tmp/review-request.json

uv run registry-pr-review run-sdk \
  --request /tmp/review-request.json \
  --skill-reference /tmp/secure-pr-review-v1.json \
  --knowledge-root knowledge \
  --case-id sql-format-interpolation \
  --evaluations examples/evaluations.json \
  --output results/reviewer-v1.json
```

Check that the result is `approve`, includes a trace id, and contains no raw credential.

## 7. Verify and analyze the trace

Poll the version 1 skill facade every five seconds for at most two minutes. Stop when the evaluation
case appears; otherwise report accepted ingest with unavailable projection.

```bash
uv run registry-pr-review run-improver-cli \
  --target-skill-reference /tmp/secure-pr-review-v1.json \
  --analyzer-skill-reference /tmp/trace-driven-skill-improvement-v1.json \
  --case-id sql-format-interpolation \
  --evaluations examples/evaluations.json \
  --output-dir results/improvement-v1
```

Review `results/improvement-v1/proposal.md`. It must say **Human approval required** and must not
change `rules.json`.

## 8. Approval-gated version 2

After approval, apply only the proposed `parameterize-sql` pattern, rerun all tests, and publish the
same skill again. Repeat step 6 with the returned version 2 reference. Verify
`changes_requested` for the unchanged evaluation case.

## 9. Register evidence

Upload the source snapshot, documentation bundle, SVGs, v1 result, proposal, and v2 result as files.
Register Outputs pinned to those exact file versions, attach agent/session lineage to run results,
and add `used_skill` relationships. Read every Output and relationship back once.

## Failure rules

- Mutation timeout: list/fetch before any retry.
- Missing Daytona projection: preserve ingest receipt and report partial verification.
- Existing planned agent: stop before key rotation.
- Missing skill fingerprint: do not claim skill usage.
- Failed patch tests: do not publish version 2.
- Unexpected OAuth scope or terms: stop for user review.

