"""Planted data problems.

Each row has a `dirty_rate` chance of receiving exactly one problem, chosen among the
ones that make sense for its extract. Every planted problem is counted, so the silver
layer can later be checked against the manifest ("we planted 37 duplicates, silver
removed 37").
"""

import random
from collections import Counter
from dataclasses import dataclass

from supply_chain_generator.extracts import MATERIAL_CODE_WIDTH, ExtractSpec, format_qty

DUPLICATE = "duplicate"
CODE_FORMAT = "code_format"
INVALID_DATE = "invalid_date"
UNIT_VARIANT = "unit_variant"
BAD_QUANTITY = "bad_quantity"
DECIMAL_COMMA = "decimal_comma"
ORPHAN_REFERENCE = "orphan_reference"

ALL_ISSUES = (
    DUPLICATE,
    CODE_FORMAT,
    INVALID_DATE,
    UNIT_VARIANT,
    BAD_QUANTITY,
    DECIMAL_COMMA,
    ORPHAN_REFERENCE,
)

UNIT_ALIASES = {"PC": ("pc", "UN", "pcs"), "KG": ("kg", "Kg"), "L": ("LT", "l")}
IMPOSSIBLE_DATES = ("00000000", "", "{year}0230", "{year}1131", "{year}0431")


@dataclass
class DirtResult:
    rows: list[dict[str, str]]
    counts: Counter


def applicable_issues(spec: ExtractSpec) -> list[str]:
    issues = [DUPLICATE]
    if spec.code_columns:
        issues.append(CODE_FORMAT)
    if spec.date_columns:
        issues.append(INVALID_DATE)
    if spec.unit_column:
        issues.append(UNIT_VARIANT)
    if spec.qty_columns:
        issues += [BAD_QUANTITY, DECIMAL_COMMA]
    if spec.reference_columns:
        issues.append(ORPHAN_REFERENCE)
    return issues


def inject(
    rows: list[dict[str, str]], spec: ExtractSpec, rate: float, rng: random.Random
) -> DirtResult:
    counts: Counter = Counter()
    if rate <= 0 or not rows:
        return DirtResult(rows=[dict(r) for r in rows], counts=counts)

    issues = applicable_issues(spec)
    out: list[dict[str, str]] = []
    for original in rows:
        row = dict(original)
        if rng.random() >= rate:
            out.append(row)
            continue
        issue = rng.choice(issues)
        counts[issue] += 1
        if issue == DUPLICATE:
            out.append(row)
            out.append(dict(row))  # the same record sent twice
            continue
        _apply(issue, row, spec, rng)
        out.append(row)
    return DirtResult(rows=out, counts=counts)


def _apply(issue: str, row: dict[str, str], spec: ExtractSpec, rng: random.Random) -> None:
    if issue == CODE_FORMAT:
        col = rng.choice(spec.code_columns)
        code = row[col].strip()
        row[col] = rng.choice(
            (code.lower().ljust(MATERIAL_CODE_WIDTH), " " + code, code, code.lower())
        )
    elif issue == INVALID_DATE:
        col = rng.choice(spec.date_columns)
        year = row[col][:4] if row[col][:4].isdigit() else "2026"
        row[col] = rng.choice(IMPOSSIBLE_DATES).format(year=year)
    elif issue == UNIT_VARIANT:
        col = spec.unit_column
        unit = row[col]
        qty_col = spec.qty_columns[0] if spec.qty_columns else None
        if unit == "KG" and qty_col and spec.name == "purchase_orders" and rng.random() < 0.5:
            # same quantity, expressed in grams
            row[col] = "G"
            row[qty_col] = format_qty(float(row[qty_col]) * 1000)
        else:
            row[col] = rng.choice(UNIT_ALIASES.get(unit, (unit.lower(),)))
    elif issue == BAD_QUANTITY:
        col = rng.choice(spec.qty_columns)
        value = row[col]
        negative = "-1" if float(value) == 0 else "-" + value.lstrip("-")
        choice = rng.choice(("0", negative))
        row[col] = negative if spec.zero_qty_allowed else choice
    elif issue == DECIMAL_COMMA:
        col = rng.choice(spec.qty_columns)
        value = row[col]
        row[col] = value.replace(".", ",") if "." in value else value + ",00"
    elif issue == ORPHAN_REFERENCE:
        col = rng.choice(spec.reference_columns)
        row[col] = f"XX{rng.randint(1000, 9999)}".ljust(MATERIAL_CODE_WIDTH)
