from __future__ import annotations

import io
import zipfile
from pathlib import Path


def build_worker_archive(package_dir: Path) -> bytes:
    """Create a zipapp containing only this package's Python sources."""
    root = package_dir.resolve()
    if not (root / "worker.py").is_file():
        raise ValueError("Package directory must contain worker.py")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "__main__.py",
            "from registry_pr_review_demo.worker import main\nraise SystemExit(main())\n",
        )
        for source in sorted(root.glob("*.py")):
            archive.writestr(f"registry_pr_review_demo/{source.name}", source.read_bytes())
    return buffer.getvalue()
