# Registry trace evidence contract

Use the access-controlled skill facade:

```text
GET /skill/v1/skills/{skill_id}/traces?version_ordinal={ordinal}
GET /skill/v1/skills/{skill_id}/traces/{trace_id}/spans?version_ordinal={ordinal}
```

Call these through `atlanai api get skill:/...`. The list returns `items`, cursor `page`, and an
advisory `access` block. Span evidence used by this skill is limited to:

- `trace_id`, `trace_status`, `duration_ms`, and summary error/span counts;
- `skill_name`, `skill_version`, and match confidence;
- `atlan.skill.source_digest` and `atlan.skill.skillmd_sha256` when present;
- `demo.eval.case_id`, `demo.eval.expected_decision`, `review.decision`,
  `review.finding_count`, and matched rule ids.

Do not treat the access block as authorization logic; the gateway already enforced access. Do not
copy raw input, output, events, or arbitrary span attributes into the proposal. A missing trace
after an accepted ingest may be projection lag, not proof of loss; poll for at most two minutes.
