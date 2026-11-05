-- One row per calendar day, from the first movement to the last scheduled due date.
with bounds as (
    select
        least(
            (select min(movement_date) from {{ source('silver', 'inventory_movements') }}),
            (select min(release_date) from {{ source('silver', 'customer_schedules') }})
        ) as first_day,
        greatest(
            (select max(due_date) from {{ source('silver', 'customer_schedules') }}),
            (select max(promised_date) from {{ source('silver', 'purchase_orders') }})
        ) as last_day
),

days as (
    select explode(sequence(first_day, last_day, interval 1 day)) as date_day
    from bounds
)

select
    date_day,
    year(date_day) as year,
    month(date_day) as month,
    weekofyear(date_day) as iso_week,
    date_trunc('week', date_day)::date as week_start,
    date_format(date_day, 'EEEE') as weekday_name,
    dayofweek(date_day) not in (1, 7) as is_business_day
from days
