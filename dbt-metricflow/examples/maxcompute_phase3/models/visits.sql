{{ config(alias=var('table_prefix') ~ '_visits') }}

select 1 as visit_id, 1 as visitor_id, cast('2026-01-31 00:00:00' as timestamp) as visited_at
union all select 2, 2, cast('2026-01-31 00:00:00' as timestamp)
union all select 3, 1, cast('2026-02-01 00:00:00' as timestamp)
union all select 4, 3, cast('2026-02-01 00:00:00' as timestamp)
union all select 5, 4, cast('2026-02-01 00:00:00' as timestamp)
