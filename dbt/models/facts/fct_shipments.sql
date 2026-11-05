select
    shipment_doc,
    shipment_item,
    customer_code,
    material_code,
    shipment_date,
    quantity as shipped_qty
from {{ source('silver', 'shipments') }}
