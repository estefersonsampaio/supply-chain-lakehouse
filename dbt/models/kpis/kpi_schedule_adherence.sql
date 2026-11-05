-- Did we ship what the customer scheduled, on the day they scheduled it?
-- One row per customer, material and business day with firm demand, up to the last
-- shipment date. Adherence caps at 100%: shipping more does not compensate a short day.
with shipped as (
    select customer_code, material_code, shipment_date, sum(shipped_qty) as shipped_qty
    from {{ ref('fct_shipments') }}
    group by customer_code, material_code, shipment_date
),

last_shipment as (
    select max(shipment_date) as last_day from shipped
)

select
    s.customer_code,
    c.name as customer_name,
    s.material_code,
    s.due_date,
    d.week_start,
    s.scheduled_qty,
    coalesce(sh.shipped_qty, 0) as shipped_qty,
    least(coalesce(sh.shipped_qty, 0), s.scheduled_qty) as on_schedule_qty,
    round(least(coalesce(sh.shipped_qty, 0), s.scheduled_qty) / s.scheduled_qty, 3)
        as adherence
from {{ ref('fct_customer_schedule') }} as s
inner join {{ ref('dim_customer') }} as c on s.customer_code = c.customer_code
inner join {{ ref('dim_date') }} as d on s.due_date = d.date_day
left join shipped as sh
    on s.customer_code = sh.customer_code
    and s.material_code = sh.material_code
    and s.due_date = sh.shipment_date
where
    s.is_firm
    and s.scheduled_qty > 0
    and s.due_date <= (select last_day from last_shipment)
