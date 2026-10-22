from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from importlib import import_module
from importlib.metadata import distribution, distributions, version
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast
from uuid import uuid4

logger = logging.getLogger(__name__)
BUNDLE = Path(__file__).resolve().parent

if TYPE_CHECKING:
    from odps import ODPS  # type: ignore[import]

JsonScalar = str | int | float | None
ResultRow = dict[str, JsonScalar]


class QueryCase(TypedDict, total=False):
    """Serialized requests and independent expected results shipped with the bundle."""

    name: str
    metrics: list[str]
    group_by: list[str]
    expected: list[ResultRow]
    start_time: str | None
    end_time: str | None
    where: list[str]
    capture_warehouse_plan: bool
    expected_scan_partitions: list[str] | None


def environment() -> dict[str, str]:
    """Keep commands on the clean venv's PATH and out of source/user-site packages."""
    result = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "DBT_PROJECT_DIR", "DBT_PROFILES_DIR"):
        result.pop(key, None)
    result["PYTHONNOUSERSITE"] = "1"
    result["PATH"] = str(Path(sys.executable).parent) + os.pathsep + result.get("PATH", "")
    result["VIRTUAL_ENV"] = sys.prefix
    return result


def check_install() -> dict[str, object]:
    """Prove the two trial distributions are non-editable, version-paired, and imported from this venv."""
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    assert sys.prefix != sys.base_prefix, "Use the clean virtual environment"
    modules: dict[str, str] = {}
    for package, module in (("metricflow", "metricflow"), ("dbt-metricflow", "dbt_metricflow")):
        assert version(package) == manifest["versions"][package], (package, version(package))
        module_file = import_module(module).__file__
        assert module_file is not None
        location = Path(module_file).resolve()
        assert location.is_relative_to(Path(sys.prefix).resolve()), (module, location)
        modules[package] = str(location)
        info = distribution(package)
        direct_url = info.read_text("direct_url.json")
        if direct_url is not None:
            assert not json.loads(direct_url).get("dir_info", {}).get("editable", False)
        assert not any(" @ " in dependency for dependency in (info.requires or ())), package
    versions = {
        name: version(name)
        for name in ("metricflow", "dbt-metricflow", "dbt-core", "dbt-adapters", "dbt-maxcompute", "pyodps")
    }
    result: dict[str, object] = {
        "versions": versions,
        "modules": modules,
        "python": sys.version,
        "pythonpath": os.environ.get("PYTHONPATH"),
        "venv": sys.prefix,
    }
    assert result["pythonpath"] is None, "Unset PYTHONPATH for delivery verification"
    print(json.dumps(result, indent=2), flush=True)
    return result


