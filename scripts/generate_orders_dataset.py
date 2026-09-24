"""Generate the synthetic orders dataset consumed by the Bronze layer.

By default (including a plain "Run Python File" with no arguments, e.g.
from an IDE), writes a new, distinct data/orders-<timestamp>.csv on every
run, using the timestamp as the seed — no argument is needed to get a
different file each time you run this. Every generated file has
intentionally messy data so the Silver step of src/glue/transform.py has
real cleaning work to do: inconsistent status casing, invalid/empty
amounts, and duplicate order_id rows (same id, later order_date,
simulating a re-submitted order).

Usage:
    python scripts/generate_orders_dataset.py [--rows N] [--seed N] [--out PATH]

tests/aws/test_datalake_e2e.py depends on a fixed, deterministic
data/orders.csv (seed 42) with stable duplicate order_ids (ORD-0001,
ORD-0007). To (re)generate exactly that file, use --fixed:

    python scripts/generate_orders_dataset.py --fixed
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "orders.csv"

CITIES = ["Lima", "Arequipa", "Cusco", "Trujillo"]
CARRIERS = ["DHL", "FedEx", "UPS"]
STATUS_CASINGS = ["complete", "COMPLETE", "Complete", "pending", "cancelled"]

# Fixed base date (not "today") so the generated file is byte-for-byte
# reproducible for a given --seed, run on any day.
BASE_DATE = date(2026, 9, 1)

# Fraction of rows that get an invalid amount (empty or zero), and which
# 1-based row indices get re-submitted later in the file with a later
# order_date — mirrors the shape of the original hand-written dataset this
# script replaces (order_id 1 and 7 were the intentional duplicates).
INVALID_AMOUNT_RATE = 0.1
DUPLICATE_ROW_INDICES = [1, 7]


def generate_rows(row_count: int, seed: int) -> list[dict[str, str]]:
    random.seed(seed)

    rows: list[dict[str, str]] = []

    for i in range(1, row_count + 1):
        is_invalid_amount = random.random() < INVALID_AMOUNT_RATE
        amount = "" if is_invalid_amount and random.random() < 0.5 else "0"
        if not is_invalid_amount:
            amount = f"{random.uniform(40, 420):.2f}"

        order_date = BASE_DATE + timedelta(days=(i - 1) // 3)
        rows.append(
            {
                "order_id": f"ORD-{i:04d}",
                "customer_id": f"CUST-{100 + i}",
                "order_date": order_date.isoformat(),
                "status": random.choice(STATUS_CASINGS),
                "amount": amount,
                "city": random.choice(CITIES),
                "carrier": random.choice(CARRIERS),
            }
        )

    # Re-submit specific existing orders with a later date to produce
    # intentional order_id duplicates for the Silver dedup step to resolve.
    # Row indices (not "first N rows") so which order_ids are duplicated
    # stays stable regardless of --rows.
    last_order_date = rows[-1]["order_date"] if rows else BASE_DATE.isoformat()
    resubmit_date = date.fromisoformat(last_order_date) + timedelta(days=10)
    for index in DUPLICATE_ROW_INDICES:
        if index > len(rows):
            continue
        source = rows[index - 1]
        rows.append(
            {
                **source,
                "order_date": resubmit_date.isoformat(),
                "status": source["status"].upper(),
                "amount": f"{random.uniform(40, 420):.2f}",
            }
        )

    return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "order_id",
                "customer_id",
                "order_date",
                "status",
                "amount",
                "city",
                "carrier",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the synthetic orders.csv dataset for the Bronze layer."
    )
    parser.add_argument(
        "--rows", type=int, default=40, help="Number of base rows (before duplicates)."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible output. Defaults to the current "
        "timestamp, or to 42 when --fixed is set.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path. Defaults to data/orders-<timestamp>.csv, or "
        "to data/orders.csv when --fixed is set.",
    )
    parser.add_argument(
        "--fixed",
        action="store_true",
        help="Generate the fixed, deterministic dataset that "
        "tests/aws/test_datalake_e2e.py depends on: writes to "
        "data/orders.csv (unless --out is set) using seed 42 (unless "
        "--seed is set).",
    )
    args = parser.parse_args()

    if args.fixed:
        seed = args.seed if args.seed is not None else 42
        out = args.out if args.out is not None else DEFAULT_OUTPUT
    else:
        # Microsecond resolution: two runs started in the same second (e.g.
        # re-running the script quickly from an IDE) must still get distinct
        # filenames and seeds, or the second run silently overwrites the
        # first with a %Y%m%d%H%M%S-only timestamp.
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        seed = args.seed if args.seed is not None else int(timestamp)
        out = (
            args.out
            if args.out is not None
            else REPO_ROOT / "data" / f"orders-{timestamp}.csv"
        )
        if out.exists():
            raise FileExistsError(
                f"{out} already exists — refusing to overwrite a "
                "timestamped dataset. Re-run, or pass --out explicitly."
            )

    rows = generate_rows(args.rows, seed)
    write_csv(rows, out)
    duplicate_count = sum(1 for i in DUPLICATE_ROW_INDICES if i <= args.rows)
    print(
        f"Wrote {len(rows)} rows ({args.rows} base + {duplicate_count} duplicates) to {out}"
    )


if __name__ == "__main__":
    main()
