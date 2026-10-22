from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from examples.maxcompute_phase1.verify import QueryCase, run

logger = logging.getLogger(__name__)


def phase2_cases() -> tuple[QueryCase, ...]:
    """Exercise independent facts, two-hop joins, NULL groups, and partition predicates."""
    return (
        QueryCase(
            "cross_fact_totals",
            ("revenue", "refund_amount", "net_revenue"),
            (),
            ({"revenue": 100, "refund_amount": 22, "net_revenue": 78},),
        ),
        QueryCase(
            "cross_fact_daily",
            ("revenue", "refund_amount"),
            ("metric_time__day",),
            tuple(
                {"metric_time__day": day, "revenue": revenue, "refund_amount": refund}
                for day, revenue, refund in (
                    ("2026-01-31", 10, 2),
                    ("2026-02-01", 50, 4),
                    ("2026-02-02", 40, 11),
                    ("2026-02-03", 0, None),
                    ("2026-02-04", None, 5),
                )
            ),
        ),
        QueryCase(
            "cross_fact_null_region",
            ("revenue", "refund_amount"),
            ("customer__region",),
            (
                {"customer__region": "east", "revenue": 30, "refund_amount": 6},
                {"customer__region": "west", "revenue": 30, "refund_amount": 3},
                {"customer__region": None, "revenue": 40, "refund_amount": 8},
                {"customer__region": "unused", "revenue": None, "refund_amount": 5},
            ),
        ),
        QueryCase(
            "derived_null_region",
            ("net_revenue",),
            ("customer__region",),
            (
                {"customer__region": "east", "net_revenue": 24},
                {"customer__region": "west", "net_revenue": 27},
                {"customer__region": None, "net_revenue": 32},
                {"customer__region": "unused", "net_revenue": None},
            ),
        ),
        QueryCase(
            "two_hop_dimension",
            ("revenue", "order_count"),
            ("customer__country__country_name",),
            (
                {"customer__country__country_name": "eastland", "revenue": 30, "order_count": 2},
                {"customer__country__country_name": "westland", "revenue": 30, "order_count": 2},
                {"customer__country__country_name": None, "revenue": 40, "order_count": 2},
            ),
        ),
        QueryCase(
            "cross_fact_two_hop",
            ("revenue", "refund_amount"),
            ("customer__country__country_name",),
            (
                {"customer__country__country_name": "eastland", "revenue": 30, "refund_amount": 6},
                {"customer__country__country_name": "westland", "revenue": 30, "refund_amount": 3},
                {"customer__country__country_name": None, "revenue": 40, "refund_amount": 13},
            ),
        ),
        QueryCase("zero_denominator", ("revenue_per_zero",), (), ({"revenue_per_zero": None},)),
        QueryCase(
            "partition_time_only",
            ("partitioned_revenue", "partitioned_count"),
            (),
            ({"partitioned_revenue": 40, "partitioned_count": 1},),
            start_time=datetime(2026, 2, 2),
            end_time=datetime(2026, 2, 2, 23, 59, 59),
            capture_warehouse_plan=True,
        ),
        QueryCase(
            "partition_explicit_filter",
            ("partitioned_revenue", "partitioned_count"),
            (),
            ({"partitioned_revenue": 40, "partitioned_count": 1},),
            start_time=datetime(2026, 2, 2),
            end_time=datetime(2026, 2, 2, 23, 59, 59),
            where=("{{ Dimension('partitioned_order__ds') }} = '2026-02-02'",),
            capture_warehouse_plan=True,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the phase 1 regression and MaxCompute phase 2 suite.")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    run(
        arguments.live,
        arguments.output_root,
        phase="phase2",
        fixture_overlay=Path(__file__).parent,
        extra_cases=phase2_cases(),
        extra_tables=("countries", "refunds", "partitioned_orders"),
    )
