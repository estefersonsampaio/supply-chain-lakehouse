-- Stock coverage and stockout risk per material and business day.
--
-- Daily demand:
--   finished products (PA): average firm customer demand over the next N business days
--   components (MP):        average consumption over the last N business days
-- Coverage = closing stock / daily demand, in business days.
--
-- Risk:
--   components (MP) follow MRP logic: what we have plus what is already on order, minus
--   what we will use until a new order could arrive, must stay above safety stock.
--     projected_stock = closing stock + open purchase orders
--                       - daily demand x purchase lead time (business days)
--     at risk         = projected_stock < safety stock, or stock already below safety
--                       stock, or no stock at all
--   finished products (PA) are produced every day, so the signal is production not
--   keeping up: stock below safety stock, or no stock at all.
-- overdue_qty: quantity still open on purchase order lines past their promised date.
-- An order counted as "on the way" may not be on the way at all.
{% set n = var('coverage_horizon_days') %}

with firm_demand as (
    select material_code, due_date, sum(scheduled_qty) as firm_qty
    from {{ ref('fct_customer_schedule') }}
    where is_firm
    group by material_code, due_date
),

ordered as (
    select material_code, order_date as day, sum(ordered_qty) as qty
    from {{ ref('fct_purchase_lines') }}
    group by material_code, order_date
),

received as (
    select r.material_code, r.receipt_date as day, sum(r.quantity) as qty
    from {{ source('silver', 'goods_receipts') }} as r
    inner join {{ ref('fct_purchase_lines') }} as p
        on r.po_number = p.po_number and r.po_item = p.po_item
    group by r.material_code, r.receipt_date
),

overdue_line_days as (
    select p.material_code, d.date_day, p.po_number, p.po_item, p.ordered_qty
    from {{ ref('fct_purchase_lines') }} as p
    inner join {{ ref('dim_date') }} as d
        on d.is_business_day and d.date_day > p.promised_date
),

overdue as (
    select material_code, date_day, sum(greatest(open_qty, 0)) as overdue_qty
    from (
        select
            l.material_code,
            l.date_day,
            l.ordered_qty - coalesce(sum(r.quantity), 0) as open_qty
        from overdue_line_days as l
        left join {{ source('silver', 'goods_receipts') }} as r
            on l.po_number = r.po_number
            and l.po_item = r.po_item
            and r.receipt_date <= l.date_day
        group by l.material_code, l.date_day, l.po_number, l.po_item, l.ordered_qty
    )
    group by material_code, date_day
),

base as (
    select
        inv.material_code,
        inv.date_day,
        inv.closing_stock,
        m.material_type,
        m.safety_stock,
        case
            when m.material_type = 'PA' then 2
            else cast(ceil(m.lead_time_days * 5 / 7) as int)
        end as replenishment_days,
        case
            when m.material_type = 'PA' then coalesce(f.firm_qty, 0)
            else inv.consumed_qty
        end as demand_qty,
        coalesce(o.qty, 0) as ordered_qty,
        coalesce(r.qty, 0) as received_qty,
        coalesce(od.overdue_qty, 0) as overdue_qty
    from {{ ref('fct_inventory_daily') }} as inv
    inner join {{ ref('dim_material') }} as m
        on inv.material_code = m.material_code
    left join firm_demand as f
        on inv.material_code = f.material_code and inv.date_day = f.due_date
    left join ordered as o
        on inv.material_code = o.material_code and inv.date_day = o.day
    left join received as r
        on inv.material_code = r.material_code and inv.date_day = r.day
    left join overdue as od
        on inv.material_code = od.material_code and inv.date_day = od.date_day
),

with_windows as (
    select
        *,
        case
            when material_type = 'PA' then avg(demand_qty) over (
                partition by material_code order by date_day
                rows between 1 following and {{ n }} following
            )
            else avg(demand_qty) over (
                partition by material_code order by date_day
                rows between {{ n - 1 }} preceding and current row
            )
        end as avg_daily_demand,
        greatest(
            sum(ordered_qty - received_qty) over (
                partition by material_code order by date_day
                rows between unbounded preceding and current row
            ),
            0
        ) as on_order_qty
    from base
),

projected as (
    select
        *,
        closing_stock + on_order_qty - coalesce(avg_daily_demand, 0) * replenishment_days
            as projected_stock
    from with_windows
)

select
    material_code,
    date_day,
    material_type,
    closing_stock,
    on_order_qty,
    overdue_qty,
    overdue_qty > 0 as has_overdue_order,
    safety_stock,
    round(avg_daily_demand, 3) as avg_daily_demand,
    round(closing_stock / nullif(avg_daily_demand, 0), 1) as coverage_days,
    replenishment_days,
    round(projected_stock, 3) as projected_stock,
    closing_stock < safety_stock as is_below_safety_stock,
    closing_stock <= 0 as is_stockout,
    case
        when material_type = 'PA' then closing_stock < safety_stock or closing_stock <= 0
        else projected_stock < safety_stock or closing_stock < safety_stock or closing_stock <= 0
    end as is_at_risk
from projected
