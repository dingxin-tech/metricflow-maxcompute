from __future__ import annotations

import logging
from datetime import datetime

import pytest
from metricflow_semantics.filters.time_constraint import TimeRangeConstraint
from metricflow_semantics.model.semantic_manifest_lookup import SemanticManifestLookup
from metricflow_semantics.specs.dunder_column_association_resolver import DunderColumnAssociationResolver

from metricflow.engine.metricflow_engine import MetricFlowEngine, MetricFlowQueryRequest
from metricflow.plan_conversion.to_sql_plan.dataflow_to_sql import DataflowToSqlPlanConverter
from metricflow.plan_conversion.to_sql_plan.maxcompute_partition import MaxComputePartitionMapping
from metricflow.protocols.sql_client import SqlClient, SqlEngine
from metricflow.sql.render.maxcompute import MaxComputeSqlPlanRenderer
from metricflow_semantic_interfaces.implementations.element_config import PydanticSemanticLayerElementConfig
from metricflow_semantic_interfaces.implementations.elements.dimension import PydanticDimension
from metricflow_semantic_interfaces.implementations.semantic_manifest import PydanticSemanticManifest
from metricflow_semantic_interfaces.type_enums import DimensionType, TimeGranularity

logger = logging.getLogger(__name__)


def config() -> dict[str, object]:
    """A bounded ingestion contract used for independent boundary expectations."""
    return dict(
        time_dimension="ordered_at",
        partition_dimension="ds",
        time_zone="UTC",
        partition_time_zone="Asia/Shanghai",
        max_early_arrival_seconds=32400,
        max_lateness_seconds=86400,
        partition_format="yyyy-mm-dd",
    )


@pytest.mark.parametrize(
    ("start", "grain", "overrides", "expected"),
    [
        ("2026-02-02", TimeGranularity.DAY, {}, ("2026-02-01", "2026-02-04")),
        ("2026-02-01", TimeGranularity.MONTH, {"max_early_arrival_seconds": 0}, ("2026-02-01", "2026-03-02")),
        (
            "2026-03-08",
            TimeGranularity.DAY,
            {
                "time_zone": "America/New_York",
                "partition_time_zone": "UTC",
                "max_early_arrival_seconds": 0,
                "max_lateness_seconds": 0,
            },
            ("2026-03-08", "2026-03-09"),
        ),
        (
            "2026-11-01T01:00",
            TimeGranularity.HOUR,
            {
                "time_zone": "America/New_York",
                "partition_time_zone": "Etc/GMT+6",
                "max_early_arrival_seconds": 0,
                "max_lateness_seconds": 0,
            },
            ("2026-10-31", "2026-11-01"),
        ),
        (
            "2026-03-08T02:00",
            TimeGranularity.HOUR,
            {
                "time_zone": "America/New_York",
                "partition_time_zone": "Etc/GMT+7",
                "max_early_arrival_seconds": 0,
                "max_lateness_seconds": 0,
            },
            ("2026-03-07", "2026-03-08"),
        ),
        ("2026-02-02", TimeGranularity.DAY, {"partition_format": "yyyymmdd"}, ("20260201", "20260204")),
    ],
)
def test_partition_bounds(
    start: str, grain: TimeGranularity, overrides: dict[str, object], expected: tuple[str, str]
) -> None:
    """Include whole buckets and both sides of clock changes; offsets are elapsed seconds."""
    settings = config()
    settings.update(overrides)
    instant = datetime.fromisoformat(start)
    mapping = MaxComputePartitionMapping.from_meta(settings)
    assert mapping.partition_bounds(TimeRangeConstraint(start_time=instant, end_time=instant), grain) == expected


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_lateness_seconds", -1),
        ("max_lateness_seconds", True),
        ("max_early_arrival_seconds", "0"),
        ("partition_format", "mm-dd-yyyy"),
        ("time_zone", ""),
        ("unexpected", 1),
    ],
)
def test_invalid_contract(key: str, value: object) -> None:
    """Reject typoed, unordered or unbounded mappings instead of risking silent data loss."""
    settings = config()
    settings[key] = value
    with pytest.raises(ValueError):
        MaxComputePartitionMapping.from_meta(settings)


def test_missing_lateness_is_not_zero() -> None:
    """Require an explicit bound even when no late data is allowed."""
    settings = config()
    del settings["max_lateness_seconds"]
    with pytest.raises(ValueError):
        MaxComputePartitionMapping.from_meta(settings)


@pytest.mark.parametrize("enabled", [False, True])
def test_compiler_uses_source_mapping(
    simple_semantic_manifest: PydanticSemanticManifest, sql_client: SqlClient, enabled: bool
) -> None:
    """Compile a real semantic graph and keep this opt-in optimization exclusive to MaxCompute."""
    settings = config()
    settings.update(time_dimension="ds", partition_dimension="ds_key")
    manifest = simple_semantic_manifest.copy(
        update={
            "semantic_models": [
                model.copy(
                    update={
                        "config": PydanticSemanticLayerElementConfig(meta={"maxcompute_partition_mapping": settings}),
                        "dimensions": tuple(model.dimensions)
                        + (PydanticDimension(name="ds_key", type=DimensionType.CATEGORICAL, is_partition=True),),
                    }
                )
                if model.name == "bookings_source"
                else model
                for model in simple_semantic_manifest.semantic_models
            ]
        }
    )
    lookup = SemanticManifestLookup(manifest)
    engine = MetricFlowEngine(semantic_manifest_lookup=lookup, sql_client=sql_client)
    plan = engine.explain(
        MetricFlowQueryRequest.create(
            metric_names=("bookings",),
            time_constraint_start=datetime(2026, 2, 2),
            time_constraint_end=datetime(2026, 2, 2),
        )
    ).dataflow_plan
    converted = DataflowToSqlPlanConverter(DunderColumnAssociationResolver(), lookup).convert_to_sql_plan(
        sql_engine_type=SqlEngine.MAXCOMPUTE if enabled else SqlEngine.DUCKDB, dataflow_plan_node=plan.sink_node
    )
    sql = MaxComputeSqlPlanRenderer().render_sql_plan(converted.sql_plan).sql
    assert ("ds_key >= '2026-02-01'" in sql) is enabled
    assert ("ds_key <= '2026-02-04'" in sql) is enabled
