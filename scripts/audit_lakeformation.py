"""Audit (and optionally revoke) Lake Formation grants left in the account.

This project no longer uses Lake Formation (no aws_lakeformation_*
resources in infra/), but a database created while Lake Formation
resources previously existed can end up with explicit grants that
survive after the Terraform code is removed — Lake Formation state lives
in the account, not in Terraform state. This script lists every
database-level and table-level grant Lake Formation still knows about, so
you can get the account back to a clean, IAM-only state.

By default it is read-only. Pass --revoke to actually remove the
database/table grants it found (never touches account-level settings like
DataLakeAdmins, and never deregisters S3 locations — those are shown for
context only). It always prints the exact plan and asks for confirmation
before revoking anything.

IMPORTANT: --revoke never touches grants for the IAM_ALLOWED_PRINCIPALS
pseudo-principal by default. That grant is what makes the "IAM-only"
permission model actually work on a given database/table — it is not a
Lake Formation residue, it IS the mechanism that lets any IAM role with
the right IAM policy read/write it without any Lake Formation grant of
its own. Revoking it re-introduces the exact "Insufficient Lake Formation
permission(s)" error this script exists to clean up (confirmed by
experience: doing this once broke Glue Crawlers that were working fine).
Pass --include-iam-allowed-principals to revoke those too, and only if
you specifically intend to move that resource to a real Lake
Formation-governed permission model.

Usage:
    uv run python scripts/audit_lakeformation.py            # read-only audit
    uv run python scripts/audit_lakeformation.py --revoke    # audit + revoke (asks to confirm)
    uv run python scripts/audit_lakeformation.py --revoke --yes  # revoke without prompting
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import boto3
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


def get_client(service: str):
    load_dotenv(REPO_ROOT / ".env.credentials")
    return boto3.client(
        service,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        verify=False,
    )


@dataclass(frozen=True)
class Grant:
    principal: str
    permissions: list[str]
    resource: dict  # exact Resource shape for revoke_permissions
    label: str  # human-readable description for the plan/confirmation


def get_data_lake_admins(lakeformation) -> list[str]:
    settings = lakeformation.get_data_lake_settings()["DataLakeSettings"]
    return [
        a["DataLakePrincipalIdentifier"] for a in settings.get("DataLakeAdmins", [])
    ]


def print_account_settings(lakeformation) -> None:
    print("=== Account-level Lake Formation settings ===")
    settings = lakeformation.get_data_lake_settings()["DataLakeSettings"]

    admins = get_data_lake_admins(lakeformation)
    print(f"DataLakeAdmins: {admins or '(none)'}")

    for key in ("CreateDatabaseDefaultPermissions", "CreateTableDefaultPermissions"):
        value = settings.get(key, [])
        print(f"{key}: {value or '(empty)'}")


def print_registered_locations(lakeformation) -> None:
    print("\n=== Registered data lake locations (not touched by --revoke) ===")
    resources = lakeformation.list_resources().get("ResourceInfoList", [])
    if not resources:
        print("(none)")
    for resource in resources:
        print(f"  {resource.get('ResourceArn')} (role: {resource.get('RoleArn')})")


IAM_ALLOWED_PRINCIPALS = "IAM_ALLOWED_PRINCIPALS"


def collect_database_and_table_grants(
    glue, lakeformation, include_iam_allowed_principals: bool = False
) -> list[Grant]:
    grants: list[Grant] = []

    print("\n=== Databases in the Glue Data Catalog, and their LF grants ===")
    databases = glue.get_databases().get("DatabaseList", [])
    if not databases:
        print("(no databases in this catalog)")
        return grants

    for database in databases:
        name = database["Name"]
        print(f"\n[{name}] (CreateTime: {database.get('CreateTime')})")

        db_permissions = lakeformation.list_permissions(
            Resource={"Database": {"Name": name}}
        ).get("PrincipalResourcePermissions", [])
        if not db_permissions:
            print("  Database-level grants: (none)")
        for entry in db_permissions:
            principal = entry["Principal"]["DataLakePrincipalIdentifier"]
            permissions = entry.get("Permissions", [])
            is_iam_allowed = principal == IAM_ALLOWED_PRINCIPALS
            suffix = " (kept: makes IAM-only access work)" if is_iam_allowed else ""
            print(f"  Database-level grant -> {principal}: {permissions}{suffix}")
            if is_iam_allowed and not include_iam_allowed_principals:
                continue
            grants.append(
                Grant(
                    principal=principal,
                    permissions=permissions,
                    resource={"Database": {"Name": name}},
                    label=f"database '{name}'",
                )
            )

        tables = glue.get_tables(DatabaseName=name).get("TableList", [])
        for table in tables:
            table_permissions = lakeformation.list_permissions(
                Resource={"Table": {"DatabaseName": name, "Name": table["Name"]}}
            ).get("PrincipalResourcePermissions", [])
            for entry in table_permissions:
                principal = entry["Principal"]["DataLakePrincipalIdentifier"]
                permissions = entry.get("Permissions", [])
                is_iam_allowed = principal == IAM_ALLOWED_PRINCIPALS
                suffix = " (kept: makes IAM-only access work)" if is_iam_allowed else ""
                print(
                    f"  Table '{table['Name']}' grant -> {principal}: "
                    f"{permissions}{suffix}"
                )
                if is_iam_allowed and not include_iam_allowed_principals:
                    continue
                grants.append(
                    Grant(
                        principal=principal,
                        permissions=permissions,
                        resource={
                            "Table": {"DatabaseName": name, "Name": table["Name"]}
                        },
                        label=f"table '{name}.{table['Name']}'",
                    )
                )

    return grants


def remove_data_lake_admins(
    lakeformation, admins: list[str], skip_confirm: bool
) -> None:
    if not admins:
        print("\nNo Data Lake Administrators configured — nothing to remove.")
        return

    print(f"\n=== Plan: remove {len(admins)} Data Lake Administrator(s) ===")
    for admin in admins:
        print(f"  REMOVE admin: {admin}")
    print(
        "  Note: as long as ANY Data Lake Administrator exists, Glue keeps "
        "evaluating permissions through Lake Formation instead of falling "
        "back to plain IAM — this is why the crawler kept failing even "
        "after every explicit grant was revoked."
    )

    if not skip_confirm:
        answer = (
            input("\nProceed with removing the admins above? [y/N] ").strip().lower()
        )
        if answer != "y":
            print("Aborted — admins were not removed.")
            return

    # put_data_lake_settings replaces the whole settings object, so the
    # existing create-default-permissions must be re-sent explicitly or
    # they would silently reset.
    current = lakeformation.get_data_lake_settings()["DataLakeSettings"]
    lakeformation.put_data_lake_settings(
        DataLakeSettings={
            **current,
            "DataLakeAdmins": [],
        }
    )
    print("Removed all Data Lake Administrators.")


def revoke_grants(lakeformation, grants: list[Grant], skip_confirm: bool) -> None:
    if not grants:
        print("\nNo database/table grants found — nothing to revoke.")
        return

    print(f"\n=== Plan: revoke {len(grants)} grant(s) ===")
    for grant in grants:
        print(f"  REVOKE {grant.permissions} on {grant.label} from {grant.principal}")

    if not skip_confirm:
        answer = (
            input("\nProceed with revoking the grants above? [y/N] ").strip().lower()
        )
        if answer != "y":
            print("Aborted — nothing was revoked.")
            return

    for grant in grants:
        lakeformation.revoke_permissions(
            Principal={"DataLakePrincipalIdentifier": grant.principal},
            Resource=grant.resource,
            Permissions=grant.permissions,
        )
        print(f"Revoked {grant.permissions} on {grant.label} from {grant.principal}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit (and optionally revoke) Lake Formation grants."
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke every database/table grant found (after showing the "
        "plan and asking to confirm, unless --yes is also set).",
    )
    parser.add_argument(
        "--remove-admins",
        action="store_true",
        help="Also remove every Data Lake Administrator from the account "
        "(account-level, broader impact — separate flag on purpose). Do "
        "this if crawlers still fail with a Lake Formation permission "
        "error after --revoke found and removed all explicit grants: as "
        "long as any admin exists, Glue keeps routing permission checks "
        "through Lake Formation instead of falling back to plain IAM.",
    )
    parser.add_argument(
        "--include-iam-allowed-principals",
        action="store_true",
        help="Also include IAM_ALLOWED_PRINCIPALS grants in --revoke. "
        "DANGEROUS on a database/table you want to keep IAM-only: that "
        "grant IS the mechanism making IAM-only access work, not a "
        "residue. Revoking it reproduces the 'Insufficient Lake Formation "
        "permission(s)' error. Only use this if you are intentionally "
        "moving a resource to Lake-Formation-governed permissions.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt when used with --revoke or --remove-admins.",
    )
    args = parser.parse_args()

    lakeformation = get_client("lakeformation")
    glue = get_client("glue")

    print_account_settings(lakeformation)
    print_registered_locations(lakeformation)
    grants = collect_database_and_table_grants(
        glue, lakeformation, args.include_iam_allowed_principals
    )

    if args.revoke:
        revoke_grants(lakeformation, grants, skip_confirm=args.yes)
    elif not args.remove_admins:
        print(
            "\nRead-only run. Re-run with --revoke to remove the "
            "database/table grants listed above."
        )

    if args.remove_admins:
        admins = get_data_lake_admins(lakeformation)
        remove_data_lake_admins(lakeformation, admins, skip_confirm=args.yes)


if __name__ == "__main__":
    main()
