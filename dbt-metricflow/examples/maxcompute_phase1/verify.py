from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from typing import cast
from uuid import uuid4

from dbt.adapters.maxcompute.context import GLOBAL_SQL_HINTS  # type: ignore[import]
from odps import ODPS  # type: ignore[import]

from dbt_metricflow.cli.cli_configuration import CLIConfiguration
from metricflow.engine.metricflow_engine import MetricFlowQueryRequest

logger = logging.getLogger(__name__)


JsonScalar = str | int | float | bool | None
ResultRow = dict[str, JsonScalar]


def normalize(value: object) -> JsonScalar:
    """Normalize warehouse scalar types for deterministic result comparisons."""
    if value is None:
        return None
    if issubclass(type(value), (date, datetime)):
        return cast(date, value).isoformat()[:10]
    if type(value) is Decimal:
        return float(value)
    if type(value) not in (str, int, float, bool):
        raise TypeError(f"Unsupported result value: {type(value)}")
    return cast(JsonScalar, value)


@dataclass(frozen=True)
class QueryCase:
    """A metric request and its independently calculated expected result."""

    name: str
    metrics: tuple[str, ...]
    group_by: tuple[str, ...]
    expected: tuple[ResultRow, ...]
    start_time: datetime | None = None
    end_time: datetime | None = None
    where: tuple[str, ...] = ()
    capture_warehouse_plan: bool = False
    expected_scan_partitions: tuple[str, ...] | None = None


