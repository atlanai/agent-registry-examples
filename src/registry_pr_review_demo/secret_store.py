from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import keyring


@dataclass(frozen=True, slots=True)
class KeychainCommandResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


class KeychainSecretStore:
    def __init__(
        self,
        *,
        runner: Callable[[Sequence[str], bytes | None], KeychainCommandResult] | None = None,
    ) -> None:
        self._runner = runner

    def put(self, *, service: str, account: str, secret: bytes) -> None:
        if not service or not account or not secret or b"\n" in secret:
            raise ValueError("service, account, and a single-line secret are required")
        if self._runner is None:
            keyring.set_password(service, account, secret.decode())
            return
        result = self._runner(
            (
                "security",
                "add-generic-password",
                "-U",
                "-a",
                account,
                "-s",
                service,
                "-w",
            ),
            secret + b"\n",
        )
        if result.exit_code != 0:
            raise RuntimeError("failed to store credential in macOS Keychain")

    def get(self, *, service: str, account: str) -> bytes:
        if not service or not account:
            raise ValueError("service and account are required")
        if self._runner is None:
            secret = keyring.get_password(service, account)
            if not secret:
                raise RuntimeError("credential is not available in macOS Keychain")
            return secret.encode()
        result = self._runner(
            ("security", "find-generic-password", "-a", account, "-s", service, "-w"),
            None,
        )
        if result.exit_code != 0:
            raise RuntimeError("credential is not available in macOS Keychain")
        secret = result.stdout.rstrip(b"\r\n")
        if not secret:
            raise RuntimeError("credential in macOS Keychain is empty")
        return secret
