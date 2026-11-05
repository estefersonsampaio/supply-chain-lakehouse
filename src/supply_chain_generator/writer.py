"""Write daily extracts as CSV files plus a manifest of planted problems.

Layout:

    <out>/<extract>/<extract>_<YYYYMMDD>.csv   one file per extract and business day
    <out>/_manifest/manifest_<YYYYMMDD>.json   rows written and problems planted

Some quarantinable problems in transactions are "fixed at the source": the clean record
(same ERP record number) is re-sent at the end of a later file. The manifest counts
those rows as corrections_resent.

Files use ';' as separator, as many ERP exports do.
"""

import csv
import json
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

from supply_chain_generator.business_calendar import add_business_days, erp_date
from supply_chain_generator.config import GeneratorConfig
from supply_chain_generator.dirt import inject
from supply_chain_generator.extracts import EXTRACTS
from supply_chain_generator.simulation import Simulator

SEPARATOR = ";"


def generate(config: GeneratorConfig, out_dir: Path) -> list[dict]:
    """Run the simulation and write all files. Returns one manifest per day."""
    out_dir = Path(out_dir)
    manifests = []
    # day -> extract -> corrected records to append to that day's file
    pending: dict[date, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for day_output in Simulator(config).run():
        stamp = erp_date(day_output.day)
        manifest = {
            "date": day_output.day.isoformat(),
            "dirty_rate": config.dirty_rate,
            "extracts": {},
        }
        for name, spec in EXTRACTS.items():
            rows = day_output.rows.get(name, [])
            rng = random.Random(f"{config.seed}:{name}:{stamp}")
            result = inject(rows, spec, config.dirty_rate, rng)
            for delay, record in result.corrections:
                pending[add_business_days(day_output.day, delay)][name].append(record)
            resent = pending.get(day_output.day, {}).get(name, [])
            path = out_dir / name / f"{name}_{stamp}.csv"
            _write_csv(path, spec.columns, result.rows + resent)
            manifest["extracts"][name] = {
                "clean_rows": len(rows),
                "rows_written": len(result.rows) + len(resent),
                "corrections_resent": len(resent),
                "planted": dict(sorted(result.counts.items())),
            }
        pending.pop(day_output.day, None)
        manifest_path = out_dir / "_manifest" / f"manifest_{stamp}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifests.append(manifest)
    return manifests


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=SEPARATOR, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[col] for col in columns])
