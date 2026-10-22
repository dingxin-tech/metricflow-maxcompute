from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import datetime

from metricflow_semantics.errors.error_classes import UnsupportedEngineFeatureError
from metricflow_semantics.sql.sql_bind_parameters import SqlBindParameterSet
from metricflow_semantics.sql.sql_exprs import (
    SqlAddTimeExpression,
    SqlBetweenExpression,
    SqlDateTruncExpression,
    SqlExtractExpression,
    SqlPercentileExpression,
    SqlPercentileFunctionType,
    SqlStringLiteralExpression,
    SqlSubtractTimeIntervalExpression,
)
from typing_extensions import override

from metricflow.protocols.sql_client import SqlEngine
from metricflow.sql.render.expr_renderer import DefaultSqlExpressionRenderer, SqlExpressionRenderResult
from metricflow.sql.render.sql_plan_renderer import DefaultSqlPlanRenderer
from metricflow_semantic_interfaces.type_enums import DatePart, TimeGranularity

logger = logging.getLogger(__name__)


class MaxComputeSqlExpressionRenderer(DefaultSqlExpressionRenderer):
    """Render MaxCompute expressions using the ODPS 2.0 type system."""

    sql_engine = SqlEngine.MAXCOMPUTE

    @property
    @override
    def supported_percentile_function_types(self) -> Collection[SqlPercentileFunctionType]:
        return {
            SqlPercentileFunctionType.CONTINUOUS,
            SqlPercentileFunctionType.DISCRETE,
            SqlPercentileFunctionType.APPROXIMATE_CONTINUOUS,
        }

    @override
    def visit_percentile_expr(self, node: SqlPercentileExpression) -> SqlExpressionRenderResult:
        function_type = node.percentile_args.function_type
        if function_type not in self.supported_percentile_function_types:
            raise UnsupportedEngineFeatureError("MaxCompute does not provide approximate discrete percentiles")
        argument = self.render_sql_expr(node.order_by_arg)
        function_name = {
            SqlPercentileFunctionType.CONTINUOUS: "PERCENTILE_CONT",
            SqlPercentileFunctionType.DISCRETE: "PERCENTILE_DISC",
            SqlPercentileFunctionType.APPROXIMATE_CONTINUOUS: "PERCENTILE_APPROX",
        }[function_type]
        argument_sql = argument.sql
        if function_type is SqlPercentileFunctionType.APPROXIMATE_CONTINUOUS:
            # Unlike the exact aggregates, PERCENTILE_APPROX does not accept DECIMAL input.
            argument_sql = f"CAST({argument_sql} AS DOUBLE)"
        return SqlExpressionRenderResult(
            sql=f"{function_name}({argument_sql}, {node.percentile_args.percentile})",
            bind_parameter_set=argument.bind_parameter_set,
        )

    _TIME_UNITS = {
        TimeGranularity.MILLISECOND: "ff3",
        TimeGranularity.SECOND: "ss",
        TimeGranularity.MINUTE: "mi",
        TimeGranularity.HOUR: "hour",
        TimeGranularity.DAY: "day",
        TimeGranularity.WEEK: "week",
        TimeGranularity.MONTH: "month",
        TimeGranularity.QUARTER: "quarter",
        TimeGranularity.YEAR: "year",
    }

    @override
    def visit_date_trunc_expr(self, node: SqlDateTruncExpression) -> SqlExpressionRenderResult:
        self._validate_granularity_for_engine(node.time_granularity)
        rendered_arg = self.render_sql_expr(node.arg)
        return SqlExpressionRenderResult(
            sql=f"DATETRUNC({rendered_arg.sql}, '{self._TIME_UNITS[node.time_granularity]}')",
            bind_parameter_set=rendered_arg.bind_parameter_set,
        )

    @override
    def visit_subtract_time_interval_expr(self, node: SqlSubtractTimeIntervalExpression) -> SqlExpressionRenderResult:
        self._validate_granularity_for_engine(node.granularity)
        rendered_arg = self.render_sql_expr(node.arg)
        return SqlExpressionRenderResult(
            sql=f"DATEADD({rendered_arg.sql}, {-node.count}, '{self._TIME_UNITS[node.granularity]}')",
            bind_parameter_set=rendered_arg.bind_parameter_set,
        )

    @override
    def visit_add_time_expr(self, node: SqlAddTimeExpression) -> SqlExpressionRenderResult:
        self._validate_granularity_for_engine(node.granularity)
        rendered_arg = self.render_sql_expr(node.arg)
        rendered_count = self.render_sql_expr(node.count_expr)
        return SqlExpressionRenderResult(
            sql=f"DATEADD({rendered_arg.sql}, {rendered_count.sql}, '{self._TIME_UNITS[node.granularity]}')",
            bind_parameter_set=SqlBindParameterSet.merge_iterable(
                (rendered_arg.bind_parameter_set, rendered_count.bind_parameter_set)
            ),
        )

    @override
    def visit_extract_expr(self, node: SqlExtractExpression) -> SqlExpressionRenderResult:
        rendered_arg = self.render_sql_expr(node.arg)
        if node.date_part is DatePart.DOW:
            # WEEKDAY returns Monday=0; MetricFlow requires ISO Monday=1.
            sql = f"(WEEKDAY(CAST({rendered_arg.sql} AS DATETIME)) + 1)"
        elif node.date_part is DatePart.DOY:
            sql = f"DAYOFYEAR({rendered_arg.sql})"
        else:
            sql = f"{node.date_part.value.upper()}({rendered_arg.sql})"
        return SqlExpressionRenderResult(sql=sql, bind_parameter_set=rendered_arg.bind_parameter_set)

    @override
    def visit_between_expr(self, node: SqlBetweenExpression) -> SqlExpressionRenderResult:
        start_literal = node.start_expr.as_string_literal_expression
        end_literal = node.end_expr.as_string_literal_expression
        if start_literal is None or end_literal is None:
            return super().visit_between_expr(node)
        normalized_bounds: list[str] = []
        for literal in (start_literal, end_literal):
            try:
                parsed_bound = datetime.fromisoformat(literal.literal_value)
            except ValueError:
                return super().visit_between_expr(node)
            if parsed_bound.tzinfo is not None:
                return super().visit_between_expr(node)
            # DATE-only strings do not reliably coerce to TIMESTAMP in BETWEEN.
            # e.g. '2026-02-02' needs CAST('2026-02-02 00:00:00' AS TIMESTAMP).
            normalized_bound = literal.literal_value.replace("T", " ")
            if len(normalized_bound) == 10:
                normalized_bound += " 00:00:00"
            rendered_bound = self.render_sql_expr(SqlStringLiteralExpression.create(normalized_bound))
            normalized_bounds.append(f"CAST({rendered_bound.sql} AS {self.timestamp_data_type})")
        rendered_arg = self.render_sql_expr(node.column_arg)
        return SqlExpressionRenderResult(
            sql=f"{rendered_arg.sql} BETWEEN {normalized_bounds[0]} AND {normalized_bounds[1]}",
            bind_parameter_set=rendered_arg.bind_parameter_set,
        )


class MaxComputeSqlPlanRenderer(DefaultSqlPlanRenderer):
    """Render MaxCompute plans; execution delegates to the dbt MaxCompute adapter."""

    EXPR_RENDERER = MaxComputeSqlExpressionRenderer()
