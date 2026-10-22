from __future__ import annotations

import hashlib
import logging
import tarfile
from pathlib import Path

import pytest

from scripts.maxcompute_trial.build import archive_bundle
from scripts.maxcompute_trial.install import verify_checksums
from scripts.maxcompute_trial.verify_cli import QueryCase, compare_csv

logger = logging.getLogger(__name__)


def test_trial_checksum_and_versioned_archive(tmp_path: Path) -> None:
    """Preserve the trial suffix and verify the actual archive's shipped bytes."""
    bundle = tmp_path / "trial.1"
    bundle.mkdir()
    (bundle / "payload.txt").write_text("trial payload")
    archive = archive_bundle(bundle)
    assert archive.name == "trial.1.tar.gz"
    assert (
        archive.with_name(archive.name + ".sha256")
        .read_text()
        .startswith(hashlib.sha256(archive.read_bytes()).hexdigest())
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(archive) as stream:
        for name in ("payload.txt", "SHA256SUMS"):
            member = stream.extractfile(f"trial.1/{name}")
            assert member is not None
            (extracted / name).write_bytes(member.read())
    verify_checksums(extracted)
    (bundle / "payload.txt").write_text("changed after sealing")
    with pytest.raises(ValueError, match="checksum"):
        verify_checksums(bundle)


def test_trial_checksum_refuses_escape(tmp_path: Path) -> None:
    """A matching checksum must not authorize a path outside the bundle."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("outside")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (bundle / "SHA256SUMS").write_text(f"{digest}  ../outside\n")
    with pytest.raises(ValueError, match="checksum"):
        verify_checksums(bundle)


@pytest.mark.parametrize("bad_row", ["east,", "east,0", "west,30"])
def test_cli_csv_comparison_catches_wrong_results(tmp_path: Path, bad_row: str) -> None:
    """Wrong NULL, number or group must fail the package's cloud acceptance verifier."""
    case: QueryCase = {"metrics": ["revenue"], "expected": [{"region": "east", "revenue": 30}]}
    output = tmp_path / "result.csv"
    output.write_text("region,revenue\neast,30.0000000001\n")
    assert compare_csv(output, case) == [{"region": "east", "revenue": "30.0000000001"}]
    output.write_text(f"region,revenue\n{bad_row}\n")
    with pytest.raises((AssertionError, ValueError)):
        compare_csv(output, case)


def test_cli_csv_null_is_not_zero(tmp_path: Path) -> None:
    """The release gate distinguishes a missing aggregate from numeric zero."""
    case: QueryCase = {"metrics": ["revenue"], "expected": [{"revenue": None}]}
    output = tmp_path / "result.csv"
    output.write_text('revenue\n""\n')
    assert compare_csv(output, case) == [{"revenue": ""}]
    output.write_text("revenue\n0\n")
    with pytest.raises(AssertionError):
        compare_csv(output, case)
