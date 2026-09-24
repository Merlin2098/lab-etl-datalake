"""Glue ETL job: Bronze -> Silver -> Gold for the orders medallion data lake.

Reads raw order CSVs from Bronze, cleans and deduplicates them into Silver,
then aggregates Silver into a Gold dataset partitioned by year/month/day.

Paths are passed as job parameters (BRONZE_PATH, SILVER_PATH, GOLD_PATH),
not hardcoded, so the same script works across environments.
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
        .groupBy("city", "year", "month", "day")
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

    bronze_df = (
        spark.read.option("header", "true")
        .option("inferSchema", "true")
        .csv(args["BRONZE_PATH"])
    )

    silver_df = build_silver(bronze_df)
    silver_df.write.mode("overwrite").parquet(args["SILVER_PATH"])

    gold_df = build_gold(silver_df)
    (
        gold_df.write.mode("overwrite")
        .partitionBy("year", "month", "day")
        .parquet(args["GOLD_PATH"])
    )

    job.commit()


if __name__ == "__main__":
    main()
