# MaxCompute phase 1 verification

This fixture exercises the real dbt adapter and MetricFlow compiler. It covers
sum, count, count-distinct, ratio, day/month/week grouping, a foreign-to-primary
dimension join, combined time/dimension grouping, and a time-range filter.
The data includes missing customer keys, NULL keys/amounts, and a month boundary.

Required environment variables:

- `MAXCOMPUTE_PROJECT`
- `MAXCOMPUTE_ENDPOINT`
- `ALIBABA_CLOUD_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
- Optional: `MAXCOMPUTE_SCHEMA` (default: `default`)

From `dbt-metricflow/`, compile without issuing warehouse queries:

```shell
hatch run maxcompute-env:python examples/maxcompute_phase1/verify.py \
  --output-root ../git_ignored/maxcompute-phase1
```

For actual warehouse verification, add `--live`. This creates three tiny,
non-partitioned fixture tables with a unique `mf_phase1_...` prefix and a one-day
lifecycle. The verifier parses the fixture project, creates every model through
`dbt run` with normal relation-cache population, compiles every metric query, executes warehouse
`EXPLAIN`, runs the queries through `AdapterBackedSqlClient`, compares results
against explicit expected rows, and deletes only the three tables for that run.
It does not use existing business tables or change project settings.

Each run preserves dbt logs, the copied project and generated semantic manifest,
SQL, dataflow plans, actual/expected results, and cleanup status under the output
directory. A failed query makes the verifier fail, rather than silently skip.

The profile reads credentials from the environment; it contains no secrets.
The semantic YAML uses the legacy specification accepted by dbt-core 1.11 and
1.12, matching the CLI's supported range. It is normalized by the manifest parser.

This first phase does not establish support for cumulative/conversion metrics,
SCDs, arbitrary identifier quoting, physical partition pruning, or hosted dbt
Semantic Layer service deployment. Microsecond/nanosecond truncation is rejected
explicitly. The implementation assumes the ODPS 2.0 type system; the dbt adapter
supplies its normal SQL hints.

For automatic partition pruning and advanced metrics, see the
[phase 3 support guide](../maxcompute_phase3/README.md).

Use PyODPS 0.13.2 or newer, as configured in `maxcompute-env`. Older PyODPS
releases failed to deserialize existing VECTOR columns during relation-cache
population. The verifier now uses the full `dbt run` path without bypassing
that scan. For environments with intermittent HTTP connection resets, use the
HTTPS form of the same regional MaxCompute endpoint.

## Full-chain validation on 2026-10-22

`dbt run` created all three models (PASS=3, ERROR=0), and all seven metric cases
passed compilation, warehouse EXPLAIN, and result comparison. All three tables
were deleted and verified absent. The run used HTTPS, normal catalog scanning,
and the local MetricFlow checkout (explicitly selected with Hatch's PYTHONPATH).
Evidence run: `mf_phase1_20261022_083432_2ab1ff89` under
`git_ignored/maxcompute-fullchain/` at the repository root.

## Earlier CTAS-backed validation on 2026-10-22

The cloud verification passed all seven cases: single-table metrics,
day grouping, month grouping, week grouping, dimension join, month plus region,
and time-range filtering. Every case passed compilation, warehouse EXPLAIN,
execution through the dbt adapter, and comparison with expected results.
The fixture includes month-end 23:59 and next-month 00:01 timestamps.

Tested cloud environment: Python 3.12.7, dbt-core 1.12.6, dbt-adapters 1.24.5,
dbt-maxcompute 1.11.4, PyODPS 0.13.2, and this checkout's MetricFlow 0.214.0.dev0.
All three final-run fixture tables were removed; a separate audit found none
of the twelve uniquely named tables from all four attempts remaining.

Local checks: `make test` passed 1,941 tests (60 skipped); the CLI suite in
`maxcompute-env` passed 45 tests (2 skipped); `make lint` passed.

Issues found during verification:

- Bare date strings in a TIMESTAMP `BETWEEN` predicate passed EXPLAIN but returned
  empty aggregates. The renderer now emits explicit TIMESTAMP casts with full
  midnight time components, and the real time-filter case passes.
- The existing Python environment's older PyODPS could not deserialize an
  unrelated VECTOR column during `dbt run`'s relation-cache scan. The earlier
  CTAS setup bypassed this issue; the full-chain run above uses PyODPS 0.13.2
  and passes the normal scan.
- A prior HTTP run had connection resets in two read operations. The final run
  with the isolated dependency environment completed all seven cases without
  retries; this does not establish a general network reliability guarantee.
- With Hatch's uv installer, the old unqualified `pip` post-install hook resolved
  to a system Python 2 pip. The hook now bootstraps pip in the environment and
  invokes it through that environment's Python.
