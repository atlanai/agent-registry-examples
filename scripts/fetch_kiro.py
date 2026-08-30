#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import cast

MAX_ARCHIVE_BYTES = 800 * 1024 * 1024
MAX_BINARY_BYTES = 150 * 1024 * 1024
ALLOWED_HOST = "prod.download.cli.kiro.dev"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_verified_archive(
    archive: Path,
    target: Path,
    *,
    archive_digest: str,
    member: str,
    binary_digest: str,
) -> None:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES or sha256(archive) != archive_digest:
        raise RuntimeError("Kiro archive failed size or SHA-256 verification")
    with zipfile.ZipFile(archive) as package:
        info = package.getinfo(member)
        if info.file_size > MAX_BINARY_BYTES:
            raise RuntimeError("Kiro launcher exceeds the verified size limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            with package.open(info) as source:
                shutil.copyfileobj(source, temporary)
        try:
            if sha256(temporary_path) != binary_digest:
                raise RuntimeError("Kiro launcher failed SHA-256 verification")
            temporary_path.chmod(0o755)
            temporary_path.replace(target)
        finally:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify the pinned Kiro CLI launcher")
    parser.add_argument("--manifest", type=Path, default=Path("vendor/kiro/manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("work/kiro/kiro-cli"))
    args = parser.parse_args()
    manifest_raw: object = json.loads(cast(Path, args.manifest).read_text(encoding="utf-8"))
    if not isinstance(manifest_raw, dict):
        raise RuntimeError("Kiro manifest must be an object")
    manifest = cast(dict[str, object], manifest_raw)
    url = str(manifest["archive_url"])
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise RuntimeError("Kiro manifest points outside the approved host")
    output = cast(Path, args.output)
    with tempfile.TemporaryDirectory(prefix="kiro-download-") as directory:
        archive = Path(directory) / "kiro.zip"
        request = urllib.request.Request(  # noqa: S310 - scheme and host validated above
            url, headers={"User-Agent": "software-factory-demo"}
        )
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - host allowlisted above
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != ALLOWED_HOST:
                raise RuntimeError("Kiro download redirected outside the approved host")
            size = 0
            with archive.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise RuntimeError("Kiro archive exceeds the download limit")
                    handle.write(chunk)
        extract_verified_archive(
            archive,
            output,
            archive_digest=str(manifest["archive_sha256"]),
            member=str(manifest["binary_member"]),
            binary_digest=str(manifest["binary_sha256"]),
        )
    print(f"Verified Kiro CLI {manifest['version']} at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
