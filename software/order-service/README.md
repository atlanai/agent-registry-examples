# Order service

The order service is the product surface reviewed by this factory. Its repository layer uses bound
SQL parameters and ships with a focused unit test. The factory keeps intentionally risky changes in
`factory/fixtures/`; those patches are review inputs and never become application code.
