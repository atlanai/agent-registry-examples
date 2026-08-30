#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src/registry_pr_review_demo"
        ).is_dir():
            return candidate
    raise SystemExit("run this repository-local skill from the registry-pr-review-demo checkout")


def main() -> int:
    root = find_repo_root(Path.cwd())
    env = os.environ.copy()
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required")
    command = [uv, "run", "registry-pr-review", "analyze-traces", *sys.argv[1:]]
    # No shell is used; user arguments remain individual argv entries for the fixed CLI.
    completed = subprocess.run(command, cwd=root, env=env, check=False)  # noqa: S603
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
