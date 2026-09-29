"""
One-time (or re-runnable) seed of the *real*, deployed Products DynamoDB
table with the 100-product sample catalog from app/seed_data.py.

Unlike local_dev.py (which fakes DynamoDB in memory with moto), this talks
to whatever real table PRODUCTS_TABLE / AWS_REGION point at — so run this
only after `cdk deploy` has created the table, and only against a table
you actually want populated (it's safe to re-run: put_item overwrites by
product_id, it never duplicates).

Usage:
    cd infra && cdk deploy   # first, if you haven't already
    cd ..
    export PRODUCTS_TABLE=<ApiFunctionUrl output's table name, or see infra/README.md>
    export AWS_REGION=ap-south-1
    python scripts/seed_products.py

Or just `cp .env.example .env`, fill it in, and this script will pick up
the same PRODUCTS_TABLE / AWS_REGION your app/db.py already uses (it loads
.env if python-dotenv is installed and a .env file is present).
"""
from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import _floats_to_decimal, products_table  # noqa: E402
from app.seed_data import SEED_PRODUCTS  # noqa: E402


def main() -> None:
    table_name = os.environ.get("PRODUCTS_TABLE", "CharkhaLifestyleProducts")
    region = os.environ.get("AWS_REGION", "ap-south-1")
    print(f"Seeding {len(SEED_PRODUCTS)} products into DynamoDB table "
          f"'{table_name}' in {region}...")
    confirm = input("This writes to a REAL AWS table, not a local fake. Continue? [y/N] ")
    if confirm.strip().lower() != "y":
        print("Aborted.")
        return

    table = products_table()
    with table.batch_writer(overwrite_by_pkeys=["product_id"]) as batch:
        for item in SEED_PRODUCTS:
            batch.put_item(Item=_floats_to_decimal(item))

    print(f"Done — {len(SEED_PRODUCTS)} products written to '{table_name}'.")


if __name__ == "__main__":
    main()