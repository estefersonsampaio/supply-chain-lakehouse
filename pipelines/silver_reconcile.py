"""Reconcile what silver detected with what the generator planted (pure Python)."""

import json
from pathlib import Path

ISSUES = (
    "duplicate",
    "code_format",
    "unit_variant",
    "decimal_comma",
    "invalid_date",
    "bad_quantity",
    "orphan_reference",
)
ACTION = {
    "duplicate": "removed",
    "code_format": "fixed",
    "unit_variant": "fixed",
    "decimal_comma": "fixed",
    "invalid_date": "quarantined",
    "bad_quantity": "quarantined",
    "orphan_reference": "quarantined",
}


def planted_from_manifests(manifest_dir: str | Path, dates: set[str]) -> dict[tuple[str, str], int]:
    """Sum planted problems per (extract, issue) for the given YYYYMMDD dates."""
    totals: dict[tuple[str, str], int] = {}
    for path in sorted(Path(manifest_dir).glob("manifest_*.json")):
        stamp = path.stem.rsplit("_", 1)[-1]
        if stamp not in dates:
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for extract, info in manifest["extracts"].items():
            for issue, count in info["planted"].items():
                totals[(extract, issue)] = totals.get((extract, issue), 0) + count
    return totals


def reconcile(
    detected: dict[str, dict[str, int]], planted: dict[tuple[str, str], int]
) -> list[dict]:
    """One row per extract and issue: planted, detected, action and whether they match."""
    rows = []
    for extract, counts in detected.items():
        for issue in ISSUES:
            p = planted.get((extract, issue), 0)
            d = counts.get(issue, 0)
            rows.append(
                {
                    "extract": extract,
                    "issue": issue,
                    "action": ACTION[issue],
                    "planted": p,
                    "detected": d,
                    "matches": p == d,
                }
            )
    return rows
