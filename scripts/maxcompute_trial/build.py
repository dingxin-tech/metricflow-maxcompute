from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def source_version(path: Path) -> str:
    """Read a literal package version without importing development packages."""
    for node in ast.parse(path.read_text()).body:
        if type(node) is ast.Assign and any(
            type(target) is ast.Name and target.id == "__version__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert type(value) in (str,)
            return value
    raise ValueError(f"Missing version in {path}")


def write_checksums(bundle: Path) -> None:
    """Hash every distributed file, excluding the checksum file itself."""
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}"
        for path in sorted(bundle.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (bundle / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def assemble(destination: Path, hatch: str) -> Path:
    """Build paired wheels and assemble a self-contained trial bundle; no credentials are included."""
    destination.mkdir(parents=True, exist_ok=False)
    wheel_dir = destination / "wheels"
    wheel_dir.mkdir()
    source_dir = destination / "sources"
    source_dir.mkdir()
    versions = {
        "metricflow": source_version(ROOT / "metricflow/__about__.py"),
        "dbt-metricflow": source_version(ROOT / "dbt-metricflow/dbt_metricflow/__about__.py"),
    }
    wheels: list[str] = []
    sdists: list[str] = []
    build_environment = dict(os.environ)
    for key in ("HATCH_ENV", "HATCH_ENV_ACTIVE"):
        build_environment.pop(key, None)
    for project, name in ((ROOT, "metricflow"), (ROOT / "dbt-metricflow", "dbt-metricflow")):
        subprocess.run([hatch, "build", "-t", "wheel", "-t", "sdist"], cwd=project, env=build_environment, check=True)
        wheel = project / "dist" / f"{name.replace('-', '_')}-{versions[name]}-py3-none-any.whl"
        with ZipFile(wheel) as archive:
            metadata = Parser().parsestr(
                archive.read(next(member for member in archive.namelist() if member.endswith("/METADATA"))).decode()
            )
            dependencies = metadata.get_all("Requires-Dist", [])
            if any(" @ " in requirement or "{root" in requirement for requirement in dependencies):
                raise ValueError(f"Non-portable wheel dependencies: {wheel.name}")
            assert metadata["Version"] == versions[name]
            if name == "dbt-metricflow":
                assert f"metricflow=={versions['metricflow']}" in dependencies
                assert any("pyodps" in dependency and "0.13.2" in dependency for dependency in dependencies)
        shutil.copy2(wheel, wheel_dir / wheel.name)
        wheels.append(f"wheels/{wheel.name}")
        sdist = project / "dist" / f"{name.replace('-', '_')}-{versions[name]}.tar.gz"
        shutil.copy2(sdist, source_dir / sdist.name)
        sdists.append(f"sources/{sdist.name}")
    for filename in ("install.py", "verify_cli.py", "QUICKSTART.zh-CN.md", "queries.json", "constraints.txt"):
        shutil.copy2(Path(__file__).parent / filename, destination / filename)
    for filename in ("LICENSE", "ATTRIBUTION.md"):
        shutil.copy2(ROOT / filename, destination / filename)
    examples = ROOT / "dbt-metricflow/examples"
    validation = destination / "verification_project"
    validation.mkdir()
    for filename in ("dbt_project.yml", "profiles.yml"):
        shutil.copy2(examples / "maxcompute_phase1" / filename, validation / filename)
    shutil.copytree(examples / "maxcompute_phase1/models", validation / "models")
    shutil.copytree(examples / "maxcompute_phase3/models", validation / "models", dirs_exist_ok=True)
    example = destination / "example"
    shutil.copytree(Path(__file__).parent / "example", example)
    shutil.copy2(validation / "profiles.yml", example / "profiles.yml")
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()
    modified = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()
    manifest = {
        "trial": versions["metricflow"].split("+", 1)[1],
        "versions": versions,
        "wheels": wheels,
        "sources": sdists,
        "python_accepted": "3.12",
        "upstream_base_commit": (ROOT / "UPSTREAM_BASE").read_text().strip(),
        "source_commit": source_commit,
        "source_state": "modified checkout" if modified else "clean checkout",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_checksums(destination)
    return destination


def archive_bundle(bundle: Path) -> Path:
    """Create a distributable archive from finalized files, excluding runtime evidence and environments."""
    write_checksums(bundle)
    archive_path = bundle.parent / (bundle.name + ".tar.gz")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(bundle, arcname=bundle.name)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_name(archive_path.name + ".sha256").write_text(f"{digest}  {archive_path.name}\n")
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build or re-archive the MaxCompute trial delivery.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hatch", default="hatch")
    parser.add_argument("--archive-only", action="store_true")
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if not arguments.archive_only:
        assemble(output, arguments.hatch)
    print(archive_bundle(output))
