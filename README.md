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

See [docs/architecture.md](docs/architecture.md) for the business problem, the data flow, the planted data problems and the key decisions.

## Roadmap

- [ ] Data generator with planted data problems
- [ ] Bronze: incremental ingestion
- [ ] Silver: cleaning, deduplication, quarantine
- [ ] Gold: dbt star schema, KPIs and tests
- [ ] Databricks Job deployed as code
- [ ] CI with GitHub Actions
- [ ] Dashboard
- [ ] How to run it yourself

## Author

Esteferson Sampaio · [LinkedIn](https://www.linkedin.com/in/estefersonsampaio/)
