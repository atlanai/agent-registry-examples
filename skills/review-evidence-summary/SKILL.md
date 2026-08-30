---
name: review-evidence-summary
description: Normalize governed PR-review findings into a compact machine-readable decision and human summary. Use after review and test-impact analysis; never change the underlying findings.
metadata:
  skill_version: "0.1.1"
---

# Review Evidence Summary

Preserve the supplied decision and findings. Produce one JSON object with:

- `decision`: `approve`, `comment`, or `changes_requested`;
- `findings`: rule id, severity, message, and diff line;
- `skills_used`: Registry id, version, and source digest for every verified skill;
- `test_plan`: focused tests from the test-impact analysis;
- `summary`: at most four factual sentences.

Reject missing skill fingerprints, unknown decisions, or findings without line evidence. Never include
raw diff content, credentials, model reasoning, or a claim that a test ran when it was only proposed.
