-- On-time delivery and lead time per supplier, over completed purchase order lines.
select
    s.supplier_code,
    s.name as supplier_name,
    s.country,
    s.is_importer,
    count(*) as lines_ordered,
    count_if(p.is_fully_received) as lines_completed,
    count_if(p.is_on_time) as lines_on_time,
    round(count_if(p.is_on_time) / nullif(count_if(p.is_fully_received), 0), 3) as on_time_rate,
    round(avg(p.lead_time_days), 1) as avg_lead_time_days,
    round(avg(case when p.days_late > 0 then p.days_late end), 1) as avg_days_late_when_late,
    max(p.days_late) as max_days_late
from {{ ref('fct_purchase_lines') }} as p
inner join {{ ref('dim_supplier') }} as s on p.supplier_code = s.supplier_code
group by s.supplier_code, s.name, s.country, s.is_importer
