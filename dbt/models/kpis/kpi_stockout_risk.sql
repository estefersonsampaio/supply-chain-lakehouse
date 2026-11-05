-- The planner's morning list: materials at risk on the latest business day, with how
-- long they have been at risk and who supplies them.
with latest as (
    select max(date_day) as last_day from {{ ref('kpi_stock_coverage') }}
),

streak as (
    select
        material_code,
        count_if(is_at_risk) as days_at_risk_last_2_weeks
    from {{ ref('kpi_stock_coverage') }}
    where date_day > date_sub((select last_day from latest), 14)
    group by material_code
)

select
    c.date_day as as_of,
    c.material_code,
    m.description,
    m.material_type_name,
    m.main_supplier_name,
    m.is_imported,
    c.closing_stock,
    c.on_order_qty,
    c.overdue_qty,
    c.projected_stock,
    c.safety_stock,
    c.coverage_days,
    c.replenishment_days,
    c.is_stockout,
    s.days_at_risk_last_2_weeks
from {{ ref('kpi_stock_coverage') }} as c
inner join latest as l on c.date_day = l.last_day
inner join {{ ref('dim_material') }} as m on c.material_code = m.material_code
inner join streak as s on c.material_code = s.material_code
where c.is_at_risk
