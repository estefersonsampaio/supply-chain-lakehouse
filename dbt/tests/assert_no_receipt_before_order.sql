-- Business rule: goods cannot arrive before they were ordered.
select po_number, po_item, order_date, first_receipt_date
from {{ ref('fct_purchase_lines') }}
where first_receipt_date < order_date
