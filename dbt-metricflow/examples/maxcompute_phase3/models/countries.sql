{{ config(alias=var('table_prefix') ~ '_countries') }}

select 1 as country_id, 'eastland' as country_name
union all
select 2, 'westland'
