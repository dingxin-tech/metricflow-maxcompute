# MaxCompute support and phase 3 verification

Run from `dbt-metricflow/` with the phase 1 credential environment:

```shell
hatch run maxcompute-env:python -m examples.maxcompute_phase3.verify --live \
  --output-root ../git_ignored/maxcompute-phase3
```

Use a regional HTTPS endpoint and the isolated `maxcompute-env` (PyODPS 0.13.2
or newer within the configured compatibility range). The suite builds ten
tables with unique aliases using normal `dbt run`, runs phase 1/2 regressions,
and checks results and native partition scans. It deletes only its own ten
aliases and verifies they are absent. Omit `--live` for parse/compile only.

## Explicit business-time to partition mapping

Configure this on the **semantic model**, next to `model: ref(...)`:

```yaml
config:
  meta:
    maxcompute_partition_mapping:
      time_dimension: ordered_at
      partition_dimension: ds
      time_zone: UTC
      partition_time_zone: Asia/Shanghai
      max_early_arrival_seconds: 32400
      max_lateness_seconds: 86400
      partition_format: yyyy-mm-dd
```

`ordered_at` must be a time dimension on this model. `ds` must be a categorical
dimension with `is_partition: true`, referring to the physical date partition
key. Allowed string formats are `yyyy-mm-dd` and `yyyymmdd`; both sort by date.
Every configuration field is required, unknown fields and negative/non-integer
bounds are rejected. Time zones must be IANA names understood by `zoneinfo`.

The mapping is a **hard data contract**, including backfills:

```text
event instant - max_early_arrival_seconds
    <= partition-generating arrival instant
    <= event instant + max_lateness_seconds
ds = date(arrival instant in partition_time_zone)
```

`time_zone` describes the wall-clock values of the evaluated time dimension
and the query bounds. It does not transform the business-time SQL expression,
change query grouping, or change warehouse session settings. For a raw TIMESTAMP
dimension, it must match the warehouse session's interpretation of that column.
If the dimension uses an expression to produce a different local clock, declare
that clock's zone. The example fixes the dbt connection timezone to UTC.

Only declare zero lateness if zero is guaranteed. If arrival delay/backfill is
unbounded, omit the entire mapping to retain the original full-scan behavior.
Rows that violate a declared contract may be excluded; the optimizer cannot
infer an ingestion SLA from current table contents.

For a UTC business-day query on February 2, the example expands to a full day,
converts to Shanghai time, and applies the early/late offsets. It adds:

```sql
ds >= '2026-02-01' AND ds <= '2026-02-04'
```

The original business-time predicate remains. No cast or date function is
applied to `ds`, allowing the warehouse to prune physical partitions. Both sides
of the daylight-saving fold/gap are included conservatively. The offsets are
elapsed seconds in UTC, rather than local calendar-day arithmetic.

The compiler uses the time constraint on the **input dataflow node**. A rolling
metric's lookback or a conversion query's extended input window is therefore
retained. An outer output-date range must not be applied to all fact tables.
No bounds means no automatic predicate. Missing/ambiguous source lineage or an
unavailable partition projection also causes a safe skip. Entity paths must
match, preventing a partition from a different join role from being constrained.
Only structured MetricFlow time constraints are used; raw SQL filter strings
are not parsed to invent bounds.

Previous-day offsets retain upstream's default INNER time-spine join: a date
without a matching prior source day is absent, rather than automatically filled
with zero or NULL. The example therefore returns February 1 through February 3.

## Covered capabilities

| Capability | Verification |
| --- | --- |
| Sum, count, distinct, average, min, max, sum_boolean | Cloud result comparison |
| Ratio and derived metrics, NULL groups and zero denominator | Cloud result comparison |
| Day/month/week grouping and time filters | Cloud result comparison |
| Cross-fact aggregation, sparse dates, two-hop dimension joins | Cloud result comparison |
| Explicit `ds` filtering and automatic mapped partition bounds | Cloud native scans and result comparison |
| Cumulative total, trailing two days, month-to-date, previous-day offset | Phase 3 cloud suite |
| Conversion count/rate, duplicate purchases, strict window boundary, future conversion window | Phase 3 cloud suite |
| SCD natural key, inclusive start/exclusive end, NULL-ended validity | Phase 3 cloud suite |
| Median, exact continuous/discrete percentile, approximate continuous percentile | Phase 3 cloud suite |
| DST fold/gap, date formats, missing/invalid mapping fields | Unit tests |

Approximate discrete percentiles are explicitly rejected: MaxCompute's
`PERCENTILE_APPROX` can interpolate and cannot guarantee an input value.
Microsecond/nanosecond truncation is explicitly rejected. The fixture does not
establish hosted dbt Semantic Layer deployment, arbitrary identifiers requiring
quoting, multi-SCD joins disallowed by upstream, or performance at production
scale. These are outside this adapter's phase 1–3 acceptance scope.

## Issues addressed

- Older PyODPS failed on catalog VECTOR metadata; the current environment uses
  0.13.2 and the full `dbt run` relation-cache path.
- MaxCompute does not compare DATE and TIMESTAMP implicitly. Semantic time
  projections, SCD validity bounds and time-spine projections are normalized to
  TIMESTAMP on the MaxCompute engine only.
- Date-only strings cast to TIMESTAMP may produce NULL. Generated time literals
  use full midnight components; fixture event timestamps do as well.
- The column pruner previously failed for a constant aggregate without input
  column dependencies. It now retains a column to preserve source row counts.
- Exact percentile aggregates use MaxCompute's column-first function syntax.
  Approximate percentiles require an explicit DOUBLE input cast for DECIMAL
  columns; the exact aggregates retain DECIMAL inputs.
- Native EXPLAIN text is read via PyODPS task results instead of a tabular reader.
  The capture uses the adapter's SQL hints, including support for the non-equi
  joins generated by cumulative metrics, and the fixture's UTC session zone.

Each run saves dbt artifacts/logs, SQL, dataflow plans, native plans, actual and
expected rows, scanned partitions, dependency versions and cleanup status.

## Final acceptance on 2026-10-22

Run `mf_phase3_20261022_092549_5043d50c` under
`git_ignored/maxcompute-acceptance/` at the repository root passed:

- Normal `dbt run`: all ten models built (PASS=10, ERROR=0).
- All 31 requests: compilation, warehouse EXPLAIN and actual/expected results.
- All six native-plan captures; all configured scan-partition assertions.
- Cleanup: all ten tables deleted and verified absent.

A separate prefix audit covering all twelve live attempts found no remaining
tables, including temporary names sharing those run prefixes. The audit is
saved as `git_ignored/maxcompute-acceptance/cleanup-audit.json`.

The mapped February 2 query reads four of seven partitions and returns revenue
90 / count 3, identical to the unmapped control. Its input includes data stored
in the previous arrival date and up to the second subsequent arrival date.
The rolling query reads six partitions for the planner's conservatively expanded
lookback and returns 140, identical to its unmapped control. An unbounded query
retains all seven partitions and returns 360 / 8.

Tested versions: dbt-core 1.12.6, dbt-adapters 1.24.5, dbt-maxcompute 1.11.4,
PyODPS 0.13.2, MetricFlow 0.214.0.dev0, Python 3.12.7.
Local regression: `make test` passed 1,964 tests (60 skipped); CLI passed 45
(2 skipped); `make lint` passed. DST fold/gap validation is unit-level;
the cloud mapping case validates UTC -> Asia/Shanghai and arrival bounds.
