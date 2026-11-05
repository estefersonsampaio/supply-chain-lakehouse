"""Bronze: load new landing files into append-only Delta tables.

One Auto Loader stream per extract, run with trigger(availableNow=True): each run picks
up only the files that arrived since the previous run and then stops. The checkpoint
remembers which files were already loaded, so running the job twice never duplicates
data (idempotent ingestion).

Bronze keeps the data exactly as delivered: every column is text, codes keep their
padding, wrong dates stay wrong. Cleaning is silver's job. Three metadata columns are
added for lineage:

    _source_file   full path of the CSV file
    _file_date     business day of the extract (from the file name)
    _ingested_at   when this run loaded the row
"""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

EXTRACTS = (
    "materials",
    "bom",
    "suppliers",
    "customers",
    "customer_schedules",
    "purchase_orders",
    "goods_receipts",
    "inventory_movements",
    "shipments",
)


def ingest_extract(
    spark: SparkSession, extract: str, landing: str, checkpoints: str, table: str
) -> None:
    stream = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", f"{checkpoints}/{extract}/schema")
        .option("cloudFiles.inferColumnTypes", "false")  # bronze keeps everything as text
        .option("header", "true")
        .option("sep", ";")
        .option("ignoreLeadingWhiteSpace", "false")
        .option("ignoreTrailingWhiteSpace", "false")
        .option("pathGlobFilter", f"{extract}_*.csv")
        .load(f"{landing}/{extract}/")
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn(
            "_file_date",
            F.to_date(
                F.regexp_extract(F.col("_metadata.file_name"), r"_(\d{8})\.csv$", 1), "yyyyMMdd"
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )
    query = (
        stream.writeStream.option("checkpointLocation", f"{checkpoints}/{extract}/checkpoint")
        .option("mergeSchema", "true")
        .trigger(availableNow=True)
        .toTable(table)
    )
    query.awaitTermination()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--landing", required=True, help="landing volume path")
    parser.add_argument("--checkpoints", required=True, help="checkpoint volume path")
    parser.add_argument("--extracts", nargs="*", default=list(EXTRACTS))
    args = parser.parse_args()

    spark = SparkSession.builder.getOrCreate()
    for extract in args.extracts:
        table = f"{args.catalog}.{args.schema}.{extract}"
        before = spark.table(table).count() if spark.catalog.tableExists(table) else 0
        ingest_extract(spark, extract, args.landing, args.checkpoints, table)
        after = spark.table(table).count()
        print(f"{extract:<20} +{after - before:>7} rows (total {after})")


if __name__ == "__main__":
    main()
