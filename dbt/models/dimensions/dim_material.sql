select
    m.material_code,
    m.description,
    m.material_type,
    case m.material_type when 'PA' then 'finished product' else 'component' end
        as material_type_name,
    m.unit,
    m.lead_time_days,
    m.safety_stock,
    m.main_supplier_code,
    s.name as main_supplier_name,
    coalesce(s.country <> 'BR', false) as is_imported
from {{ source('silver', 'materials') }} as m
left join {{ source('silver', 'suppliers') }} as s
    on m.main_supplier_code = s.supplier_code