def command(arguments: list[str], cwd: Path, log: Path, env: dict[str, str]) -> str:
    """Invoke actual installed console scripts and preserve output without exposing credential environment values."""
    executable = Path(sys.executable).parent / (arguments[0] + (".exe" if os.name == "nt" else ""))
    result = subprocess.run(
        [str(executable), *arguments[1:]], cwd=cwd, env=env, check=False, capture_output=True, text=True, timeout=900
    )
    log.write_text(result.stdout + result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{arguments[0]} {arguments[1]} exited {result.returncode}; see {log}")
    return result.stdout


def compare_csv(path: Path, case: QueryCase) -> list[dict[str, str]]:
    """Compare CLI-exported CSV with independent expected groups, preserving NULL and numeric tolerance."""
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        assert set(reader.fieldnames or ()) == set(case["expected"][0]), reader.fieldnames
    expected = case["expected"]
    assert len(rows) == len(expected), (rows, expected)
    dimensions = sorted(set(expected[0]) - set(case["metrics"]))

    def row_key(row: Mapping[str, JsonScalar]) -> tuple[str, ...]:
        return tuple(str(row[name] or "") for name in dimensions)

    for actual, wanted in zip(sorted(rows, key=row_key), sorted(expected, key=row_key)):
        for name, value in wanted.items():
            if value is None:
                assert actual[name] == "", (actual, wanted)
            elif type(value) in (int, float):
                assert math.isclose(float(actual[name]), cast(float, value), rel_tol=1e-9, abs_tol=1e-9), (
                    actual,
                    wanted,
                )
            elif name.startswith("metric_time"):
                assert actual[name][:10] == value, (actual, wanted)
            else:
                assert actual[name] == value, (actual, wanted)
    return rows


def warehouse() -> ODPS:
    """Use the fixture's runtime credentials only for native EXPLAIN and scoped cleanup."""
    from odps import ODPS  # type: ignore[import]

    client = ODPS(
        os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
        os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
        os.environ["MAXCOMPUTE_PROJECT"],
        endpoint=os.environ["MAXCOMPUTE_ENDPOINT"],
    )
    client.schema = os.environ.get("MAXCOMPUTE_SCHEMA", "default")
    return client


def live_run(output_root: Path) -> Path:
    """Run normal dbt and all metric requests via installed mf; always clean exactly this run's ten tables."""
    required = (
        "MAXCOMPUTE_PROJECT",
        "MAXCOMPUTE_ENDPOINT",
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Set required environment variables: {', '.join(missing)}")
    from dbt.adapters.maxcompute.context import GLOBAL_SQL_HINTS  # type: ignore[import]

    if output_root.resolve().is_relative_to(BUNDLE):
        raise ValueError("Keep verification output outside the immutable delivery bundle")
    prefix = f"mf_trial_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    output = output_root.resolve() / prefix
    project = output / "project"
    output.mkdir(parents=True)
    shutil.copytree(BUNDLE / "verification_project", project)
    env = environment()
    env["MF_MAXCOMPUTE_TABLE_PREFIX"] = prefix
    case_reports: list[dict[str, object]] = []
    cleanup_reports: list[dict[str, object]] = []
    report: dict[str, object] = {
        "prefix": prefix,
        "install": check_install(),
        "cases": case_reports,
        "cleanup": cleanup_reports,
    }
    cases = cast(list[QueryCase], json.loads((BUNDLE / "queries.json").read_text()))
    suffixes = (
        "orders",
        "customers",
        "time_spine",
        "countries",
        "refunds",
        "partitioned_orders",
        "arrival_orders",
        "customer_history",
        "visits",
        "purchases",
    )
    try:
        for action in ("parse", "run"):
            command(["dbt", action, "--profiles-dir", str(project)], project, output / f"dbt-{action}.log", env)
            report[f"dbt_{action}"] = "PASS"
        command(["mf", "list", "metrics"], project, output / "mf-list-metrics.log", env)
        report["mf_list_metrics"] = "PASS"
        for case in cases:
            record: dict[str, object] = {"name": case["name"]}
            case_reports.append(record)
            try:
                arguments = ["mf", "query", "--quiet", "--metrics", ",".join(case["metrics"])]
                if case["group_by"]:
                    arguments += ["--group-by", ",".join(case["group_by"])]
                for bound, flag in ((case.get("start_time"), "--start-time"), (case.get("end_time"), "--end-time")):
                    if bound is not None:
                        arguments += [flag, bound]
                for predicate in case.get("where", []):
                    arguments += ["--where", predicate]
                sql = command(arguments + ["--explain"], project, output / f"{case['name']}.sql", env)
                record["mf_explain"] = "PASS"
                csv_path = output / f"{case['name']}.csv"
                command(arguments + ["--csv", str(csv_path)], project, output / f"{case['name']}.log", env)
                record["actual_csv_rows"] = compare_csv(csv_path, case)
                record["expected"] = case["expected"]
                if case.get("capture_warehouse_plan"):
                    instance = warehouse().execute_sql(
                        f"EXPLAIN {sql}", hints={**GLOBAL_SQL_HINTS, "odps.sql.timezone": "UTC"}
                    )
                    plan = "\n".join(instance.get_task_results().values())
                    (output / f"{case['name']}.warehouse-plan.txt").write_text(plan)
                    record["warehouse_instance"] = instance.id
                    expected_partitions = case.get("expected_scan_partitions")
                    if expected_partitions is not None:
                        scanned = sorted(
                            {
                                part.strip().rsplit("/ds=", 1)[1]
                                for line in plan.splitlines()
                                if line.strip().startswith("Data source:")
                                for part in line.split("Data source:", 1)[1].split(",")
                                if "/ds=" in part
                            }
                        )
                        assert scanned == sorted(expected_partitions), scanned
                        record["scanned_partitions"] = scanned
                record["status"] = "PASS"
                print(f"{case['name']}: PASS", flush=True)
            except Exception as error:
                record["error"] = f"{type(error).__name__}: {error}"
                print(f"{case['name']}: FAIL; see report", flush=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        client = warehouse()
        for suffix in suffixes:
            table = f"{prefix}_{suffix}"
            for attempt in range(3):
                try:
                    client.delete_table(table, if_exists=True)
                    assert not client.exist_table(table)
                    cleanup_reports.append({"table": table, "status": "PASS"})
                    break
                except Exception as error:
                    if attempt == 2:
                        cleanup_reports.append({"table": table, "error": f"{type(error).__name__}: {error}"})
        report["remaining_prefix_tables"] = [table.name for table in client.list_tables(prefix=prefix)]
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(f"Evidence: {output}", flush=True)
    assert "error" not in report and not report["remaining_prefix_tables"], output
    assert len(case_reports) == len(cases) and all(case.get("status") == "PASS" for case in case_reports), output
    assert all(table.get("status") == "PASS" for table in cleanup_reports), output
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify installed trial wheels and run the real dbt/mf CLI cloud chain."
    )
    parser.add_argument("--check-install", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--freeze", type=Path)
    arguments = parser.parse_args()
    check_install()
    if arguments.freeze:
        # Pin third-party runtime packages; the two forked packages are supplied as exact wheels.
        pins = sorted(
            {
                f"{item.metadata['Name']}=={item.version}"
                for item in distributions()
                if item.metadata["Name"].lower().replace("_", "-")
                not in ("metricflow", "dbt-metricflow", "pip", "setuptools", "wheel")
            }
        )
        arguments.freeze.write_text(
            "# Runtime versions resolved and accepted on Python 3.12.\n" + "\n".join(pins) + "\n"
        )
    if arguments.live:
        assert arguments.output_root is not None, "--output-root is required with --live"
        live_run(arguments.output_root)
