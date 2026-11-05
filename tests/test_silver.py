"""Silver rules on local Spark.

The main test runs the generator with a high dirty rate, reads the CSV files the same
way bronze does (all text), runs silver and checks that every planted problem was
detected: the same reconciliation the Databricks job enforces.
"""

from datetime import date
from decimal import Decimal

import pytest
from pyspark.sql import functions as F
from silver_reconcile import planted_from_manifests, reconcile
from silver_rules import build_silver
from silver_spec import SPEC_BY_EXTRACT, SPECS

from supply_chain_generator.config import GeneratorConfig
from supply_chain_generator.writer import generate


def read_bronze(spark, folder, extract):
    return (
        spark.read.option("header", "true")
        .option("sep", ";")
        .option("ignoreLeadingWhiteSpace", "false")
        .option("ignoreTrailingWhiteSpace", "false")
        .csv(str(folder / extract))
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn(
            "_file_date",
            F.to_date(
                F.regexp_extract(F.col("_metadata.file_name"), r"_(\d{8})\.csv$", 1), "yyyyMMdd"
            ),
        )
    )


@pytest.fixture(scope="module")
def silver_run(spark, tmp_path_factory):
    out = tmp_path_factory.mktemp("landing")
    generate(GeneratorConfig(start_date=date(2026, 1, 5), days=21, dirty_rate=0.15), out)
    results = {}
    valid_materials = None
    for spec in SPECS:
        result = build_silver(read_bronze(spark, out, spec.extract), spec, valid_materials)
        if spec.extract == "materials":
            valid_materials = result.clean.cache()
        results[spec.extract] = result
    return out, results


def test_every_planted_problem_is_detected(silver_run):
    out, results = silver_run
    dates = {p.stem.rsplit("_", 1)[-1] for p in (out / "_manifest").glob("*.json")}
    planted = planted_from_manifests(out / "_manifest", dates)
    detected = {e: {"duplicate": r.duplicates_removed, **r.flags} for e, r in results.items()}
    rows = reconcile(detected, planted)
    mismatches = [r for r in rows if not r["matches"]]
    assert not mismatches, mismatches
    assert sum(r["planted"] for r in rows) > 100  # the test really exercised the rules


def test_quarantined_rows_are_not_in_clean_tables(silver_run):
    _, results = silver_run
    for extract, result in results.items():
        spec = SPEC_BY_EXTRACT[extract]
        q = result.quarantine.count()
        quarantined_flags = sum(
            result.flags[f] for f in ("invalid_date", "bad_quantity", "orphan_reference")
        )
        assert q == quarantined_flags, extract
        if not spec.snapshot:
            assert result.clean.count() == result.rows_in - result.duplicates_removed - q


def test_clean_tables_are_typed_and_valid(silver_run):
    _, results = silver_run
    materials = {r.material_code for r in results["materials"].clean.collect()}
    for extract, result in results.items():
        spec = SPEC_BY_EXTRACT[extract]
        rows = result.clean.collect()
        assert rows, extract
        keys = [tuple(getattr(r, k) for k in spec.key) for r in rows]
        assert len(keys) == len(set(keys)), f"duplicate keys in {extract}"
        for row in rows:
            for col in spec.columns:
                value = getattr(row, col.name)
                if col.kind == "code":
                    assert value == value.strip().upper()
                if col.kind == "date":
                    assert isinstance(value, date)
                if col.kind == "qty":
                    assert isinstance(value, Decimal) and value >= 0
                if col.kind == "unit":
                    assert value in ("PC", "KG", "L")
            for ref in spec.references:
                assert getattr(row, ref) in materials


def test_snapshot_keeps_one_row_per_material(silver_run):
    _, results = silver_run
    clean = results["materials"].clean
    assert clean.count() == clean.select("material_code").distinct().count() == 42


# ------------------------------------------------------------------ single rules
def _po_row(**overrides):
    row = {
        "C7_NUM": "000001",
        "C7_ITEM": "0001",
        "C7_FORNECE": "S00001",
        "C7_LOJA": "01",
        "C7_PRODUTO": "MP0001".ljust(15),
        "C7_UM": "KG",
        "C7_QUANT": "12.5",
        "C7_EMISSAO": "20260105",
        "C7_DATPRF": "20260115",
        "_source_file": "f.csv",
        "_file_date": date(2026, 1, 5),
    }
    row.update(overrides)
    return row


def _run_po(spark, rows):
    materials = spark.createDataFrame([("MP0001",)], "material_code string")
    df = spark.createDataFrame(rows)
    return build_silver(df, SPEC_BY_EXTRACT["purchase_orders"], materials)


def test_grams_are_converted_to_kg(spark):
    result = _run_po(spark, [_po_row(C7_UM="G", C7_QUANT="12500")])
    row = result.clean.first()
    assert (row.unit, row.quantity) == ("KG", Decimal("12.500"))
    assert result.flags["unit_variant"] == 1


def test_decimal_comma_and_code_format_are_fixed(spark):
    result = _run_po(spark, [_po_row(C7_QUANT="12,5", C7_PRODUTO=" mp0001")])
    row = result.clean.first()
    assert (row.material_code, row.quantity) == ("MP0001", Decimal("12.500"))
    assert result.flags["decimal_comma"] == 1 and result.flags["code_format"] == 1


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"C7_EMISSAO": "20261131"}, "invalid_date"),
        ({"C7_DATPRF": "00000000"}, "invalid_date"),
        ({"C7_QUANT": "-12.5"}, "bad_quantity"),
        ({"C7_QUANT": "0"}, "bad_quantity"),
        ({"C7_PRODUTO": "XX1234".ljust(15)}, "orphan_reference"),
    ],
)
def test_unfixable_rows_go_to_quarantine(spark, override, reason):
    result = _run_po(spark, [_po_row(**override)])
    assert result.clean.count() == 0
    assert [r.reason for r in result.quarantine.collect()] == [reason]


def test_exact_duplicates_in_a_file_are_removed(spark):
    result = _run_po(spark, [_po_row(), _po_row(), _po_row(_source_file="g.csv")])
    assert result.duplicates_removed == 1
