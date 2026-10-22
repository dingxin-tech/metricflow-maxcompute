{{ config(alias=var('table_prefix') ~ '_orders') }}

select 1 as order_id, 1 as customer_id, timestamp '2026-01-31 23:59:00' as ordered_at, cast(10 as decimal(18,2)) as amount
union all
select 2, 1, timestamp '2026-02-01 00:01:00', cast(20 as decimal(18,2))
union all
select 3, 2, timestamp '2026-02-01 13:00:00', cast(30 as decimal(18,2))
union all
select 4, 999, timestamp '2026-02-02 14:00:00', cast(40 as decimal(18,2))
union all
select 5, cast(null as bigint), timestamp '2026-02-03 15:00:00', cast(0 as decimal(18,2))
union all
select 6, 2, timestamp '2026-02-03 16:00:00', cast(null as decimal(18,2))
