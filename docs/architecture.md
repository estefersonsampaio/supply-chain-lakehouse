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
- facts: `fct_customer_schedule` (latest firm release per day), `fct_inventory_daily`, `fct_purchase_receipts`, `fct_shipments`.

KPI marts:

| KPI | Definition (first version) |
|---|---|
| Stock coverage (days) | Current stock divided by average daily firm demand for the next N days |
| Stockout risk | Materials whose projected stock goes below safety stock within the supplier lead time |
| Supplier lead time and on-time rate | Days from order to receipt, and share of lines received by the promised date |
| Schedule adherence | Shipped quantity versus scheduled quantity per customer, material and day |

dbt tests: uniqueness and not-null on keys, relationships between facts and dimensions, accepted values, and business rules (for example: no receipt before its purchase order).

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
| Silver rules as pure functions tested on local Spark | Fast feedback without a cluster, same ANSI SQL behaviour as Databricks serverless |
| Simulated data only | No real company data, not even anonymized |

## Findings on Databricks Free Edition

- The Databricks CLI works with OAuth login (no personal token stored), and Asset Bundles deploy schemas, volumes and jobs.
- Jobs run on serverless compute; a small run takes about 3 minutes including start-up.
- There is one serverless SQL warehouse (2X-Small), which dbt will use.
- External cloud storage (ADLS or S3) cannot be registered: only Databricks-managed storage exists. **Decision:** the landing zone is a Unity Catalog volume. Reading from external cloud storage stays as a next step for a paid workspace.

## Still to check

- Dashboard limits and scheduling a job on Free Edition.
