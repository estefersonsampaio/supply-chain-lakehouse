"""Silver cleaning rules, as pure functions over Spark DataFrames.

For every bronze row the rules produce clean, typed columns and one flag per kind of
problem. What happens to each problem:

    duplicate         removed (exact copy of a row in the same file)
    code_format       fixed   (trim + uppercase)
    unit_variant      fixed   (PC / KG / L; grams converted to KG)
    decimal_comma     fixed   (12,5 -> 12.5)
    invalid_date      quarantined
    bad_quantity      quarantined
    orphan_reference  quarantined (material code not in the material master)

Every flag is counted, so the counts can be reconciled with what the generator planted.
"""

from dataclasses import dataclass

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F
from silver_spec import SilverSpec

MATERIAL_CODE_WIDTH = 15
STANDARD_UNITS = ("PC", "KG", "L")
# raw unit (uppercased) -> (standard unit, factor applied to quantities)
UNIT_MAP = {
    "PC": ("PC", 1.0),
    "UN": ("PC", 1.0),
    "PCS": ("PC", 1.0),
    "KG": ("KG", 1.0),
    "G": ("KG", 0.001),
    "L": ("L", 1.0),
    "LT": ("L", 1.0),
}
FIXED = ("code_format", "unit_variant", "decimal_comma")
QUARANTINED = ("invalid_date", "bad_quantity", "orphan_reference")  # order = priority
ALL_FLAGS = FIXED + QUARANTINED
LINEAGE = ("_source_file", "_file_date")


@dataclass
class SilverOutput:
    clean: DataFrame
    quarantine: DataFrame
    duplicates_removed: int
    flags: dict[str, int]
    rows_in: int


def remove_duplicates(df: DataFrame, spec: SilverSpec) -> tuple[DataFrame, int]:
    """Drop exact copies of a row within the same file."""
    rows_in = df.count()
    deduped = df.dropDuplicates([*spec.raw_columns, "_source_file"])
    return deduped, rows_in - deduped.count()


def _q(name: str) -> str:
    return f"`{name}`"


def clean_code(raw: str) -> Column:
    return F.upper(F.trim(F.col(raw)))


def code_format_problem(raw: str) -> Column:
    expected = F.rpad(F.upper(F.trim(F.col(raw))), MATERIAL_CODE_WIDTH, " ")
    return F.col(raw).isNull() | (F.col(raw) != expected)


def parse_date(raw: str) -> Column:
    return F.when(
        F.col(raw).rlike(r"^[0-9]{8}$"),
        F.expr(f"try_to_timestamp({_q(raw)}, 'yyyyMMdd')"),
    ).cast("date")


def parse_qty(raw: str) -> Column:
    return F.expr(f"try_cast(regexp_replace(trim({_q(raw)}), ',', '.') as decimal(18,3))")


def unit_and_factor(raw: str) -> tuple[Column, Column]:
    upper = F.upper(F.trim(F.col(raw)))
    unit = F.lit(None).cast("string")
    factor = F.lit(None).cast("double")
    for source, (target, mult) in UNIT_MAP.items():
        unit = F.when(upper == source, F.lit(target)).otherwise(unit)
        factor = F.when(upper == source, F.lit(mult)).otherwise(factor)
    return unit, factor


