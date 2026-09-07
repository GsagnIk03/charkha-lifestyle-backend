"""
Thin DynamoDB access layer. Uses boto3's resource API directly rather than
an ORM — the schema here is small enough (three tables, no joins) that an
ORM would add more indirection than it saves.

Table names come from environment variables so the same code runs against
whatever the SAM template names the tables in each stage (dev/prod).
"""

from __future__ import annotations

import os
from functools import lru_cache

import boto3

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


@lru_cache
def _resource():
    return boto3.resource("dynamodb", region_name=AWS_REGION)


def products_table():
    return _resource().Table(os.environ.get("PRODUCTS_TABLE", "AtelierProducts"))


def inventory_requests_table():
    return _resource().Table(os.environ.get("INVENTORY_REQUESTS_TABLE", "AtelierInventoryChangeRequests"))


def orders_table():
    return _resource().Table(os.environ.get("ORDERS_TABLE", "AtelierOrders"))
