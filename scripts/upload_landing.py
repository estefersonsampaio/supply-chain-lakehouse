"""Upload generated extracts to the landing volume, simulating daily arrival.

Only files up to --until are sent, and files already in the volume are skipped, so
running it again with a later date "delivers" just the new business days:

    uv run python scripts/upload_landing.py --until 2026-01-30 --profile free
    uv run python scripts/upload_landing.py --until 2026-02-27 --profile free

Requires the Databricks CLI, logged in with the given profile.
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path


def remote_files(volume: str, folder: str, profile: str) -> set[str]:
    result = subprocess.run(
        ["databricks", "fs", "ls", f"dbfs:{volume}/{folder}", "-p", profile, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # folder does not exist yet
        return set()
    return {entry["name"] for entry in json.loads(result.stdout or "[]")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=Path("data/landing"))
    parser.add_argument("--volume", default="/Volumes/workspace/sc_landing/erp_extracts")
    parser.add_argument("--until", type=date.fromisoformat, required=True)
    parser.add_argument("--profile", default="DEFAULT")
    args = parser.parse_args()

    until = args.until.strftime("%Y%m%d")
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        sent = 0
        for folder in sorted(p for p in args.source.iterdir() if p.is_dir()):
            already = remote_files(args.volume, folder.name, args.profile)
            for path in sorted(folder.glob("*")):
                stamp = path.stem.rsplit("_", 1)[-1]
                if stamp > until or path.name in already:
                    continue
                target = staging / folder.name / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                sent += 1
        if not sent:
            print("nothing new to upload")
            return
        destination = f"dbfs:{args.volume}"
        subprocess.run(
            ["databricks", "fs", "cp", "-r", str(staging), destination, "-p", args.profile],
            check=True,
            capture_output=True,
        )
        print(f"uploaded {sent} files up to {args.until} to {args.volume}")


if __name__ == "__main__":
    main()
