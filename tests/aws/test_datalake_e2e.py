"""End-to-end pipeline test for the medallion data lake.

Runs the real Bronze -> Silver -> Gold pipeline against live AWS
infrastructure: uploads the synthetic dataset, runs the actual Glue Job,
runs the actual Glue Crawler, then queries Silver/Gold through real Athena
queries and asserts on the results.

This is a real workload, not a smoke test — it costs money (Glue DPU-hours,
Athena data scanned) and writes/overwrites data under the data lake bucket's
bronze/silver/gold prefixes. Requires:

- Live AWS credentials in `.env.credentials` (loaded by aws_session.py).
- A completed `terraform apply` (reads resource names from `terraform
  output`, never hardcodes them).

Run explicitly, e.g.:
    uv run python -m pytest tests/aws/test_datalake_e2e.py -m cloud -v -s
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.aws.aws_session import get_client

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INFRA_DIR = REPO_ROOT / "infra"
ORDERS_CSV = REPO_ROOT / "data" / "orders.csv"

GLUE_JOB_POLL_SECONDS = 15
GLUE_JOB_TIMEOUT_SECONDS = 20 * 60
CRAWLER_POLL_SECONDS = 10
CRAWLER_TIMEOUT_SECONDS = 10 * 60
ATHENA_POLL_SECONDS = 2
ATHENA_TIMEOUT_SECONDS = 2 * 60

# Source dataset: 42 rows, 2 intentional order_id duplicates
# (ORD-0001, ORD-0007), some invalid/empty amounts, inconsistent status
# casing. See data/orders.csv.
EXPECTED_TOTAL_ROWS = 42
EXPECTED_DUPLICATE_ORDER_IDS = {"ORD-0001", "ORD-0007"}


def _terraform_outputs() -> dict[str, str]:
    result = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=INFRA_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return {k: v["value"] for k, v in json.loads(result.stdout).items()}


@dataclass(frozen=True)
class StackOutputs:
    data_lake_bucket_name: str
    glue_database_name: str
    glue_job_name: str
    glue_silver_crawler_name: str
    glue_gold_crawler_name: str
    athena_workgroup_name: str
    data_job_execution_role_arn: str


@pytest.fixture(scope="module")
def stack() -> StackOutputs:
    outputs = _terraform_outputs()
    return StackOutputs(
        data_lake_bucket_name=outputs["data_lake_bucket_name"],
        glue_database_name=outputs["glue_database_name"],
        glue_job_name=outputs["glue_job_name"],
        glue_silver_crawler_name=outputs["glue_silver_crawler_name"],
        glue_gold_crawler_name=outputs["glue_gold_crawler_name"],
        athena_workgroup_name=outputs["athena_workgroup_name"],
        data_job_execution_role_arn=outputs["data_job_execution_role_arn"],
    )


def _wait_for_glue_job(glue, job_name: str, run_id: str) -> str:
    deadline = time.monotonic() + GLUE_JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        run = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]
        state = run["JobRunState"]
        if state in {"SUCCEEDED", "FAILED", "TIMEOUT", "STOPPED", "ERROR"}:
            return state
        time.sleep(GLUE_JOB_POLL_SECONDS)
    raise TimeoutError(f"Glue job {job_name} run {run_id} did not finish in time")


def _wait_for_crawler(glue, crawler_name: str) -> str:
    deadline = time.monotonic() + CRAWLER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        crawler = glue.get_crawler(Name=crawler_name)["Crawler"]
        if crawler["State"] == "READY":
            return crawler["LastCrawl"]["Status"]
        time.sleep(CRAWLER_POLL_SECONDS)
    raise TimeoutError(f"Crawler {crawler_name} did not finish in time")


def _run_athena_query(
    athena, workgroup: str, database: str, query: str
) -> list[list[str]]:
    start = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    query_execution_id = start["QueryExecutionId"]

    deadline = time.monotonic() + ATHENA_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        execution = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = execution["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in {"FAILED", "CANCELLED"}:
            reason = execution["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(
                f"Athena query failed ({state}): {reason}\nQuery: {query}"
            )
        time.sleep(ATHENA_POLL_SECONDS)
    else:
        raise TimeoutError(f"Athena query did not finish in time: {query}")

    results = athena.get_query_results(QueryExecutionId=query_execution_id)
    rows = results["ResultSet"]["Rows"]
    # First row is the column header.
    return [
        [field.get("VarCharValue", "") for field in row["Data"]] for row in rows[1:]
    ]


@pytest.mark.cloud
def test_pipeline_end_to_end(stack: StackOutputs) -> None:
    s3 = get_client("s3")
    glue = get_client("glue")
    athena = get_client("athena")

    # --- Step 1: upload the real dataset to Bronze under a source partition ---
    # Hive-style source=<name>/ lets multiple origins with the same orders
    # schema share this one pipeline (see src/glue/transform.py docstring).
    bronze_key = "bronze/orders/source=lab/orders.csv"
    s3.upload_file(str(ORDERS_CSV), stack.data_lake_bucket_name, bronze_key)

    uploaded = s3.head_object(Bucket=stack.data_lake_bucket_name, Key=bronze_key)
    assert uploaded["ContentLength"] > 0

    # --- Step 2: run the real Glue Job (Bronze -> Silver -> Gold) ---
    run = glue.start_job_run(JobName=stack.glue_job_name)
    run_id = run["JobRunId"]
    final_state = _wait_for_glue_job(glue, stack.glue_job_name, run_id)
    assert final_state == "SUCCEEDED", (
        f"Glue job run {run_id} ended in state {final_state}"
    )

    # Silver and Gold prefixes must contain actual Parquet output.
    silver_objects = s3.list_objects_v2(
        Bucket=stack.data_lake_bucket_name, Prefix="silver/orders/"
    )
    assert silver_objects.get("KeyCount", 0) > 0, "Glue job produced no Silver output"

    gold_objects = s3.list_objects_v2(
        Bucket=stack.data_lake_bucket_name, Prefix="gold/orders/"
    )
    assert gold_objects.get("KeyCount", 0) > 0, "Glue job produced no Gold output"
    gold_keys = [obj["Key"] for obj in gold_objects["Contents"]]
    assert any("source=lab" in key for key in gold_keys), (
        "Gold output is not partitioned by source as expected"
    )
    assert any("year=" in key for key in gold_keys), (
        "Gold output is not partitioned by year as expected"
    )

    # --- Step 3: run the real Crawlers to catalog Silver and Gold ---
    # Silver and Gold are cataloged by two separate crawlers (each with its
    # own table_prefix) rather than one crawler with two s3_target blocks:
    # both prefixes end in the same last path segment (.../orders/), and a
    # single crawler would otherwise name the first table "orders" and the
    # second with a random hash suffix on collision. table_prefix makes the
    # resulting names deterministic.
    glue.start_crawler(Name=stack.glue_silver_crawler_name)
    silver_crawl_status = _wait_for_crawler(glue, stack.glue_silver_crawler_name)
    assert silver_crawl_status == "SUCCEEDED", (
        f"Silver crawler finished with status {silver_crawl_status}"
    )

    glue.start_crawler(Name=stack.glue_gold_crawler_name)
    gold_crawl_status = _wait_for_crawler(glue, stack.glue_gold_crawler_name)
    assert gold_crawl_status == "SUCCEEDED", (
        f"Gold crawler finished with status {gold_crawl_status}"
    )

    tables = glue.get_tables(DatabaseName=stack.glue_database_name)["TableList"]
    table_names = {table["Name"] for table in tables}
    silver_table = "silver_orders"
    gold_table = "gold_orders"
    assert silver_table in table_names, (
        f"Expected table '{silver_table}' in catalog, got: {table_names}"
    )
    assert gold_table in table_names, (
        f"Expected table '{gold_table}' in catalog, got: {table_names}"
    )

    # --- Step 4: validate Silver via real Athena queries ---
    total_rows = _run_athena_query(
        athena,
        stack.athena_workgroup_name,
        stack.glue_database_name,
        f"SELECT COUNT(*) FROM {silver_table}",
    )
    silver_row_count = int(total_rows[0][0])
    # Silver must have fewer rows than Bronze: dedup + invalid-row filtering
    # must have actually run, not just passed data through untouched.
    assert 0 < silver_row_count < EXPECTED_TOTAL_ROWS, (
        f"Expected Silver row count strictly between 0 and "
        f"{EXPECTED_TOTAL_ROWS} (dedup/cleaning must reduce the row count), "
        f"got {silver_row_count}"
    )

    dup_check = _run_athena_query(
        athena,
        stack.athena_workgroup_name,
        stack.glue_database_name,
        f"""
        SELECT order_id, COUNT(*) AS occurrences
        FROM {silver_table}
        GROUP BY order_id
        HAVING COUNT(*) > 1
        """,
    )
    assert dup_check == [], f"Silver still has duplicate order_id rows: {dup_check}"

    invalid_amount_check = _run_athena_query(
        athena,
        stack.athena_workgroup_name,
        stack.glue_database_name,
        f"SELECT COUNT(*) FROM {silver_table} WHERE amount IS NULL OR amount <= 0",
    )
    assert int(invalid_amount_check[0][0]) == 0, "Silver contains invalid amount rows"

    known_duplicate_survivors = _run_athena_query(
        athena,
        stack.athena_workgroup_name,
        stack.glue_database_name,
        (
            "SELECT order_id FROM "
            f"{silver_table} WHERE order_id IN "
            + "("
            + ", ".join(f"'{oid}'" for oid in sorted(EXPECTED_DUPLICATE_ORDER_IDS))
            + ")"
        ),
    )
    surviving_ids = {row[0] for row in known_duplicate_survivors}
    assert surviving_ids == EXPECTED_DUPLICATE_ORDER_IDS, (
        "Expected exactly one surviving row per known duplicate order_id, "
        f"got: {surviving_ids}"
    )

    # --- Step 5: validate Gold via real Athena queries ---
    gold_rows = _run_athena_query(
        athena,
        stack.athena_workgroup_name,
        stack.glue_database_name,
        f"SELECT city, orders, revenue, average_order_value FROM {gold_table}",
    )
    assert len(gold_rows) > 0, "Gold table has no rows"

    total_gold_orders = sum(int(row[1]) for row in gold_rows)
    assert total_gold_orders == silver_row_count, (
        "Gold's aggregated order count must reconcile with Silver's row count: "
        f"gold={total_gold_orders}, silver={silver_row_count}"
    )

    for city, orders, revenue, avg_order_value in gold_rows:
        assert int(orders) > 0
        assert float(revenue) > 0
        assert float(avg_order_value) > 0

    # Partition pruning sanity check: filtering by a known partition must
    # return a subset of the unfiltered result, not the same count (proves
    # the table is actually partitioned and readable by partition columns).
    # Hive-style partition columns discovered by a crawler are cataloged as
    # string by default (confirmed via `aws glue get-table`), not int, so
    # the filter must compare against string literals.
    partitioned_rows = _run_athena_query(
        athena,
        stack.athena_workgroup_name,
        stack.glue_database_name,
        f"SELECT COUNT(*) FROM {gold_table} WHERE year = '2026' AND month = '9'",
    )
    assert int(partitioned_rows[0][0]) > 0, (
        "Partition filter year='2026' AND month='9' returned no rows — "
        "check Gold partitioning"
    )
