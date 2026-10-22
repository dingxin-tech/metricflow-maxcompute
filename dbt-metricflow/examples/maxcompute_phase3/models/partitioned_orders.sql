{{ config(
    alias=var('table_prefix') ~ '_partitioned_orders',
    partition_by={"fields": "ds", "data_types": "string"}
) }}

select order_id, customer_id, ordered_at, amount,
       to_char(cast(ordered_at as datetime), 'yyyy-mm-dd') as ds
from {{ ref('orders') }}
