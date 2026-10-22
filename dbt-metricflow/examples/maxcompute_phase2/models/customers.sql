{{ config(alias=var('table_prefix') ~ '_customers') }}

select 1 as customer_id, 'east' as region, 1 as country_id
union all
select 2, 'west', 2
union all
select 3, 'unused', cast(null as bigint)
