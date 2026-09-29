"""
Thin DynamoDB access layer. Uses boto3's resource API directly rather than
an ORM — the schema here is small enough (three tables, no joins) that an
ORM would add more indirection than it saves.

Table names come from environment variables so the same code runs against
whatever the SAM template names the tables in each stage (dev/prod).
"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache

import boto3

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


@lru_cache
def _resource():
    return boto3.resource("dynamodb", region_name=AWS_REGION)


def _floats_to_decimal(value):
    """boto3's DynamoDB resource API rejects Python `float` outright
    ("Float types are not supported. Use Decimal types instead.") - convert
    recursively so callers can keep ordinary `float` fields on their Pydantic
    models (Product.price, Order.amount, an inventory-request payload with a
    new price, ...) and just pass `to_item(model)` to put_item/update_item.
    """
    if isinstance(value, float):
        # str() first: Decimal(3900.0) can carry binary-float noise that
        # Decimal(str(3900.0)) avoids.
        return Decimal(str(value))
    if isinstance(value, list):
        return [_floats_to_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _floats_to_decimal(v) for k, v in value.items()}
    return value


def to_item(model) -> dict:
    """Convert a Pydantic model into a DynamoDB-safe dict for put_item/
    update_item (recursively turns float into Decimal)."""
    return _floats_to_decimal(model.model_dump())


def products_table():
    return _resource().Table(os.environ.get("PRODUCTS_TABLE", "CharkhaLifestyleProducts"))


def inventory_requests_table():
    return _resource().Table(os.environ.get("INVENTORY_REQUESTS_TABLE", "CharkhaLifestyleInventoryChangeRequests"))


def orders_table():
    return _resource().Table(os.environ.get("ORDERS_TABLE", "CharkhaLifestyleOrders"))