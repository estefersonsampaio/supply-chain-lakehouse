import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

# PySpark 4.0 needs Java 17 or 21. On macOS with Homebrew, use openjdk@17 if no
# JAVA_HOME is set (the system Java may be too new).
_BREW_JDK17 = Path("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
if "JAVA_HOME" not in os.environ and _BREW_JDK17.exists():
    os.environ["JAVA_HOME"] = str(_BREW_JDK17)


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.sql.ansi.enabled", "true")  # same as Databricks serverless
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
