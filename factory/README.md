# Factory control plane

This directory holds deterministic review inputs and factory-level configuration. Product code
lives under `software/`; agents and skills remain independently inspectable under `agents/` and
`skills/`.

`fixtures/risky-order-change.diff` is a proposed change, not shipped application code. The review
workflow feeds it to the LangGraph PR-review agent using the current Registry skill fingerprint.
The expected outcome is `changes_requested` for dynamic evaluation and interpolated SQL.
