# Trace-driven skill improver

This agent reads version-scoped Atlan trace evidence, compares an observed decision with the
checked-in expectation, and produces one bounded skill patch proposal. It cannot edit or publish a
skill. The `proposal_only` boundary keeps the improvement loop reviewable by a human.
