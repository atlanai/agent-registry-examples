# Governed PR review agent

This LangGraph agent resolves `secure-pr-review` by immutable Registry version, loads the referenced
engineering standards, reviews only added diff lines, and records the skill fingerprint with the
decision. Daytona is the live execution boundary; GitHub Actions provides the repeatable review
entrypoint and evidence artifact.
