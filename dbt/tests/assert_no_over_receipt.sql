-- Business rule: a purchase order line cannot receive more than was ordered.
select po_number, po_item, ordered_qty, received_qty
from {{ ref('fct_purchase_lines') }}
where received_qty > ordered_qty
