"""Command line: python -m supply_chain_generator --days 60 --out data/landing"""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path

from supply_chain_generator.config import GeneratorConfig
from supply_chain_generator.writer import generate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate simulated ERP extracts.")
    parser.add_argument("--out", type=Path, default=Path("data/landing"))
    parser.add_argument("--days", type=int, default=60, help="calendar days to simulate")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 1, 5))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dirty-rate", type=float, default=0.02)
    args = parser.parse_args(argv)

    config = GeneratorConfig(
        seed=args.seed, start_date=args.start_date, days=args.days, dirty_rate=args.dirty_rate
    )
    manifests = generate(config, args.out)

    rows: Counter = Counter()
    planted: Counter = Counter()
    for manifest in manifests:
        for name, info in manifest["extracts"].items():
            rows[name] += info["rows_written"]
            planted.update(info["planted"])

    print(f"{len(manifests)} business days written to {args.out}")
    for name, count in rows.items():
        print(f"  {name:<20} {count:>8} rows")
    print(
        "planted problems: " + (", ".join(f"{k}={v}" for k, v in sorted(planted.items())) or "none")
    )


if __name__ == "__main__":
    main()
