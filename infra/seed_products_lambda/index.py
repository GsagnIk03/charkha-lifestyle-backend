"""
Custom Resource handler: runs as part of `cdk deploy` itself (wrapped in a
cr.Provider in charkha_stack.py), not as a separate script anyone has to
remember to run. On every deploy — local or via CI, doesn't matter, it's
the same CloudFormation stack either way — CloudFormation invokes this
Lambda, which:

  1. Checks whether the Products table already has items.
  2. If it's empty (a brand-new table, e.g. right after the very first
     deploy), seeds it with the 100-product sample catalog from
     seed_data.json.
  3. If it already has items, does nothing. This is the important part:
     it means re-deploying never silently overwrites price/stock/status an
     owner has since edited through the dashboard on these same
     product_ids — the seed only ever fires once, automatically, on a
     table that's never been touched.

seed_data.json is a generated copy of the backend repo's app/seed_data.py
— see scripts/gen_products.py, which writes both files together so they
can't drift apart. This Lambda only needs boto3 (built into every Lambda
Python runtime), so it's a plain asset zip, no pip bundling required.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import boto3

TABLE_NAME = os.environ["PRODUCTS_TABLE"]
# Lambda's runtime sets AWS_REGION (not AWS_DEFAULT_REGION, which is what
# boto3 checks by default) — pass it explicitly rather than lean on the
# Lambda bootstrap's undocumented env-var aliasing. Same pattern app/db.py
# already uses elsewhere in this repo.
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


def _floats_to_decimal(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_floats_to_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _floats_to_decimal(v) for k, v in value.items()}
    return value


def handler(event, context):
    physical_id = f"charkha-lifestyle-seed-products-{TABLE_NAME}"

    # Nothing to clean up on stack/resource deletion — this resource only
    # ever writes sample data, and deleting the Products table itself
    # (elsewhere in the stack) already takes that data with it.
    if event.get("RequestType") == "Delete":
        return {"PhysicalResourceId": physical_id}

    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)

    existing_count = table.scan(Select="COUNT").get("Count", 0)
    if existing_count > 0:
        print(
            f"Products table '{TABLE_NAME}' already has {existing_count} item(s) — "
            "skipping seed (this is expected on every deploy after the first)."
        )
        return {"PhysicalResourceId": physical_id}

    seed_data_path = os.path.join(os.path.dirname(__file__), "seed_data.json")
    with open(seed_data_path) as f:
        products = json.load(f)

    with table.batch_writer(overwrite_by_pkeys=["product_id"]) as batch:
        for item in products:
            batch.put_item(Item=_floats_to_decimal(item))

    print(f"Seeded {len(products)} products into '{TABLE_NAME}'.")
    return {"PhysicalResourceId": physical_id}