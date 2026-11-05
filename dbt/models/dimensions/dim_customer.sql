select
    customer_code,
    name,
    country
from {{ source('silver', 'customers') }}
