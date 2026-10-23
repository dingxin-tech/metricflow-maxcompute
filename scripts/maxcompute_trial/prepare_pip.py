from __future__ import annotations

import argparse
import hashlib
import json
import logging
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)


def prepare(archive: Path, release_url: str, output: Path) -> None:
    """Expose the accepted wheels and constraints through one versioned pip requirements URL."""
    base = release_url.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc or any(character.isspace() for character in base):
        raise ValueError("Use an HTTPS release URL without whitespace")
    output.mkdir(parents=True, exist_ok=False)
    requirements = ["# Python 3.12; paired MaxCompute trial wheels and accepted runtime constraints."]
    requirements.append(f"-c {base}/constraints.txt")
    with tarfile.open(archive, "r:gz") as source:
        # Bundles contain exactly one top-level directory, e.g. trial/manifest.json.
        manifests = [
            member
            for member in source.getmembers()
            if len(PurePosixPath(member.name).parts) == 2 and PurePosixPath(member.name).name == "manifest.json"
        ]
        if len(manifests) != 1:
            raise ValueError("Expected one bundle manifest")
        manifest_stream = source.extractfile(manifests[0])
        assert manifest_stream is not None
        manifest = json.load(manifest_stream)
        prefix = str(PurePosixPath(manifests[0].name).parent)
        constraint_stream = source.extractfile(f"{prefix}/constraints.txt")
        assert constraint_stream is not None
        (output / "constraints.txt").write_bytes(constraint_stream.read())
        wheels = manifest["wheels"]
        assert len(wheels) == 2
        for relative in wheels:
            name = PurePosixPath(relative).name
            assert name.endswith(".whl")
            package = "dbt-metricflow[dbt-maxcompute]" if name.startswith("dbt_metricflow-") else "metricflow"
            member_stream = source.extractfile(f"{prefix}/{relative}")
            assert member_stream is not None
            data = member_stream.read()
            (output / name).write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            requirements.append(f"{package} @ {base}/{quote(name)}#sha256={digest}")
    (output / "requirements.txt").write_text("\n".join(requirements) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare pip-installable assets from an accepted trial archive.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    prepare(arguments.archive, arguments.release_url, arguments.output)
