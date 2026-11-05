# Supply chain lakehouse

> **ES:** Pipeline de datos de supply chain (MRP de un proveedor de autopartes) en Databricks: ingesta incremental, capas bronze/silver/gold, modelado con dbt, tests de calidad de datos y orquestación como código. Proyecto de portfolio con datos simulados. **En construcción.**

**Status: work in progress.** This README will grow with the project.

## What this is

A portfolio project that rebuilds the analytical side of an MRP (material requirements planning) process for an auto-parts supplier, using a modern lakehouse stack:

- a Python generator of realistic, messy ERP extracts;
- incremental ingestion into Delta tables (bronze);
- cleaning, typing and deduplication with PySpark (silver);
- a star schema and supply chain KPIs modelled with dbt, with data quality tests (gold);
- one Databricks Job that runs the whole flow, deployed from this repository.

The idea comes from real work: years ago I built an MRP for a supplier of the main automakers (customer schedules, purchasing, imports, stock and production orders) on an on-premise ERP. This project asks how I would build the data side of it today.

**All data is simulated.** No real company data is used, not even anonymized.

## Stack

Python 3.12 · PySpark · Databricks (Free Edition) · Delta Lake · dbt · Databricks Asset Bundles · GitHub Actions

## Design

- [docs/architecture.md](docs/architecture.md): business problem, data flow, gold model, KPIs and key decisions.
- [docs/data-dictionary.md](docs/data-dictionary.md): every raw ERP column, its clean name and the planted data problems.

## The data generator

A small Python package (no dependencies) simulates the plant day by day: customers send delivery schedules, production follows the firm demand and the bill of materials, shipments go out, and a simple MRP rule places purchase orders with domestic and importing suppliers, some of which deliver late. Then it plants data problems on purpose (duplicates, malformed codes, impossible dates, unit variants, bad quantities, decimal commas, orphan references) and writes one CSV per extract and business day, plus a manifest that counts every planted problem.

```bash
uv sync
uv run python -m supply_chain_generator --days 60 --out data/landing
```

```
44 business days written to data/landing
  customer_schedules      18539 rows
  inventory_movements      2275 rows
  shipments                 905 rows
  ...
planted problems: bad_quantity=89, code_format=84, decimal_comma=74, duplicate=99, ...
```

The same seed always produces the same files, and adding days never changes the files of earlier days, which is what incremental ingestion needs. In a clean 90-day run (seed 42), customer service stays around 99% until an imported component arrives late in mid-March and service drops to 60-75% for two weeks: exactly the kind of event the KPIs have to show.

The generator tests check reproducibility, file layout, referential integrity of the clean data, that stock never goes negative, and that the manifest matches what was actually planted.

## Bronze: incremental ingestion on Databricks

Everything in the workspace is defined as code in a Databricks Asset Bundle ([databricks.yml](databricks.yml) and [resources/](resources/)): one schema per layer (`sc_landing`, `sc_bronze`, `sc_silver`, `sc_gold`), the landing and checkpoint volumes, and the `supply_chain_pipeline` job.

[pipelines/bronze_ingest.py](pipelines/bronze_ingest.py) runs one Auto Loader stream per extract with `trigger(availableNow=True)`: each run loads only the files that arrived since the last run, then stops. Bronze keeps the data exactly as delivered (all text, padded codes, wrong dates included) and adds lineage columns: `_source_file`, `_file_date` and `_ingested_at`.

Databricks Free Edition cannot register external cloud storage, so the landing zone is a Unity Catalog volume. [scripts/upload_landing.py](scripts/upload_landing.py) uploads the generated files up to a given date and skips files already there, which simulates files arriving day by day.

Proof of incremental, idempotent loading (first run on 4 weeks of files, then 4 more weeks, then a run with nothing new):

| Extract | Run 1 | Run 2 | Run 3 | Total | Expected (manifests) |
|---|---:|---:|---:|---:|---:|
| customer_schedules | +8,429 | +8,421 | +0 | 16,850 | 16,850 |
| inventory_movements | +1,036 | +1,031 | +0 | 2,067 | 2,067 |
| shipments | +399 | +422 | +0 | 821 | 821 |
| purchase_orders | +24 | +48 | +0 | 72 | 72 |
| goods_receipts | +15 | +21 | +0 | 36 | 36 |

All nine extracts matched the generator manifests exactly.

```bash
databricks bundle deploy -p <profile>
uv run python scripts/upload_landing.py --until 2026-01-30 --profile <profile>
databricks bundle run supply_chain_pipeline -p <profile>
```

## Silver: cleaning, quarantine and a data quality gate

[pipelines/silver_transform.py](pipelines/silver_transform.py) turns each bronze table into a clean, typed table with English column names ([pipelines/silver_spec.py](pipelines/silver_spec.py) holds the mapping). The rules live in [pipelines/silver_rules.py](pipelines/silver_rules.py) as pure functions, tested on local Spark:

| Problem | Action |
|---|---|
| Exact duplicate in the same file | removed |
| Material code in the wrong format | fixed (trim + uppercase) |
| Unit variant (`pcs`, `kg`, `LT`, grams) | fixed (`PC` / `KG` / `L`, grams converted to KG) |
| Decimal comma | fixed |
| Impossible date | quarantined |
| Negative quantity, or zero where zero makes no sense | quarantined |
| Material code that is not in the material master | quarantined |

Quarantined rows are not dropped: they go to `sc_silver.quarantine` with the reason and the raw record, as they would need to be fixed at the source. Master data keeps the latest valid version of each record.

**Data quality gate.** Silver counts every problem it detects and compares the counts with the generator manifests in `sc_silver.dq_reconciliation`. If any count differs, the job fails. Result of the run on 8 weeks of files (24,000+ rows, 63 checks):

| Problem | Planted | Detected | Action |
|---|---:|---:|---|
| duplicate | 88 | 88 | removed |
| bad_quantity | 82 | 82 | quarantined |
| invalid_date | 81 | 81 | quarantined |
| code_format | 78 | 78 | fixed |
| decimal_comma | 70 | 70 | fixed |
| orphan_reference | 68 | 68 | quarantined |
| unit_variant | 4 | 4 | fixed |

Silver is a full refresh (overwrite) on every run: at this volume it takes seconds and makes re-runs always safe. An incremental `MERGE` is a possible next step.

## Tests

```bash
uv run pytest
```

31 tests: the generator (reproducibility, integrity of clean data, manifest accuracy) and the silver rules on local Spark, including an end-to-end check that every problem planted in a generated dataset is detected. Local Spark needs Java 17 or 21 (`brew install openjdk@17` on macOS; `tests/conftest.py` picks it up).

## Roadmap

- [x] Data generator with planted data problems
- [x] Bronze: incremental ingestion
- [x] Silver: cleaning, deduplication, quarantine, data quality gate
- [ ] Gold: dbt star schema, KPIs and tests
- [ ] Databricks Job deployed as code
- [ ] CI with GitHub Actions
- [ ] Dashboard
- [ ] How to run it yourself

## Author

Esteferson Sampaio · [LinkedIn](https://www.linkedin.com/in/estefersonsampaio/)
