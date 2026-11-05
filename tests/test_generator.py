import csv
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from supply_chain_generator.config import GeneratorConfig
from supply_chain_generator.extracts import EXTRACTS
from supply_chain_generator.writer import generate

SHORT = dict(start_date=date(2026, 1, 5), days=21)


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def read_all(out: Path, extract: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted((out / extract).glob("*.csv")):
        rows += read(path)
    return rows


@pytest.fixture(scope="module")
def clean(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("clean")
    generate(GeneratorConfig(dirty_rate=0, **SHORT), out)
    return out


@pytest.fixture(scope="module")
def dirty(tmp_path_factory) -> tuple[Path, list[dict]]:
    out = tmp_path_factory.mktemp("dirty")
    manifests = generate(GeneratorConfig(dirty_rate=0.2, **SHORT), out)
    return out, manifests


def files_of(out: Path) -> dict[str, bytes]:
    return {str(p.relative_to(out)): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


# --------------------------------------------------------------- reproducibility
def test_same_seed_same_files(tmp_path):
    config = GeneratorConfig(**SHORT)
    generate(config, tmp_path / "a")
    generate(config, tmp_path / "b")
    assert files_of(tmp_path / "a") == files_of(tmp_path / "b")


def test_more_days_keeps_earlier_files_identical(tmp_path):
    """Needed for incremental ingestion: day N never changes when day N+1 is added."""
    generate(GeneratorConfig(start_date=date(2026, 1, 5), days=10), tmp_path / "short")
    generate(GeneratorConfig(start_date=date(2026, 1, 5), days=20), tmp_path / "long")
    short, long = files_of(tmp_path / "short"), files_of(tmp_path / "long")
    assert short.keys() < long.keys()
    assert all(long[name] == content for name, content in short.items())


def test_different_seed_changes_data(tmp_path):
    generate(GeneratorConfig(seed=1, **SHORT), tmp_path / "a")
    generate(GeneratorConfig(seed=2, **SHORT), tmp_path / "b")
    assert files_of(tmp_path / "a") != files_of(tmp_path / "b")


# ----------------------------------------------------------------------- layout
def test_one_file_per_extract_and_business_day(clean):
    stamps = {p.stem.split("_")[-1] for p in (clean / "materials").glob("*.csv")}
    assert len(stamps) == 15  # 21 calendar days from a Monday = 15 business days
    for stamp in stamps:
        assert datetime.strptime(stamp, "%Y%m%d").weekday() < 5
        for name in EXTRACTS:
            assert (clean / name / f"{name}_{stamp}.csv").exists()
        assert (clean / "_manifest" / f"manifest_{stamp}.json").exists()


def test_headers_match_layout(clean):
    for name, spec in EXTRACTS.items():
        first = sorted((clean / name).glob("*.csv"))[0]
        header = first.read_text(encoding="utf-8").splitlines()[0]
        assert tuple(header.split(";")) == spec.columns


# --------------------------------------------------------- clean data integrity
def test_clean_data_has_no_duplicates(clean):
    for name, spec in EXTRACTS.items():
        if spec.snapshot:
            continue
        rows = [tuple(r.values()) for r in read_all(clean, name)]
        assert len(rows) == len(set(rows)), name


def test_clean_references_exist(clean):
    materials = {r["B1_COD"] for r in read_all(clean, "materials")}
    for name, spec in EXTRACTS.items():
        for col in spec.reference_columns:
            for row in read_all(clean, name):
                assert row[col] in materials, (name, col, row[col])


def test_clean_quantities_and_dates_are_valid(clean):
    for name, spec in EXTRACTS.items():
        for row in read_all(clean, name):
            for col in spec.qty_columns:
                assert float(row[col]) >= 0, (name, row)
            for col in spec.date_columns:
                datetime.strptime(row[col], "%Y%m%d")


def test_receipts_match_purchase_orders(clean):
    orders = {(r["C7_NUM"], r["C7_ITEM"]): r for r in read_all(clean, "purchase_orders")}
    received: dict[tuple[str, str], float] = {}
    for receipt in read_all(clean, "goods_receipts"):
        key = (receipt["D1_PEDIDO"], receipt["D1_ITEMPC"])
        order = orders[key]
        assert receipt["D1_COD"] == order["C7_PRODUTO"]
        assert receipt["D1_FORNECE"] == order["C7_FORNECE"]
        assert receipt["D1_DTDIGIT"] > order["C7_EMISSAO"]
        received[key] = received.get(key, 0) + float(receipt["D1_QUANT"])
    for key, qty in received.items():
        assert qty <= float(orders[key]["C7_QUANT"]) + 1e-6


def test_stock_never_goes_negative(clean):
    """Rebuild stock from all movements: it must never go below zero."""
    events: list[tuple[str, int, str, float]] = []
    for r in read_all(clean, "inventory_movements"):
        sign = 1 if int(r["D3_TM"]) < 500 else -1
        # within a day: entries first, then exits
        events.append(
            (r["D3_EMISSAO"], 0 if sign > 0 else 2, r["D3_COD"], sign * float(r["D3_QUANT"]))
        )
    for r in read_all(clean, "goods_receipts"):
        events.append((r["D1_DTDIGIT"], 0, r["D1_COD"], float(r["D1_QUANT"])))
    for r in read_all(clean, "shipments"):
        events.append((r["D2_EMISSAO"], 1, r["D2_COD"], -float(r["D2_QUANT"])))
    stock: dict[str, float] = {}
    for _, _, code, qty in sorted(events):
        stock[code] = stock.get(code, 0) + qty
        assert stock[code] > -1e-6, code


def test_schedules_have_firm_and_forecast(clean):
    types = {r["ZA1_TIPO"] for r in read_all(clean, "customer_schedules")}
    assert types == {"F", "P"}


# ---------------------------------------------------------------- planted dirt
def test_clean_run_plants_nothing(tmp_path):
    manifests = generate(GeneratorConfig(dirty_rate=0, **SHORT), tmp_path)
    assert all(not info["planted"] for m in manifests for info in m["extracts"].values())


def test_manifest_counts_match_files(dirty):
    out, manifests = dirty
    for manifest in manifests:
        stamp = manifest["date"].replace("-", "")
        for name, info in manifest["extracts"].items():
            rows = read(out / name / f"{name}_{stamp}.csv")
            assert len(rows) == info["rows_written"]
            assert info["rows_written"] == (
                info["clean_rows"]
                + info["planted"].get("duplicate", 0)
                + info["corrections_resent"]
            )


def test_duplicates_are_exact_copies(dirty):
    out, manifests = dirty
    for name, spec in EXTRACTS.items():
        if spec.snapshot:
            continue
        planted = sum(m["extracts"][name]["planted"].get("duplicate", 0) for m in manifests)
        rows = [tuple(r.values()) for r in read_all(out, name)]
        assert len(rows) - len(set(rows)) == planted, name


def test_all_problem_types_are_planted(dirty):
    _, manifests = dirty
    planted = set()
    for manifest in manifests:
        for info in manifest["extracts"].values():
            planted |= set(info["planted"])
    assert planted == {
        "duplicate",
        "code_format",
        "invalid_date",
        "unit_variant",
        "bad_quantity",
        "decimal_comma",
        "orphan_reference",
    }


def test_manifest_is_valid_json(dirty):
    out, _ = dirty
    for path in (out / "_manifest").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) == {"date", "dirty_rate", "extracts"}


def test_invalid_config_is_rejected():
    with pytest.raises(ValueError):
        GeneratorConfig(days=0)
    with pytest.raises(ValueError):
        GeneratorConfig(dirty_rate=1.5)


def test_bad_quantity_is_negative_where_zero_is_valid():
    """A customer can schedule zero, so a planted bad quantity there must be negative."""
    import random

    from supply_chain_generator.dirt import inject

    spec = EXTRACTS["customer_schedules"]
    rows = [
        {c: "" for c in spec.columns} | {"ZA1_QUANT": q, "ZA1_DTEMIS": "20260105"}
        for q in ("0", "15", "120.5") * 200
    ]
    for row in rows:
        row["ZA1_DTENT"] = "20260106"
        row["ZA1_PROD"] = "PA0001".ljust(15)
    result = inject(rows, spec, rate=1.0, rng=random.Random(7))
    assert result.counts["bad_quantity"] > 0
    changed = [r["ZA1_QUANT"] for r in result.rows if "," not in r["ZA1_QUANT"]]
    originals = {"0", "15", "120.5"}
    planted = [q for q in changed if q not in originals]
    assert len(planted) == result.counts["bad_quantity"]
    assert all(float(q) < 0 for q in planted)


def test_record_numbers_are_unique_in_clean_transactions(clean):
    for name, spec in EXTRACTS.items():
        if spec.snapshot:
            continue
        numbers = [r["R_E_C_N_O_"] for r in read_all(clean, name)]
        assert len(numbers) == len(set(numbers)), name


def test_corrections_are_resent_later_with_the_same_record_number(dirty):
    """A quarantinable problem fixed at the source comes back clean in a later file."""
    out, manifests = dirty
    resent_total = sum(m["extracts"][n]["corrections_resent"] for m in manifests for n in EXTRACTS)
    assert resent_total > 0
    for name, spec in EXTRACTS.items():
        if spec.snapshot:
            assert all(m["extracts"][name]["corrections_resent"] == 0 for m in manifests)
            continue
        seen: dict[str, list[tuple[str, dict]]] = {}
        for path in sorted((out / name).glob("*.csv")):
            stamp = path.stem.rsplit("_", 1)[-1]
            for row in read(path):
                seen.setdefault(row["R_E_C_N_O_"], []).append((stamp, row))
        repeated = {k: v for k, v in seen.items() if len({s for s, _ in v}) > 1}
        expected = sum(m["extracts"][name]["corrections_resent"] for m in manifests)
        assert len(repeated) == expected, name
        for versions in repeated.values():
            (first_day, first), (last_day, last) = versions[0], versions[-1]
            assert last_day > first_day and last != first
