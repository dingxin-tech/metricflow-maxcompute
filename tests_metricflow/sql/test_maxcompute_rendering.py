from __future__ import annotations

import logging

import pytest
from metricflow_semantics.errors.error_classes import UnsupportedEngineFeatureError
from metricflow_semantics.sql.sql_exprs import (
    SqlAddTimeExpression,
    SqlBetweenExpression,
    SqlDateTruncExpression,
    SqlExtractExpression,
    SqlIntegerExpression,
    SqlPercentileExpression,
    SqlPercentileExpressionArgument,
    SqlPercentileFunctionType,
    SqlStringExpression,
    SqlStringLiteralExpression,
    SqlSubtractTimeIntervalExpression,
)

from metricflow.sql.render.maxcompute import MaxComputeSqlExpressionRenderer
from metricflow_semantic_interfaces.type_enums import DatePart, TimeGranularity

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    ("function_type", "function_name"),
    [
        (SqlPercentileFunctionType.CONTINUOUS, "PERCENTILE_CONT"),
        (SqlPercentileFunctionType.DISCRETE, "PERCENTILE_DISC"),
        (SqlPercentileFunctionType.APPROXIMATE_CONTINUOUS, "PERCENTILE_APPROX"),
    ],
)
def test_maxcompute_percentile(function_type: SqlPercentileFunctionType, function_name: str) -> None:
    """Use column-first MaxCompute aggregates rather than WITHIN GROUP syntax."""
    expression = SqlPercentileExpression.create(
        order_by_arg=SqlStringExpression.create("amount"),
        percentile_args=SqlPercentileExpressionArgument(percentile=0.9, function_type=function_type),
    )
    argument = (
        "CAST(amount AS DOUBLE)" if function_type is SqlPercentileFunctionType.APPROXIMATE_CONTINUOUS else "amount"
    )
    assert MaxComputeSqlExpressionRenderer().render_sql_expr(expression).sql == f"{function_name}({argument}, 0.9)"


def test_maxcompute_rejects_approximate_discrete_percentile() -> None:
    """PERCENTILE_APPROX may interpolate; it cannot promise an input value."""
    with pytest.raises(UnsupportedEngineFeatureError):
        MaxComputeSqlExpressionRenderer().render_sql_expr(
            SqlPercentileExpression.create(
                order_by_arg=SqlStringExpression.create("amount"),
                percentile_args=SqlPercentileExpressionArgument(
                    percentile=0.5, function_type=SqlPercentileFunctionType.APPROXIMATE_DISCRETE
                ),
            )
        )


@pytest.mark.parametrize(
    ("grain", "unit"),
    [
        (TimeGranularity.YEAR, "year"),
        (TimeGranularity.QUARTER, "quarter"),
        (TimeGranularity.MONTH, "month"),
        (TimeGranularity.WEEK, "week"),
        (TimeGranularity.DAY, "day"),
        (TimeGranularity.HOUR, "hour"),
        (TimeGranularity.MINUTE, "mi"),
        (TimeGranularity.SECOND, "ss"),
        (TimeGranularity.MILLISECOND, "ff3"),
    ],
)
def test_maxcompute_time_expressions(grain: TimeGranularity, unit: str) -> None:
    """Use MaxCompute argument order and units for truncation and arithmetic."""
    renderer = MaxComputeSqlExpressionRenderer()
    argument = SqlStringExpression.create("src.created_at")
    assert renderer.render_sql_expr(SqlDateTruncExpression.create(arg=argument, time_granularity=grain)).sql == (
        f"DATETRUNC(src.created_at, '{unit}')"
    )
    assert (
        renderer.render_sql_expr(SqlSubtractTimeIntervalExpression.create(arg=argument, count=2, granularity=grain)).sql
        == f"DATEADD(src.created_at, -2, '{unit}')"
    )
    assert (
        renderer.render_sql_expr(
            SqlAddTimeExpression.create(arg=argument, count_expr=SqlIntegerExpression.create(2), granularity=grain)
        ).sql
        == f"DATEADD(src.created_at, 2, '{unit}')"
    )


@pytest.mark.parametrize("grain", [TimeGranularity.MICROSECOND, TimeGranularity.NANOSECOND])
def test_maxcompute_rejects_unsupported_granularity(grain: TimeGranularity) -> None:
    """Reject precision that DATETRUNC cannot preserve."""
    with pytest.raises(UnsupportedEngineFeatureError):
        MaxComputeSqlExpressionRenderer().render_sql_expr(
            SqlDateTruncExpression.create(arg=SqlStringExpression.create("created_at"), time_granularity=grain)
        )


@pytest.mark.parametrize(
    ("date_part", "expected"),
    [
        (DatePart.YEAR, "YEAR(created_at)"),
        (DatePart.QUARTER, "QUARTER(created_at)"),
        (DatePart.MONTH, "MONTH(created_at)"),
        (DatePart.DAY, "DAY(created_at)"),
        (DatePart.DOW, "(WEEKDAY(CAST(created_at AS DATETIME)) + 1)"),
        (DatePart.DOY, "DAYOFYEAR(created_at)"),
    ],
)
def test_maxcompute_date_parts(date_part: DatePart, expected: str) -> None:
    """Normalize date parts, including ISO weekday numbering."""
    assert (
        MaxComputeSqlExpressionRenderer()
        .render_sql_expr(SqlExtractExpression.create(arg=SqlStringExpression.create("created_at"), date_part=date_part))
        .sql
        == expected
    )


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (
            "2026-02-02",
            "2040-12-31",
            "created_at BETWEEN CAST('2026-02-02 00:00:00' AS TIMESTAMP) AND CAST('2040-12-31 00:00:00' AS TIMESTAMP)",
        ),
        (
            "2026-02-02T12:34:56",
            "2026-02-03 12:34:56.123456",
            "created_at BETWEEN CAST('2026-02-02 12:34:56' AS TIMESTAMP) AND CAST('2026-02-03 12:34:56.123456' AS TIMESTAMP)",
        ),
        ("alpha", "zulu", "created_at BETWEEN 'alpha' AND 'zulu'"),
    ],
)
def test_maxcompute_between_literals(start: str, end: str, expected: str) -> None:
    """Cast only ISO time bounds, preserving ordinary string comparisons."""
    node = SqlBetweenExpression.create(
        column_arg=SqlStringExpression.create("created_at"),
        start_expr=SqlStringLiteralExpression.create(start),
        end_expr=SqlStringLiteralExpression.create(end),
    )
    assert MaxComputeSqlExpressionRenderer().render_sql_expr(node).sql == expected


def test_maxcompute_between_expressions() -> None:
    """Preserve numeric expressions instead of treating them as date literals."""
    node = SqlBetweenExpression.create(
        column_arg=SqlStringExpression.create("value"),
        start_expr=SqlIntegerExpression.create(1),
        end_expr=SqlIntegerExpression.create(10),
    )
    assert MaxComputeSqlExpressionRenderer().render_sql_expr(node).sql == "value BETWEEN 1 AND 10"
