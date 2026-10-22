{{ config(alias=var('table_prefix') ~ '_customer_history') }}

select 1 as customer_id, 'legacy' as tier, cast('2026-01-01' as date) as valid_from, cast('2026-02-01' as date) as valid_to
union all select 1, 'gold', cast('2026-02-01' as date), cast(null as date)
union all select 2, 'bronze', cast('2026-01-01' as date), cast('2026-02-03' as date)
union all select 2, 'silver', cast('2026-02-03' as date), cast(null as date)
