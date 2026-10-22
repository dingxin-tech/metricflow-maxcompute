from __future__ import annotations

import logging
import sqlite3

import pytest
from metricflow_semantics.sql.sql_exprs import (
    SqlAggregateFunctionExpression,
    SqlColumnReferenceExpression,
    SqlFunction,
    SqlIntegerExpression,
)
from metricflow_semantics.sql.sql_table import SqlTable

from metricflow.sql.optimizer.column_pruning.column_pruner import SqlColumnPrunerOptimizer
from metricflow.sql.render.sql_plan_renderer import DefaultSqlPlanRenderer
from metricflow.sql.sql_plan import SqlPlan, SqlSelectColumn
from metricflow.sql.sql_select_node import SqlSelectStatementNode
from metricflow.sql.sql_table_node import SqlTableNode

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("distinct", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_sum_constant_preserves_rows(distinct: bool, empty: bool) -> None:
    """A constant aggregate depends on row multiplicity, including DISTINCT and empty sources."""
    source = SqlSelectStatementNode.create(
        description="source",
        select_columns=(
            SqlSelectColumn(
                expr=SqlColumnReferenceExpression.from_column_reference(table_alias="t", column_name="value"),
                column_alias="value",
            ),
        ),
        from_source=SqlTableNode.create(SqlTable(schema_name="main", table_name="input_rows")),
        from_source_alias="t",
        distinct=distinct,
    )
    aggregate = SqlSelectStatementNode.create(
        description="count rows",
        select_columns=(
            SqlSelectColumn(
                expr=SqlAggregateFunctionExpression.create(
                    sql_function=SqlFunction.SUM, sql_function_args=(SqlIntegerExpression.create(1),)
                ),
                column_alias="n",
            ),
        ),
        from_source=source,
        from_source_alias="source",
    )
    optimized = SqlColumnPrunerOptimizer().optimize(aggregate)
    renderer = DefaultSqlPlanRenderer()
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE input_rows (value INT)")
        if not empty:
            connection.executemany("INSERT INTO input_rows VALUES (?)", ((1,), (1,), (2,)))
        expected = None if empty else (2 if distinct else 3)
        for plan_node in (aggregate, optimized):
            sql = renderer.render_sql_plan(SqlPlan(render_node=plan_node)).sql
            assert connection.execute(sql).fetchall() == [(expected,)]
