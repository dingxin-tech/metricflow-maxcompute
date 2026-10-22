from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import cast
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from metricflow_semantics.filters.time_constraint import TimeRangeConstraint
from metricflow_semantics.instances import InstanceSet, TimeDimensionInstance
from metricflow_semantics.model.semantic_manifest_lookup import SemanticManifestLookup
from metricflow_semantics.sql.sql_exprs import (
    SqlColumnReferenceExpression,
    SqlComparison,
    SqlComparisonExpression,
    SqlExpressionNode,
    SqlLogicalExpression,
    SqlLogicalOperator,
    SqlStringLiteralExpression,
)

from metricflow_semantic_interfaces.type_enums import DimensionType, TimeGranularity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaxComputePartitionMapping:
    """An ingestion-time contract: event instant - early <= arrival instant <= event instant + late."""

    time_dimension: str
    partition_dimension: str
    time_zone: ZoneInfo
    partition_time_zone: ZoneInfo
    max_early_arrival_seconds: int
    max_lateness_seconds: int
    partition_format: str

    @staticmethod
    def from_meta(value: object) -> MaxComputePartitionMapping:
        """Validate an explicit mapping; missing bounds must never silently mean no late data."""
        if type(value) is not dict:  # noqa: E721 - accept only manifest JSON types, not subclasses
            raise ValueError("maxcompute_partition_mapping must be a mapping")
        config = cast(Mapping[str, object], value)
        fields = {
            "time_dimension",
            "partition_dimension",
            "time_zone",
            "partition_time_zone",
            "max_early_arrival_seconds",
            "max_lateness_seconds",
            "partition_format",
        }
        if set(config) != fields:
            raise ValueError(f"maxcompute_partition_mapping requires exactly {sorted(fields)}")
        for key in fields - {"max_early_arrival_seconds", "max_lateness_seconds"}:
            if type(config[key]) is not str or not config[key]:  # noqa: E721
                raise ValueError(f"{key} must be a non-empty string")
        for key in ("max_early_arrival_seconds", "max_lateness_seconds"):
            if type(config[key]) is not int or cast(int, config[key]) < 0:  # noqa: E721 - bool is not an integer bound
                raise ValueError(f"{key} must be a nonnegative integer")
        if config["partition_format"] not in ("yyyy-mm-dd", "yyyymmdd"):
            raise ValueError("partition_format must be yyyy-mm-dd or yyyymmdd")
        return MaxComputePartitionMapping(
            time_dimension=cast(str, config["time_dimension"]),
            partition_dimension=cast(str, config["partition_dimension"]),
            time_zone=ZoneInfo(cast(str, config["time_zone"])),
            partition_time_zone=ZoneInfo(cast(str, config["partition_time_zone"])),
            max_early_arrival_seconds=cast(int, config["max_early_arrival_seconds"]),
            max_lateness_seconds=cast(int, config["max_lateness_seconds"]),
            partition_format=cast(str, config["partition_format"]),
        )

    def partition_bounds(self, constraint: TimeRangeConstraint, grain: TimeGranularity) -> tuple[str, str]:
        """Cover complete inclusive time buckets, DST folds/gaps, and elapsed arrival offsets."""
        increments: Mapping[TimeGranularity, timedelta | relativedelta] = {
            TimeGranularity.MILLISECOND: timedelta(milliseconds=1),
            TimeGranularity.SECOND: timedelta(seconds=1),
            TimeGranularity.MINUTE: timedelta(minutes=1),
            TimeGranularity.HOUR: timedelta(hours=1),
            TimeGranularity.DAY: timedelta(days=1),
            TimeGranularity.WEEK: timedelta(days=7),
            TimeGranularity.MONTH: relativedelta(months=1),
            TimeGranularity.QUARTER: relativedelta(months=3),
            TimeGranularity.YEAR: relativedelta(years=1),
        }
        if grain not in increments:
            raise ValueError(f"Unsupported partition time grain: {grain}")
        start = constraint.start_time
        end = constraint.end_time
        if start.tzinfo is not None or end.tzinfo is not None:
            raise ValueError("MetricFlow time bounds must be naive wall times in the configured time_zone")
        # MetricFlow compares truncated buckets, including the whole last day/hour.
        end = end + increments[grain] - timedelta(microseconds=1)
        # Both folds conservatively cover repeated and nonexistent local times.
        start_utc = min(start.replace(tzinfo=self.time_zone, fold=fold).astimezone(timezone.utc) for fold in (0, 1))
        end_utc = max(end.replace(tzinfo=self.time_zone, fold=fold).astimezone(timezone.utc) for fold in (0, 1))
        first = (start_utc - timedelta(seconds=self.max_early_arrival_seconds)).astimezone(self.partition_time_zone)
        last = (end_utc + timedelta(seconds=self.max_lateness_seconds)).astimezone(self.partition_time_zone)
        date_format = "%Y-%m-%d" if self.partition_format == "yyyy-mm-dd" else "%Y%m%d"
        return first.strftime(date_format), last.strftime(date_format)


def partition_predicate(
    lookup: SemanticManifestLookup,
    instance_set: InstanceSet,
    time_instance: TimeDimensionInstance,
    constraint: TimeRangeConstraint,
    table_alias: str,
) -> SqlExpressionNode | None:
    """Add only source-proven predicates; skip if lineage or a projected partition is unavailable."""
    if len(time_instance.defined_from) != 1:
        return None
    origin = time_instance.defined_from[0]
    model = lookup.semantic_model_lookup.get_by_reference(origin.semantic_model_reference)
    if model is None or model.config is None or "maxcompute_partition_mapping" not in model.config.meta:
        return None
    mapping = MaxComputePartitionMapping.from_meta(model.config.meta["maxcompute_partition_mapping"])
    dimensions = {dimension.name: dimension for dimension in model.dimensions}
    if mapping.time_dimension not in dimensions or dimensions[mapping.time_dimension].type is not DimensionType.TIME:
        raise ValueError("Partition mapping time_dimension must name a time dimension on the same semantic model")
    partition = dimensions.get(mapping.partition_dimension)
    if partition is None or partition.type is not DimensionType.CATEGORICAL or not partition.is_partition:
        raise ValueError("Partition mapping partition_dimension must be a categorical is_partition dimension")
    if origin.element_name != mapping.time_dimension:
        return None
    candidates = [
        instance
        for instance in instance_set.dimension_instances
        if instance.spec.entity_links == time_instance.spec.entity_links
        and any(
            ref.semantic_model_name == model.name and ref.element_name == mapping.partition_dimension
            for ref in instance.defined_from
        )
    ]
    if len(candidates) != 1:
        logger.debug("Skipping MaxCompute partition pruning: partition column is not projected")
        return None
    grain = time_instance.spec.time_granularity
    assert grain is not None
    first, last = mapping.partition_bounds(constraint, grain.base_granularity)
    column = SqlColumnReferenceExpression.from_column_reference(
        table_alias=table_alias, column_name=candidates[0].associated_column.column_name
    )
    # Compare string partition keys directly, e.g. ds >= '2026-02-01'; no casts/functions on ds.
    return SqlLogicalExpression.create(
        operator=SqlLogicalOperator.AND,
        args=(
            SqlComparisonExpression.create(
                column, SqlComparison.GREATER_THAN_OR_EQUALS, SqlStringLiteralExpression.create(first)
            ),
            SqlComparisonExpression.create(
                column, SqlComparison.LESS_THAN_OR_EQUALS, SqlStringLiteralExpression.create(last)
            ),
        ),
    )
