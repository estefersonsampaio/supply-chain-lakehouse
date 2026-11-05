-- One row per purchase order line, with what was received against it.
-- Lead time and lateness are measured on the last receipt, once the line is complete.
with receipts as (
    select
        po_number,
        po_item,
        sum(quantity) as received_qty,
        min(receipt_date) as first_receipt_date,
        max(receipt_date) as last_receipt_date,
        count(*) as receipt_count
    from {{ source('silver', 'goods_receipts') }}
    group by po_number, po_item
),

lines as (
    select
        po.po_number,
        po.po_item,
        po.supplier_code,
        po.material_code,
        po.unit,
        po.order_date,
        po.promised_date,
        po.quantity as ordered_qty,
        coalesce(r.received_qty, 0) as received_qty,
        r.first_receipt_date,
        r.last_receipt_date,
        coalesce(r.receipt_count, 0) as receipt_count,
        coalesce(r.received_qty, 0) >= po.quantity as is_fully_received
    from {{ source('silver', 'purchase_orders') }} as po
    left join receipts as r
        on po.po_number = r.po_number and po.po_item = r.po_item
)

select
    *,
    case when is_fully_received then datediff(last_receipt_date, order_date) end
        as lead_time_days,
    case when is_fully_received then datediff(last_receipt_date, promised_date) end
        as days_late,
    case when is_fully_received then last_receipt_date <= promised_date end
        as is_on_time
from lines
