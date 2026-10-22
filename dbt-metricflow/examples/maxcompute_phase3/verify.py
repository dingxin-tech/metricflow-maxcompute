from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from examples.maxcompute_phase1.verify import QueryCase, run
from examples.maxcompute_phase2.verify import phase2_cases

logger = logging.getLogger(__name__)


def phase3_cases() -> tuple[QueryCase, ...]:
    """Validate pruning before cumulative, offsets, attribution windows and SCD joins."""
    dates = ("2026-01-31", "2026-02-01", "2026-02-02", "2026-02-03")
    return (
        QueryCase(
            "aggregate_statistics",
            (
                "amount_avg",
                "amount_min",
                "amount_max",
                "amount_median",
                "amount_p90",
                "amount_disc90",
                "amount_approx_median",
                "positive_orders",
            ),
            (),
            (
                {
                    "amount_avg": 20,
                    "amount_min": 0,
                    "amount_max": 40,
                    "amount_median": 20,
                    "amount_p90": 36,
                    "amount_disc90": 40,
                    "amount_approx_median": 20,
                    "positive_orders": 4,
                },
            ),
        ),
        QueryCase(
            "percentile_by_region",
            ("amount_median",),
            ("customer__region",),
            (
                {"customer__region": "east", "amount_median": 15},
                {"customer__region": "west", "amount_median": 30},
                {"customer__region": None, "amount_median": 20},
            ),
        ),
        QueryCase(
            "arrival_pruned",
            ("arrival_revenue", "arrival_count"),
            (),
            ({"arrival_revenue": 90, "arrival_count": 3},),
            start_time=datetime(2026, 2, 2),
            end_time=datetime(2026, 2, 2),
            capture_warehouse_plan=True,
            expected_scan_partitions=("2026-02-01", "2026-02-02", "2026-02-03", "2026-02-04"),
        ),
        QueryCase(
            "arrival_control",
            ("unpruned_revenue", "unpruned_count"),
            (),
            ({"unpruned_revenue": 90, "unpruned_count": 3},),
            start_time=datetime(2026, 2, 2),
            end_time=datetime(2026, 2, 2),
            capture_warehouse_plan=True,
            expected_scan_partitions=(
                "2026-01-31",
                "2026-02-01",
                "2026-02-02",
                "2026-02-03",
                "2026-02-04",
                "2026-02-05",
                "2026-02-07",
            ),
        ),
        QueryCase(
            "arrival_no_time_filter",
            ("arrival_revenue", "arrival_count"),
            (),
            ({"arrival_revenue": 360, "arrival_count": 8},),
            capture_warehouse_plan=True,
            expected_scan_partitions=(
                "2026-01-31",
                "2026-02-01",
                "2026-02-02",
                "2026-02-03",
                "2026-02-04",
                "2026-02-05",
                "2026-02-07",
            ),
        ),
        QueryCase(
            "cumulative_daily",
            ("revenue_cumulative",),
            ("metric_time__day",),
            tuple(
                {"metric_time__day": day, "revenue_cumulative": amount}
                for day, amount in zip(dates, (10, 60, 100, 100))
            ),
        ),
        QueryCase(
            "rolling_daily",
            ("revenue_2day",),
            ("metric_time__day",),
            tuple({"metric_time__day": day, "revenue_2day": amount} for day, amount in zip(dates, (10, 60, 90, 40))),
        ),
        QueryCase(
            "mtd_daily",
            ("revenue_mtd",),
            ("metric_time__day",),
            tuple({"metric_time__day": day, "revenue_mtd": amount} for day, amount in zip(dates, (10, 50, 90, 90))),
        ),
        QueryCase(
            "previous_day",
            ("previous_revenue",),
            ("metric_time__day",),
            tuple(
                {"metric_time__day": day, "previous_revenue": amount} for day, amount in zip(dates[1:], (10, 50, 40))
            ),
        ),
        QueryCase(
            "rolling_pruned",
            ("arrival_2day",),
            ("metric_time__day",),
            ({"metric_time__day": "2026-02-03", "arrival_2day": 140},),
            start_time=datetime(2026, 2, 3),
            end_time=datetime(2026, 2, 3),
            capture_warehouse_plan=True,
            expected_scan_partitions=(
                "2026-01-31",
                "2026-02-01",
                "2026-02-02",
                "2026-02-03",
                "2026-02-04",
                "2026-02-05",
            ),
        ),
        QueryCase(
            "rolling_control",
            ("unpruned_2day",),
            ("metric_time__day",),
            ({"metric_time__day": "2026-02-03", "unpruned_2day": 140},),
            start_time=datetime(2026, 2, 3),
            end_time=datetime(2026, 2, 3),
        ),
        QueryCase(
            "conversion_totals",
            ("purchase_conversions", "purchase_conversion_rate"),
            (),
            ({"purchase_conversions": 3, "purchase_conversion_rate": 0.6},),
        ),
        QueryCase(
            "conversion_daily",
            ("purchase_conversions", "purchase_conversion_rate"),
            ("metric_time__day",),
            (
                {"metric_time__day": "2026-01-31", "purchase_conversions": None, "purchase_conversion_rate": None},
                {"metric_time__day": "2026-02-01", "purchase_conversions": 3, "purchase_conversion_rate": 1},
            ),
        ),
        QueryCase(
            "conversion_filtered",
            ("purchase_conversions", "purchase_conversion_rate"),
            (),
            ({"purchase_conversions": 3, "purchase_conversion_rate": 1},),
            start_time=datetime(2026, 2, 1),
            end_time=datetime(2026, 2, 1),
        ),
        QueryCase(
            "scd_tier",
            ("revenue", "order_count"),
            ("customer__tier",),
            (
                {"customer__tier": "legacy", "revenue": 10, "order_count": 1},
                {"customer__tier": "gold", "revenue": 20, "order_count": 1},
                {"customer__tier": "bronze", "revenue": 30, "order_count": 1},
                {"customer__tier": "silver", "revenue": None, "order_count": 1},
                {"customer__tier": None, "revenue": 40, "order_count": 2},
            ),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate MaxCompute pruning and phase 3 with phase 1/2 regressions.")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    run(
        arguments.live,
        arguments.output_root,
        phase="phase3",
        fixture_overlay=Path(__file__).parent,
        extra_cases=phase2_cases() + phase3_cases(),
        extra_tables=(
            "countries",
            "refunds",
            "partitioned_orders",
            "arrival_orders",
            "customer_history",
            "visits",
            "purchases",
        ),
    )
