# Architecture and design decisions

Status: draft, written before the first line of pipeline code. It will be updated as the project evolves.

## The business problem

An auto-parts supplier receives delivery schedules from its automaker customers every day. Each new schedule revises the previous one: quantities change, dates move, firm orders become forecasts and back. The planning team has to answer, every morning:

- Do we have enough stock to cover the next weeks of customer demand?
- Which materials are about to run out?
- Are our suppliers (many of them importers) delivering on time?
- Are we shipping what the customer scheduled, when they scheduled it?

In the ERP world this is the job of an MRP process. The data behind it is messy: codes typed by hand, units that do not match, duplicated records from re-sent files, dates that do not exist. This project rebuilds that analytical side with a modern lakehouse stack, using **simulated data only**.

## High-level flow

```
Python generator  ──>  landing (Unity Catalog volume, CSV files, one folder per extract)
                            │
                            ▼
                    bronze  (Delta, append-only, incremental ingestion, raw columns + metadata)
                            │
                            ▼
                    silver  (Delta, cleaned, typed, deduplicated, English column names,
                             rejected rows kept in quarantine tables)
                            │
                            ▼
                    gold    (dbt models: star schema + KPI marts, with tests and docs)
                            │
                            ▼
                    Databricks AI/BI dashboard
```

Everything is orchestrated by one Databricks Job, deployed from this repository as code (Databricks Asset Bundles).

## Source extracts (simulated ERP)

The raw files imitate typical ERP extracts: short uppercase column names and codes padded with spaces. Silver translates them into clean English names. The mapping is documented in `docs/data-dictionary.md` (to be written with the generator).

| Extract | What it holds | Load pattern |
|---|---|---|
| `materials` | Material master: code, description, type (finished, component, raw), unit, lead time, safety stock, main supplier | Full snapshot, daily |
| `bom` | Bill of materials: parent, component, quantity per | Full snapshot, daily |
| `suppliers` | Supplier master, with a flag for importers | Full snapshot, daily |
| `customers` | Customer master (anonymous automakers: `OEM_A`, `OEM_B`...) | Full snapshot, daily |
| `customer_schedules` | Daily delivery schedule per customer and material, firm or forecast | Incremental: one new release per customer per day, revising earlier ones |
| `purchase_orders` | Purchase order lines: supplier, material, quantity, order date, promised date | Incremental |
| `goods_receipts` | Receipts against purchase order lines | Incremental |
| `inventory_movements` | Stock movements in and out per warehouse | Incremental |
| `shipments` | Shipments to customers | Incremental |

## Planted data problems

The generator injects realistic problems on purpose, at a configurable rate, so silver has real work to do:

- duplicated rows (the same file sent twice);
- codes with trailing spaces or lowercase letters;
- invalid dates (`00000000`, 31 November);
- different units for the same thing (`PC`, `UN`, `pcs`; `KG` and `G`);
- negative or zero quantities where they make no sense;
- references to materials or suppliers that do not exist.

Rows that cannot be fixed go to quarantine tables with the reason, instead of being silently dropped.

## Gold layer (dbt)

Star schema:

- dimensions: `dim_material`, `dim_supplier`, `dim_customer`, `dim_date`;
- facts: `fct_customer_schedule` (quantity of the latest release issued before each due date), `fct_shipments`, `fct_purchase_lines` (ordered vs received per order line), `fct_inventory_daily` (closing stock per material and business day, rebuilt from all movements).

KPI models:

| KPI | Definition |
|---|---|
| Stock coverage (days) | Closing stock / average daily demand. Finished products: firm customer demand over the next 10 business days. Components: consumption over the last 10 business days |
| Stockout risk (components) | Projected stock = stock + open purchase orders − daily demand × lead time (business days). At risk if projected stock or current stock is below safety stock, or stock is zero. Open quantity past its promised date is reported as overdue |
| Stockout risk (finished products) | Produced every day, so at risk when stock is below safety stock or zero (production is not keeping up) |
| Supplier lead time and on-time rate | Days from order to the last receipt, and share of completed lines received by the promised date |
| Schedule adherence | min(shipped, scheduled) / scheduled per customer, material and day, for firm demand |

dbt tests: uniqueness and not-null on keys, relationships between facts and dimensions, accepted values, value ranges and business rules (no receipt before its order, no receipt above the ordered quantity). Negative rebuilt stock is a warning, because quarantined movements can cause it.

## Key decisions

| Decision | Why |
|---|---|
| Databricks Free Edition | Free, and Databricks plus Spark appear in a large share of junior data engineering job posts in Spain |
| Code in the repository, not in notebooks only | Reviewable, testable and deployable; notebooks are used only where they add value |
| Incremental and idempotent ingestion | Re-running a day must not duplicate data |
| dbt for gold | SQL with tests, documentation and lineage |
| Quarantine instead of dropping bad rows | Data problems must be visible, as they are in a real migration or integration |
| Silver as a full refresh | Seconds at this volume and always safe to re-run; incremental MERGE is a next step |
| A data quality gate in silver | Detected problems are reconciled with the generator manifests; any difference fails the job |
| Risk KPI counts open orders, but flags overdue ones | A first version ignored open orders and flagged every imported component; a second one trusted them blindly and only flagged a stockout on the day it happened. The final rule matches how a planner reads it |
| Quarantine with a status, resolved by the source | Problems are fixed in the ERP, not in the pipeline; the ERP record number links the corrected row to the quarantined one, so the team sees what is open and for how long |
| Silver rules as pure functions tested on local Spark | Fast feedback without a cluster, same ANSI SQL behaviour as Databricks serverless |
| Simulated data only | No real company data, not even anonymized |

## Findings on Databricks Free Edition

- The Databricks CLI works with OAuth login (no personal token stored), and Asset Bundles deploy schemas, volumes and jobs.
- Jobs run on serverless compute; a small run takes about 3 minutes including start-up.
- There is one serverless SQL warehouse (2X-Small), which dbt will use.
- External cloud storage (ADLS or S3) cannot be registered: only Databricks-managed storage exists. **Decision:** the landing zone is a Unity Catalog volume. Reading from external cloud storage stays as a next step for a paid workspace.

## Still to check

- Dashboard limits and scheduling a job on Free Edition.
