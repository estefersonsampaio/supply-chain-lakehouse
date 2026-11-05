-- Physical stock cannot be negative. In the generated data it never is, but silver
-- quarantines some movements (impossible dates, bad quantities, unknown materials), and
-- the stock rebuilt without them can dip below zero. That is a real consequence of
-- source data problems, so this test warns instead of failing the build.
{{ config(severity='warn') }}

select material_code, date_day, closing_stock
from {{ ref('fct_inventory_daily') }}
where closing_stock < 0
