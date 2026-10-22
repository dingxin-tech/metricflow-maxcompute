{{ config(alias=var('table_prefix') ~ '_time_spine') }}

select date '2026-01-31' as date_day
union all
select date '2026-02-01'
union all
select date '2026-02-02'
union all
select date '2026-02-03'
