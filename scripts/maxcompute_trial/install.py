from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_checksums(bundle: Path) -> None:
    """Verify shipped files before installing; refuse paths outside the bundle."""
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Bundle checksum mismatch: {name}")


def clean_environment() -> dict[str, str]:
    """Prevent source checkouts or user site-packages from leaking into installed commands."""
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def main() -> None:
    """Install the paired trial wheels and validate dependencies in a fresh Python 3.12 venv."""
    parser = argparse.ArgumentParser(description="Install the MaxCompute trial in a fresh Python 3.12 environment.")
    parser.add_argument("--venv", type=Path, required=True)
    arguments = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("This trial is accepted on Python 3.12. Run this installer with python3.12.")
    bundle = Path(__file__).resolve().parent
    verify_checksums(bundle)
    target = arguments.venv.resolve()
    if target.exists():
        raise FileExistsError(f"Choose a fresh environment directory; already exists: {target}")
    manifest = json.loads((bundle / "manifest.json").read_text())
    environment = clean_environment()
    subprocess.run([sys.executable, "-I", "-m", "venv", str(target)], check=True, env=environment)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = [
        str(bundle / name) + ("[dbt-maxcompute]" if "dbt_metricflow" in name else "") for name in manifest["wheels"]
    ]
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--require-virtualenv",
            "--disable-pip-version-check",
            "--constraint",
            str(bundle / "constraints.txt"),
            *requirements,
        ],
        check=True,
        env=environment,
        cwd=bundle,
    )
    subprocess.run([str(python), "-I", "-m", "pip", "check"], check=True, env=environment, cwd=bundle)
    subprocess.run(
        [str(python), "-I", str(bundle / "verify_cli.py"), "--check-install"], check=True, env=environment, cwd=bundle
    )
    print(f"Installed trial into {target}")


if __name__ == "__main__":
    main()
