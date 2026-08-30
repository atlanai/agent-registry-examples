#!/usr/bin/env python3
from __future__ import annotations

import subprocess

from registry_pr_review_demo.secret_store import KeychainSecretStore


def main() -> int:
    copied = subprocess.run(["/usr/bin/pbpaste"], check=False, capture_output=True)
    secret = copied.stdout.rstrip(b"\r\n")
    if copied.returncode != 0 or not secret:
        raise SystemExit("copy the reveal-once Daytona API key, then run this helper")
    try:
        KeychainSecretStore().put(
            service="daytona/api-key",
            account="registry-pr-review",
            secret=secret,
        )
    finally:
        subprocess.run(["/usr/bin/pbcopy"], input=b"", check=False, capture_output=True)
    print("Stored the Daytona API key in macOS Keychain and cleared the clipboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
