# Engineering LangGraph PR Review Agent

This is the Engineering-workspace LangGraph implementation of the governed PR-review contract.
It runs in a retained Daytona demo sandbox, creates spans with the Atlan Python SDK, submits a
sanitized OTLP payload with the Agent credential mounted by Daytona, and verifies Agent and Skill
trace facades before completing.

The current live evidence is recorded in
[`registry/engineering-langgraph-runtime-state.json`](../../registry/engineering-langgraph-runtime-state.json).
