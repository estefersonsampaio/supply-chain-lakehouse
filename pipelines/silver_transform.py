"""Silver: bronze -> clean, typed tables + quarantine + data quality reconciliation.

Full refresh on every run (overwrite), so re-running is always safe. At this data volume
recomputing everything takes seconds; an incremental MERGE is a possible next step.

Tables written to the silver schema:

    <one per extract>    clean data with English column names and real types
    quarantine           rows that could not be fixed, with the reason and the raw record
    dq_summary           rows in, duplicates removed, rows quarantined, rows out
    dq_reconciliation    problems detected vs problems planted by the generator

If detected and planted do not match for any extract and problem, the task fails after
writing the tables: a data quality gate.
"""

import argparse

from pyspark.sql import DataFrame, SparkSession
from silver_reconcile import planted_from_manifests, reconcile
from silver_rules import build_silver
from silver_spec import SPECS


def write(df: DataFrame, table: str) -> None:
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--bronze-schema", required=True)
    parser.add_argument("--silver-schema", required=True)
    parser.add_argument("--manifests", required=True, help="folder with manifest_*.json")
    args = parser.parse_args()

    spark = SparkSession.builder.getOrCreate()
    bronze = f"{args.catalog}.{args.bronze_schema}"
    silver = f"{args.catalog}.{args.silver_schema}"

    detected: dict[str, dict[str, int]] = {}
    summary = []
    quarantines: list[DataFrame] = []
    valid_materials = None
    for spec in SPECS:  # materials comes first: the others are checked against it
        out = build_silver(spark.table(f"{bronze}.{spec.extract}"), spec, valid_materials)
        write(out.clean, f"{silver}.{spec.extract}")
        if spec.extract == "materials":
            valid_materials = spark.table(f"{silver}.materials")
        quarantines.append(out.quarantine)
        quarantined = out.quarantine.count()
        rows_out = spark.table(f"{silver}.{spec.extract}").count()
        detected[spec.extract] = {"duplicate": out.duplicates_removed, **out.flags}
        summary.append((spec.extract, out.rows_in, out.duplicates_removed, quarantined, rows_out))
        print(
            f"{spec.extract:<20} in={out.rows_in:>7} dup={out.duplicates_removed:>5} "
            f"quarantine={quarantined:>5} out={rows_out:>7}"
        )

    all_quarantine = quarantines[0]
    for df in quarantines[1:]:
        all_quarantine = all_quarantine.unionByName(df)
    write(all_quarantine, f"{silver}.quarantine")
    write(
        spark.createDataFrame(
            summary,
            "extract string, rows_in long, duplicates_removed long, "
            "rows_quarantined long, rows_out long",
        ),
        f"{silver}.dq_summary",
    )

    dates = {
        row[0].strftime("%Y%m%d")
        for row in spark.table(f"{bronze}.materials").select("_file_date").distinct().collect()
    }
    rows = reconcile(detected, planted_from_manifests(args.manifests, dates))
    write(
        spark.createDataFrame(
            rows,
            "extract string, issue string, action string, planted long, detected long, "
            "matches boolean",
        ),
        f"{silver}.dq_reconciliation",
    )
    mismatches = [r for r in rows if not r["matches"]]
    for r in mismatches:
        print(
            f"MISMATCH {r['extract']}.{r['issue']}: planted={r['planted']} detected={r['detected']}"
        )
    if mismatches:
        raise RuntimeError(f"data quality gate failed: {len(mismatches)} mismatches")
    print(f"data quality gate passed: {len(rows)} checks, all detected = planted")


if __name__ == "__main__":
    main()
