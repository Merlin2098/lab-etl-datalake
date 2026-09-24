"""Run Glue Crawlers on demand and print their result, for debugging.

Triggers the Silver and/or Gold crawlers, polls until each reaches a
terminal state, and prints the full LastCrawl error message on failure
(e.g. Lake Formation permission errors) — without having to click through
the Glue console each time.

Reads crawler/database names from `terraform output`, never hardcodes
them. Requires live AWS credentials in `.env.credentials` and a completed
`terraform apply`.

Usage:
    uv run python scripts/debug_crawlers.py                # both crawlers
    uv run python scripts/debug_crawlers.py --only silver   # just Silver
    uv run python scripts/debug_crawlers.py --only gold     # just Gold
    uv run python scripts/debug_crawlers.py --tables        # also list catalog tables after
    uv run python scripts/debug_crawlers.py --inspect-only  # skip running crawlers, just inspect
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
INFRA_DIR = REPO_ROOT / "infra"

POLL_SECONDS = 10
TIMEOUT_SECONDS = 10 * 60


def get_client(service: str):
    load_dotenv(REPO_ROOT / ".env.credentials")
    return boto3.client(
        service,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        verify=False,
    )


def terraform_outputs() -> dict[str, str]:
    result = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=INFRA_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return {k: v["value"] for k, v in json.loads(result.stdout).items()}


def run_crawler(glue, name: str) -> None:
    print(f"\n=== Starting crawler: {name} ===")
    try:
        glue.start_crawler(Name=name)
    except glue.exceptions.CrawlerRunningException:
        print(f"{name} is already running, watching it instead.")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        crawler = glue.get_crawler(Name=name)["Crawler"]
        state = crawler["State"]
        last_crawl = crawler.get("LastCrawl", {})
        print(f"  state={state} last_status={last_crawl.get('Status')}")

        if state == "READY":
            status = last_crawl.get("Status")
            if status == "SUCCEEDED":
                print(f"OK: {name} SUCCEEDED.")
            else:
                print(f"FAILED: {name} finished with status={status}")
                error_message = last_crawl.get("ErrorMessage")
                if error_message:
                    print(f"ErrorMessage:\n  {error_message}")
                log_group = last_crawl.get("LogGroup")
                log_stream = last_crawl.get("LogStream")
                if log_group:
                    print(f"CloudWatch logs: {log_group} / {log_stream}")
            return

        time.sleep(POLL_SECONDS)

    raise TimeoutError(f"{name} did not reach READY within {TIMEOUT_SECONDS}s")


def list_tables(glue, database_name: str) -> None:
    print(f"\n=== Tables in {database_name} ===")
    tables = glue.get_tables(DatabaseName=database_name)["TableList"]
    if not tables:
        print("  (no tables)")
    for table in tables:
        storage = table.get("StorageDescriptor", {})
        print(f"  {table['Name']} -> {storage.get('Location')}")


def inspect_database(glue, database_name: str) -> None:
    print(f"\n=== Database: {database_name} ===")
    try:
        database = glue.get_database(Name=database_name)["Database"]
        print(f"  CreateTime: {database.get('CreateTime')}")
        print(f"  CatalogId: {database.get('CatalogId')}")
        print(f"  LocationUri: {database.get('LocationUri')}")
    except glue.exceptions.EntityNotFoundException:
        print("  Does NOT exist in the Glue Data Catalog.")


def inspect_lake_formation(database_name: str) -> None:
    print("\n=== Lake Formation account settings ===")
    lakeformation = get_client("lakeformation")
    try:
        settings = lakeformation.get_data_lake_settings()["DataLakeSettings"]
    except Exception as exc:  # noqa: BLE001 - diagnostic output, not control flow
        print(f"  Could not read data lake settings: {exc}")
        return

    admins = [
        a["DataLakePrincipalIdentifier"] for a in settings.get("DataLakeAdmins", [])
    ]
    print(f"  DataLakeAdmins: {admins or '(none)'}")
    create_db_defaults = settings.get("CreateDatabaseDefaultPermissions", [])
    create_table_defaults = settings.get("CreateTableDefaultPermissions", [])
    print(
        "  CreateDatabaseDefaultPermissions: "
        f"{create_db_defaults or '(empty -> Lake Formation-only, not IAM-only)'}"
    )
    print(
        "  CreateTableDefaultPermissions: "
        f"{create_table_defaults or '(empty -> Lake Formation-only, not IAM-only)'}"
    )
    print(
        "  Note: a non-empty list containing IAM_ALLOWED_PRINCIPALS means "
        "'Use only IAM access control' is ON for new databases/tables."
    )

    print(f"\n=== Lake Formation permissions on {database_name} ===")
    try:
        permissions = lakeformation.list_permissions(
            Resource={"Database": {"Name": database_name}}
        )["PrincipalResourcePermissions"]
    except Exception as exc:  # noqa: BLE001 - diagnostic output, not control flow
        print(f"  Could not list permissions: {exc}")
        return

    if not permissions:
        print("  (no explicit Lake Formation grants found on this database)")
    for entry in permissions:
        principal = entry["Principal"]["DataLakePrincipalIdentifier"]
        perms = entry.get("Permissions", [])
        print(f"  {principal}: {perms}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Glue Crawlers on demand and print their result."
    )
    parser.add_argument(
        "--only",
        choices=["silver", "gold"],
        help="Run only this crawler instead of both.",
    )
    parser.add_argument(
        "--tables",
        action="store_true",
        help="List the catalog tables in the database after running crawlers.",
    )
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Skip running crawlers; only print database and Lake Formation "
        "diagnostics (CreateTime, account default permissions, explicit "
        "grants on the database).",
    )
    args = parser.parse_args()

    outputs = terraform_outputs()
    glue = get_client("glue")
    database_name = outputs["glue_database_name"]

    inspect_database(glue, database_name)
    inspect_lake_formation(database_name)

    if args.inspect_only:
        return

    crawlers = {
        "silver": outputs["glue_silver_crawler_name"],
        "gold": outputs["glue_gold_crawler_name"],
    }
    targets = [args.only] if args.only else ["silver", "gold"]

    failures = []
    for target in targets:
        try:
            run_crawler(glue, crawlers[target])
        except TimeoutError as exc:
            print(f"TIMEOUT: {exc}")
            failures.append(target)

    if args.tables:
        list_tables(glue, database_name)

    if failures:
        print(f"\nCrawlers that did not finish in time: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
