# Data access standard

- Bind every SQL value through the database driver's parameter API.
- Never assemble SQL with string interpolation or concatenation.
- Scope multi-tenant queries using identity-derived tenant context.
- Do not include query parameters or returned records in telemetry by default.
