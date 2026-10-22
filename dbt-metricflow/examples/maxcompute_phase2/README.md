# MaxCompute phase 2 verification

Run from `dbt-metricflow/`, using the same credential environment as phase 1:

```shell
hatch run maxcompute-env:python -m examples.maxcompute_phase2.verify --live \
  --output-root ../git_ignored/maxcompute-phase2
```

Prefer the HTTPS form of the regional `MAXCOMPUTE_ENDPOINT`. The Hatch
`maxcompute-env` requires PyODPS >=0.13.2,<0.14 and loads the local MetricFlow
checkout. Omit `--live` to parse the fixture and compile all requests locally.

This suite overlays the phase 1 project with a refunds fact table, a country
lookup, customer-to-country keys, and a physically partitioned orders model.
All six tables have unique run-specific aliases and a one-day lifecycle. They
are built by `dbt run`, and only those six known aliases are removed afterward.

It reruns all seven phase 1 cases and adds nine cases:

- Cross-fact totals and a derived net-revenue metric.
- Cross-fact daily results with dates present in only one source.
- NULL dimension keys across facts, including derived-metric results.
- Orders -> customers -> countries, including unmatched keys.
- Cross-fact combination through the same two-hop dimension path.
- A zero denominator, which must produce NULL.
- Business-time filtering versus explicit physical `ds` partition filtering.

The partition cases return the same expected metric values. Their native
MaxCompute EXPLAIN plans are saved separately so physical scans can be checked.
A correct result alone does not establish partition pruning. Declaring a
semantic dimension `is_partition` does not specify a mapping between an event
timestamp and an ingestion partition; the suite does not invent that mapping.

Each run retains dbt artifacts/logs, generated SQL, dataflow plans, native
partition EXPLAIN plans, actual/expected rows, dependency versions, and cleanup
status. No existing business table is modified and no project setting changes.

## Findings from cloud validation on 2026-10-22

The fixture uses Python 3.12.7, dbt-core 1.12.6, dbt-adapters 1.24.5,
dbt-maxcompute 1.11.4, PyODPS 0.13.2, and the local MetricFlow 0.214.0.dev0.

Evidence run: `mf_phase2_20261022_084316_8f77ef71` under
`git_ignored/maxcompute-phase2/` at the repository root. All six dbt models
built successfully; all 16 cases passed compilation, warehouse EXPLAIN, and
actual result comparison. Both native plans were collected successfully.
All six run-specific tables were deleted and verified absent.

The tested cross-fact requests and two-hop joins require no additional SQL
dialect rewrite. Sparse dates and dimensions preserve NULL values: a missing
revenue input does not become zero in `revenue - refund_amount`. The NULL
dimension group combines correctly across the two facts, and division by zero
returns NULL.

Native EXPLAIN's `Data source` confirms these scan scopes:

| Predicate | Physical `ds` partitions scanned | Revenue / count |
| --- | --- | --- |
| Business time on February 2 only | All four: January 31 through February 3 | 40 / 1 |
| Same time range plus explicit `ds = '2026-02-02'` | February 2 only | 40 / 1 |

Explicit partition filtering reaches the source and enables pruning. This
initial fixture has no automatic mapping. Explicitly configured automatic
pruning, including late-arriving data and timezone semantics, is implemented in
the [phase 3 suite](../maxcompute_phase3/README.md). `is_partition: true` alone
remains insufficient to derive a safe filter.
The time-only query is deliberately allowed to full-scan as a negative control.

PyODPS `Instance.open_reader()` cannot read this warehouse's textual EXPLAIN
response because it has no tabular schema. The verifier reads
`Instance.get_task_results()` instead. This affects plan collection, not metric
execution through the dbt adapter.