def apply_rules(df: DataFrame, spec: SilverSpec, valid_materials: DataFrame | None) -> DataFrame:
    """Add clean columns (spec names) and _flag_* columns. Raw columns are kept."""
    out = df
    flags: dict[str, Column] = {name: F.lit(False) for name in ALL_FLAGS}

    units = spec.of_kind("unit")
    factor = F.lit(1.0)
    for col in units:
        unit, factor = unit_and_factor(col.raw)
        out = out.withColumn(col.name, unit)
        flags["unit_variant"] = flags["unit_variant"] | ~F.col(col.raw).isin(*STANDARD_UNITS)

    for col in spec.columns:
        if col.kind == "code":
            out = out.withColumn(col.name, clean_code(col.raw))
            flags["code_format"] = flags["code_format"] | code_format_problem(col.raw)
        elif col.kind in ("id", "text"):
            out = out.withColumn(col.name, F.trim(F.col(col.raw)))
        elif col.kind == "int":
            out = out.withColumn(col.name, F.expr(f"try_cast(trim({_q(col.raw)}) as int)"))
        elif col.kind == "date":
            out = out.withColumn(col.name, parse_date(col.raw))
            flags["invalid_date"] = flags["invalid_date"] | F.col(col.name).isNull()
        elif col.kind == "qty":
            value = parse_qty(col.raw)
            if units:
                value = (value * factor).cast("decimal(18,3)")
            out = out.withColumn(col.name, value)
            flags["decimal_comma"] = flags["decimal_comma"] | F.col(col.raw).contains(",")
            bad = F.col(col.name).isNull() | (F.col(col.name) < 0)
            if not spec.zero_qty_allowed:
                bad = bad | (F.col(col.name) == 0)
            flags["bad_quantity"] = flags["bad_quantity"] | bad

    for name, flag in flags.items():
        if name != "orphan_reference":
            out = out.withColumn(f"_flag_{name}", F.coalesce(flag, F.lit(True)))

    orphan = F.lit(False)
    if spec.references and valid_materials is not None:
        codes = valid_materials.select(F.col("material_code").alias("_ref_code")).distinct()
        for i, ref in enumerate(spec.references):
            alias = f"_ref_ok_{i}"
            lookup = codes.withColumn(alias, F.lit(True)).withColumnRenamed(
                "_ref_code", f"_ref_code_{i}"
            )
            out = out.join(F.broadcast(lookup), out[ref] == lookup[f"_ref_code_{i}"], "left").drop(
                f"_ref_code_{i}"
            )
            orphan = orphan | F.col(alias).isNull()
    out = out.withColumn("_flag_orphan_reference", orphan)
    out = out.drop(*[c for c in out.columns if c.startswith("_ref_ok_")])

    reason = F.lit(None).cast("string")
    for name in reversed(QUARANTINED):
        reason = F.when(F.col(f"_flag_{name}"), F.lit(name)).otherwise(reason)
    return out.withColumn("_quarantine_reason", reason)


def latest_per_key(df: DataFrame, spec: SilverSpec) -> DataFrame:
    """One row per business key: the one from the most recent file."""
    window = Window.partitionBy(*spec.key).orderBy(F.col("_file_date").desc())
    return df.withColumn("_rn", F.row_number().over(window)).filter("_rn = 1").drop("_rn")


def build_silver(
    bronze: DataFrame, spec: SilverSpec, valid_materials: DataFrame | None
) -> SilverOutput:
    rows_in = bronze.count()
    deduped, duplicates = remove_duplicates(bronze, spec)
    # no .cache(): Databricks serverless compute does not support caching APIs
    flagged = apply_rules(deduped, spec, valid_materials)

    counts_row = flagged.agg(
        *[F.sum(F.col(f"_flag_{name}").cast("int")).alias(name) for name in ALL_FLAGS]
    ).first()
    flags = {name: int(counts_row[name] or 0) for name in ALL_FLAGS}

    quarantine = flagged.filter(F.col("_quarantine_reason").isNotNull()).select(
        F.lit(spec.extract).alias("extract"),
        F.col("_quarantine_reason").alias("reason"),
        F.to_json(F.struct(*[F.col(c) for c in spec.raw_columns])).alias("raw_record"),
        *LINEAGE,
    )
    valid = flagged.filter(F.col("_quarantine_reason").isNull())
    clean = latest_per_key(valid, spec).select(*[c.name for c in spec.columns], *LINEAGE)
    return SilverOutput(clean, quarantine, duplicates, flags, rows_in)
