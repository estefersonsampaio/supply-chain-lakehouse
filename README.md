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

Tests (`uv run pytest`) check reproducibility, file layout, referential integrity of the clean data, that stock never goes negative, and that the manifest matches what was actually planted.

## Roadmap

- [x] Data generator with planted data problems
- [ ] Bronze: incremental ingestion
- [ ] Silver: cleaning, deduplication, quarantine
- [ ] Gold: dbt star schema, KPIs and tests
- [ ] Databricks Job deployed as code
- [ ] CI with GitHub Actions
- [ ] Dashboard
- [ ] How to run it yourself

## Author

Esteferson Sampaio · [LinkedIn](https://www.linkedin.com/in/estefersonsampaio/)