def run(
    live: bool,
    output_root: Path,
    *,
    phase: str = "phase1",
    fixture_overlay: Path | None = None,
    extra_cases: tuple[QueryCase, ...] = (),
    extra_tables: tuple[str, ...] = (),
) -> Path:
    """Compile or execute the fixture; clean up only tables with this run's unique prefix."""
    prefix = f"mf_{phase}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    output_dir = output_root.resolve() / prefix
    project_dir = output_dir / "project"
    output_dir.mkdir(parents=True)
    shutil.copytree(Path(__file__).parent, project_dir, ignore=shutil.ignore_patterns("__pycache__"))
    if fixture_overlay is not None:
        shutil.copytree(fixture_overlay / "models", project_dir / "models", dirs_exist_ok=True)
    os.environ["MF_MAXCOMPUTE_TABLE_PREFIX"] = prefix
    case_reports: list[dict[str, object]] = []
    cleanup_reports: list[dict[str, str]] = []
    report: dict[str, object] = {
        "table_prefix": prefix,
        "live": live,
        "cases": case_reports,
        "cleanup": cleanup_reports,
        "fixture_setup": "dbt run",
        "versions": {
            name: version(name) for name in ("metricflow", "dbt-core", "dbt-adapters", "dbt-maxcompute", "pyodps")
        },
    }
    sql_client = None
    try:
        for command in ("parse", "run") if live else ("parse",):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from dbt.cli.main import cli; cli()",
                    command,
                    "--project-dir",
                    str(project_dir),
                    "--profiles-dir",
                    str(project_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            (output_dir / f"dbt_{command}.log").write_text(result.stdout + result.stderr)
            report[f"dbt_{command}"] = result.returncode
            if result.returncode:
                raise RuntimeError(f"dbt {command} failed; see {output_dir / f'dbt_{command}.log'}")

        configuration = CLIConfiguration()
        configuration.setup(dbt_profiles_path=project_dir, dbt_project_path=project_dir, configure_file_logging=False)
        sql_client = configuration.sql_client
        engine = configuration.mf
        cases = (
            ("single_table", ("revenue", "order_count", "customer_count", "average_order_value"), (), None),
            ("daily", ("revenue", "order_count"), ("metric_time__day",), None),
            ("monthly", ("revenue", "order_count"), ("metric_time__month",), None),
            ("weekly", ("revenue", "order_count"), ("metric_time__week",), None),
            ("dimension_join", ("revenue", "order_count"), ("customer__region",), None),
            ("month_and_region", ("revenue", "order_count"), ("metric_time__month", "customer__region"), None),
            ("time_filter", ("revenue", "order_count"), (), datetime(2026, 2, 2)),
        )
        expected: dict[str, list[ResultRow]] = {
            "single_table": [{"revenue": 100, "order_count": 6, "customer_count": 3, "average_order_value": 100 / 6}],
            "daily": [
                {"metric_time__day": day, "revenue": revenue, "order_count": count}
                for day, revenue, count in (
                    ("2026-01-31", 10, 1),
                    ("2026-02-01", 50, 2),
                    ("2026-02-02", 40, 1),
                    ("2026-02-03", 0, 2),
                )
            ],
            "monthly": [
                {"metric_time__month": "2026-01-01", "revenue": 10, "order_count": 1},
                {"metric_time__month": "2026-02-01", "revenue": 90, "order_count": 5},
            ],
            "weekly": [
                {"metric_time__week": "2026-01-26", "revenue": 60, "order_count": 3},
                {"metric_time__week": "2026-02-02", "revenue": 40, "order_count": 3},
            ],
            "dimension_join": [
                {"customer__region": "east", "revenue": 30, "order_count": 2},
                {"customer__region": "west", "revenue": 30, "order_count": 2},
                {"customer__region": None, "revenue": 40, "order_count": 2},
            ],
            "month_and_region": [
                {"metric_time__month": month, "customer__region": region, "revenue": revenue, "order_count": count}
                for month, region, revenue, count in (
                    ("2026-01-01", "east", 10, 1),
                    ("2026-02-01", "east", 20, 1),
                    ("2026-02-01", "west", 30, 2),
                    ("2026-02-01", None, 40, 2),
                )
            ],
            "time_filter": [{"revenue": 40, "order_count": 3}],
        }
        query_cases = (
            tuple(
                QueryCase(name, metrics, group_by, tuple(expected[name]), start_time)
                for name, metrics, group_by, start_time in cases
            )
            + extra_cases
        )
        for case in query_cases:
            name = case.name
            case_report: dict[str, object] = {"name": name}
            case_reports.append(case_report)
            try:
                request = MetricFlowQueryRequest.create(
                    metric_names=case.metrics,
                    group_by_names=case.group_by,
                    time_constraint_start=case.start_time,
                    time_constraint_end=case.end_time,
                    where_constraints=case.where or None,
                )
                explanation = engine.explain(request)
                sql = explanation.sql_statement.sql
                (output_dir / f"{name}.sql").write_text(sql)
                (output_dir / f"{name}.plan.txt").write_text(explanation.dataflow_plan.structure_text())
                case_report["compile"] = "PASS"
                if live:
                    sql_client.dry_run(sql)
                    case_report["explain"] = "PASS"
                    result_table = engine.query(request).result_df
                    assert result_table is not None
                    actual = [
                        dict(zip(result_table.column_names, (normalize(value) for value in row)))
                        for row in result_table.rows
                    ]
                    case_report["actual"] = actual
                    case_report["expected"] = list(case.expected)
                    assert_results(actual, list(case.expected))
                    case_report["result"] = "PASS"
                    if case.capture_warehouse_plan:
                        instance = create_warehouse().execute_sql(
                            f"EXPLAIN {sql}",
                            # Match adapter execution, including non-equi cumulative joins and the fixture's UTC profile.
                            hints={**GLOBAL_SQL_HINTS, "odps.sql.timezone": "UTC"},
                        )
                        # EXPLAIN returns task text without a tabular schema; open_reader() cannot decode it.
                        plan_text = "\n".join(instance.get_task_results().values())
                        (output_dir / f"{name}.warehouse-plan.txt").write_text(plan_text)
                        case_report["warehouse_plan_instance"] = instance.id
                        if case.expected_scan_partitions is not None:
                            # Native paths, e.g. project.schema.table/ds=2026-02-02, prove physical scans.
                            scanned = sorted(
                                {
                                    path.strip().rsplit("/ds=", 1)[1]
                                    for line in plan_text.splitlines()
                                    if line.strip().startswith("Data source:")
                                    for path in line.split("Data source:", 1)[1].split(",")
                                    if "/ds=" in path
                                }
                            )
                            case_report["scanned_partitions"] = scanned
                            assert scanned == sorted(case.expected_scan_partitions), (
                                scanned,
                                case.expected_scan_partitions,
                            )
                print(f"{name}: {case_report}", flush=True)
            except Exception as exc:
                case_report["error"] = f"{type(exc).__name__}: {exc}"
                print(f"{name}: FAIL ({type(exc).__name__}); see report.json", flush=True)
    finally:
        if sql_client is not None:
            sql_client.close()
        if live:
            warehouse = create_warehouse()
            for suffix in ("orders", "customers", "time_spine") + extra_tables:
                table_name = f"{prefix}_{suffix}"
                for attempt in range(3):
                    try:
                        warehouse.delete_table(table_name, if_exists=True)
                        assert not warehouse.exist_table(table_name), table_name
                        cleanup_reports.append({"table": table_name, "status": "PASS"})
                        break
                    except Exception as exc:
                        if attempt == 2:
                            cleanup_reports.append({"table": table_name, "error": f"{type(exc).__name__}: {exc}"})
        (output_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
        print(f"Evidence: {output_dir}", flush=True)
    if any("error" in case for case in case_reports + cleanup_reports):
        raise RuntimeError("Verification failed; see report.json")
    return output_dir


def assert_results(actual: list[ResultRow], expected: list[ResultRow]) -> None:
    """Compare unordered groups with tolerant numeric equality."""

    def sort_key(row: ResultRow) -> str:
        return repr(sorted((key, str(value)) for key, value in row.items()))

    assert len(actual) == len(expected), (actual, expected)
    for actual_row, expected_row in zip(sorted(actual, key=sort_key), sorted(expected, key=sort_key)):
        assert actual_row.keys() == expected_row.keys(), (actual, expected)
        for key, expected_value in expected_row.items():
            actual_value = actual_row[key]
            if type(expected_value) in (int, float):
                assert actual_value is not None and math.isclose(
                    float(actual_value), cast(float, expected_value), rel_tol=1e-9
                ), (
                    actual_row,
                    expected_row,
                )
            else:
                assert actual_value == expected_value, (actual_row, expected_row)


def create_warehouse() -> ODPS:
    """Use the same environment-based identity and schema as the fixture's dbt profile."""
    warehouse = ODPS(
        os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
        os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
        os.environ["MAXCOMPUTE_PROJECT"],
        endpoint=os.environ["MAXCOMPUTE_ENDPOINT"],
    )
    warehouse.schema = os.environ.get("MAXCOMPUTE_SCHEMA", "default")
    return warehouse


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify MetricFlow against disposable MaxCompute fixture tables.")
    parser.add_argument(
        "--live", action="store_true", help="Create fixture tables, EXPLAIN and execute, then clean up."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.live, arguments.output_root)
