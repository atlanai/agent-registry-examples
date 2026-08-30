from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest

import registry_pr_review_demo.secret_store as secret_store
from registry_pr_review_demo.secret_store import KeychainCommandResult, KeychainSecretStore


def test_keychain_store_never_places_secret_in_process_arguments() -> None:
    observed: dict[str, object] = {}

    def runner(args: Sequence[str], input_bytes: bytes | None) -> KeychainCommandResult:
        observed["args"] = tuple(args)
        observed["input"] = input_bytes
        return KeychainCommandResult(exit_code=0, stdout=b"", stderr=b"")

    store = KeychainSecretStore(runner=runner)
    store.put(service="daytona/api-key", account="registry-pr-review", secret=b"secret-value")

    args = observed["args"]
    assert isinstance(args, tuple)
    typed_args = cast(tuple[str, ...], args)
    assert typed_args[-1] == "-w"
    assert "secret-value" not in " ".join(typed_args)
    assert observed["input"] == b"secret-value\n"


def test_keychain_read_returns_bytes_without_logging() -> None:
    def runner(args: Sequence[str], input_bytes: bytes | None) -> KeychainCommandResult:
        assert input_bytes is None
        return KeychainCommandResult(exit_code=0, stdout=b"stored-secret\n", stderr=b"")

    secret = KeychainSecretStore(runner=runner).get(
        service="daytona/api-key", account="registry-pr-review"
    )

    assert secret == b"stored-secret"


def test_default_backend_uses_keyring_without_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[tuple[str, str], str] = {}

    def set_password(service: str, account: str, value: str) -> None:
        stored[(service, account)] = value

    def get_password(service: str, account: str) -> str | None:
        return stored.get((service, account))

    monkeypatch.setattr(secret_store.keyring, "set_password", set_password)
    monkeypatch.setattr(secret_store.keyring, "get_password", get_password)
    store = KeychainSecretStore()
    store.put(service="svc", account="acct", secret=b"value")
    assert store.get(service="svc", account="acct") == b"value"
