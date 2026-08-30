from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import registry_pr_review_demo
from registry_pr_review_demo.worker_bundle import build_worker_archive


def test_worker_archive_executes_as_a_zipapp(tmp_path: Path) -> None:
    package_dir = Path(registry_pr_review_demo.__file__).parent
    archive = tmp_path / "agent.pyz"
    archive.write_bytes(build_worker_archive(package_dir))
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(
            {
                "request": {
                    "repository": "example/repo",
                    "pull_request_number": 1,
                    "head_sha": "a" * 40,
                    "diff": "+safe = True",
                },
                "skill": {
                    "id": "skill_demo",
                    "version": 1,
                    "name": "secure-pr-review",
                    "rules": [],
                },
                "documents": [],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(archive),
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output_path.read_text(encoding="utf-8"))["decision"] == "approve"
