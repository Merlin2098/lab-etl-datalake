"""Glue ETL job: Bronze -> Silver -> Gold for the orders medallion data lake.

Reads raw order CSVs from Bronze, cleans and deduplicates them into Silver,
then aggregates Silver into a Gold dataset partitioned by source/year/month/day.

Paths are passed as job parameters (BRONZE_PATH, SILVER_PATH, GOLD_PATH),
not hardcoded, so the same script works across environments.

Multiple sources with the same orders schema (e.g. different stores or
channels) are supported via a Hive-style `source=<name>/` partition under
Bronze — not a separate Glue Job per source. Uploading to
bronze/orders/source=store_a/orders.csv and
bronze/orders/source=store_b/orders.csv makes Spark pick up `source` as a
regular column when BRONZE_PATH is read with basePath set to the parent
prefix; it is preserved through Silver and used as a Gold partition
column. A dataset with a different schema (not just a different source of
the same orders shape) needs its own script/Job, not a partition.
"""

from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.window import Window

REQUIRED_ARGS = ["JOB_NAME", "BRONZE_PATH", "SILVER_PATH", "GOLD_PATH"]


def build_silver(bronze_df: DataFrame) -> DataFrame:
    cleaned = (
        bronze_df.withColumn("order_id", F.trim(F.col("order_id")))
        .withColumn("customer_id", F.trim(F.col("customer_id")))
        .withColumn("order_date", F.to_date(F.col("order_date")))
        .withColumn("status", F.upper(F.trim(F.col("status"))))
        .withColumn("city", F.trim(F.col("city")))
        .withColumn("carrier", F.trim(F.col("carrier")))
        .withColumn("amount", F.col("amount").cast("decimal(18,2)"))
    )

    valid = cleaned.filter(
        F.col("order_id").isNotNull()
        & (F.col("order_id") != "")
        & F.col("amount").isNotNull()
        & (F.col("amount") > 0)
        & F.col("order_date").isNotNull()
    )

    dedup_window = F.row_number().over(
        Window.partitionBy("order_id").orderBy(F.col("order_date").desc())
    )

    return (
        valid.withColumn("_row_number", dedup_window)
        .filter(F.col("_row_number") == 1)
        .drop("_row_number")
    )


def build_gold(silver_df: DataFrame) -> DataFrame:
    return (
        silver_df.withColumn("year", F.year("order_date"))
        .withColumn("month", F.month("order_date"))
        .withColumn("day", F.dayofmonth("order_date"))
        .groupBy("source", "city", "year", "month", "day")
        .agg(
            F.count("order_id").alias("orders"),
            F.sum("amount").alias("revenue"),
            F.avg("amount").alias("average_order_value"),
        )
    )


def main() -> None:
    args = getResolvedOptions(sys.argv, REQUIRED_ARGS)

    spark_context = SparkContext()
    glue_context = GlueContext(spark_context)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    # basePath tells Spark where the Hive-style partition columns start,
    # so a layout like BRONZE_PATH/source=store_a/orders.csv yields a
    # `source` column instead of being read as a literal path segment.
    bronze_df = (
        spark.read.option("header", "true")
        .option("inferSchema", "true")
        .option("basePath", args["BRONZE_PATH"])
        .csv(args["BRONZE_PATH"])
    )
    if "source" not in bronze_df.columns:
        bronze_df = bronze_df.withColumn("source", F.lit("default"))
    else:
        # A stray file directly under BRONZE_PATH (no source=.../ segment)
        # mixed in with partitioned files yields a null source for that
        # file's rows rather than a read error. Coalesce nulls to
        # "default" so partitionBy("source") always produces a concrete
        # folder instead of silently dropping rows into
        # __HIVE_DEFAULT_PARTITION__.
        bronze_df = bronze_df.withColumn(
            "source", F.coalesce(F.col("source"), F.lit("default"))
        )

    silver_df = build_silver(bronze_df)
    (
        silver_df.write.mode("overwrite")
        .partitionBy("source")
        .parquet(args["SILVER_PATH"])
    )

    gold_df = build_gold(silver_df)
    (
        gold_df.write.mode("overwrite")
        .partitionBy("source", "year", "month", "day")
        .parquet(args["GOLD_PATH"])
    )

    job.commit()


if __name__ == "__main__":
    main()
