{{ config(alias=var('table_prefix') ~ '_purchases') }}

-- Duplicate visitor/timestamp rows exercise per-event UUID attribution.
select 1 as purchase_id, 1 as visitor_id, cast('2026-02-02 00:00:00' as timestamp) as purchased_at
union all select 2, 1, cast('2026-02-02 00:00:00' as timestamp)
union all select 3, 2, cast('2026-02-02 00:00:00' as timestamp)
union all select 4, 3, cast('2026-02-02 00:00:00' as timestamp)
union all select 5, 4, cast('2026-01-31 00:00:00' as timestamp)
