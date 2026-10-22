{{ config(alias=var('table_prefix') ~ '_refunds') }}

select 1 as refund_id, 1 as customer_id, timestamp '2026-01-31 23:59:00' as refunded_at, cast(2 as decimal(18,2)) as refund_amount
union all
select 2, 1, timestamp '2026-02-01 00:01:00', cast(4 as decimal(18,2))
union all
select 3, 2, timestamp '2026-02-02 10:00:00', cast(3 as decimal(18,2))
union all
select 4, 3, timestamp '2026-02-04 10:00:00', cast(5 as decimal(18,2))
union all
select 5, 999, timestamp '2026-02-02 10:00:00', cast(7 as decimal(18,2))
union all
select 6, cast(null as bigint), timestamp '2026-02-02 10:00:00', cast(1 as decimal(18,2))
