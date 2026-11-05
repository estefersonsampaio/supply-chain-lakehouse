-- What each customer finally asked for, per material and due date: the quantity in the
-- latest release issued before that date. Every release revises the previous ones, so
-- only the last word counts.
with ranked as (
    select
        customer_code,
        material_code,
        due_date,
        release_number,
        release_date,
        quantity,
        schedule_type,
        row_number() over (
            partition by customer_code, material_code, due_date
            order by release_date desc, release_number desc
        ) as rn
    from {{ source('silver', 'customer_schedules') }}
    where release_date < due_date
)

select
    customer_code,
    material_code,
    due_date,
    release_number as last_release_number,
    release_date as last_release_date,
    quantity as scheduled_qty,
    schedule_type = 'F' as is_firm
from ranked
where rn = 1
