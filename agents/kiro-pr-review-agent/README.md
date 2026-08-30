# Kiro PR Review Agent

This is the independent Kiro CLI implementation of the governed PR-review contract. GitHub starts
an ephemeral Daytona sandbox; Daytona injects the registered Atlan Agent credential and the Kiro
credential. The sandbox receives only the synthetic service surface, proposed diff, exact skill
bundles, custom-agent configuration, and trace worker.

Kiro has `read` and `grep` authority only. The runtime rejects unknown tools, malformed output,
unregistered skill fingerprints, missing credentials, and incomplete trace evidence.

The verified launcher version and both archive and binary SHA-256 digests are pinned in
[`vendor/kiro/manifest.json`](../../vendor/kiro/manifest.json).
