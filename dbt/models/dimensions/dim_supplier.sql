select
    supplier_code,
    name,
    country,
    country <> 'BR' as is_importer
from {{ source('silver', 'suppliers') }}
