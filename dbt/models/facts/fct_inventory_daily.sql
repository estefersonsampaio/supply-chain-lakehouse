-- Closing stock per material and business day, rebuilt from every movement:
-- initial balance + production + receipts - consumption - shipments.
-- Movement types below 500 are entries, 500 and above are exits.
with movements as (
    select
        material_code,
        movement_date as movement_day,
        case when cast(movement_type as int) < 500 then quantity else -quantity end as qty,
        case when movement_type = '501' then quantity else 0 end as consumed_qty
    from {{ source('silver', 'inventory_movements') }}

    union all

    select material_code, receipt_date, quantity, 0
    from {{ source('silver', 'goods_receipts') }}

    union all

    select material_code, shipment_date, -quantity, 0
    from {{ source('silver', 'shipments') }}
),

daily as (
    select
        material_code,
        movement_day,
        sum(qty) as net_qty,
        sum(consumed_qty) as consumed_qty
    from movements
    group by material_code, movement_day
),

bounds as (
    select min(movement_day) as first_day, max(movement_day) as last_day from daily
),

grid as (
    select m.material_code, d.date_day
    from {{ ref('dim_material') }} as m
    cross join {{ ref('dim_date') }} as d
    cross join bounds as b
    where d.is_business_day and d.date_day between b.first_day and b.last_day
)

select
    g.material_code,
    g.date_day,
    coalesce(d.net_qty, 0) as net_movement_qty,
    coalesce(d.consumed_qty, 0) as consumed_qty,
    sum(coalesce(d.net_qty, 0)) over (
        partition by g.material_code
        order by g.date_day
        rows between unbounded preceding and current row
    ) as closing_stock
from grid as g
left join daily as d
    on g.material_code = d.material_code and g.date_day = d.movement_day
