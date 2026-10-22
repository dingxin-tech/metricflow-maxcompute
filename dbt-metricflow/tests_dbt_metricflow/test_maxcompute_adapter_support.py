from __future__ import annotations

import logging

import pytest

from dbt_metricflow.cli.dbt_connectors.adapter_backed_client import AdapterBackedSqlClient, SupportedAdapterTypes
from metricflow.protocols.sql_client import SqlEngine
from metricflow.sql.render.maxcompute import MaxComputeSqlPlanRenderer

logger = logging.getLogger(__name__)
MaxComputeAdapter = pytest.importorskip("dbt.adapters.maxcompute.impl").MaxComputeAdapter


def test_maxcompute_adapter_registration() -> None:
    """Resolve the real adapter's type through the CLI registration boundary."""
    adapter_type = SupportedAdapterTypes(MaxComputeAdapter.type())
    assert adapter_type.sql_engine_type is SqlEngine.MAXCOMPUTE
    assert type(adapter_type.sql_plan_renderer) is MaxComputeSqlPlanRenderer


def test_maxcompute_adapter_client() -> None:
    """Client construction only requires adapter identity, without opening a connection."""
    adapter = MaxComputeAdapter.__new__(MaxComputeAdapter)
    client = AdapterBackedSqlClient(adapter)
    assert client.sql_engine_type is SqlEngine.MAXCOMPUTE
    assert type(client.sql_plan_renderer) is MaxComputeSqlPlanRenderer
