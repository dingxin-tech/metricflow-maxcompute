{{ config(alias=var('table_prefix') ~ '_arrival_orders', partition_by={"fields": "ds", "data_types": "string"}) }}

-- ds is arrival date in Asia/Shanghai. Include exact early/late boundary cases.
select 1 as order_id, cast('2026-02-01 23:59:00' as timestamp) as ordered_at, cast(10 as double) as amount, '2026-02-02' as ds
union all select 2, cast('2026-02-02 00:01:00' as timestamp), 20, '2026-02-01'
union all select 3, cast('2026-02-02 13:00:00' as timestamp), 30, '2026-02-03'
union all select 4, cast('2026-02-02 23:59:00' as timestamp), 40, '2026-02-04'
union all select 5, cast('2026-02-03 00:01:00' as timestamp), 50, '2026-02-03'
union all select 6, cast('2026-02-05 12:00:00' as timestamp), 60, '2026-02-05'
union all select 7, cast('2026-01-31 12:00:00' as timestamp), 70, '2026-01-31'
union all select 8, cast('2026-02-07 12:00:00' as timestamp), 80, '2026-02-07'
