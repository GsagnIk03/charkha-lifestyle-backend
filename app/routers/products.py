from __future__ import annotations

import uuid

from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import require_owner
from app.db import products_table, to_item
from app.models import Product, ProductCreate, ProductStatus

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[Product])
def list_products(
    category: str | None = None,
    # Query param is `status` (what the frontend actually sends) while the
    # Python parameter stays `status_filter` so it doesn't shadow the
    # `fastapi.status` module used elsewhere in this file.
    status_filter: ProductStatus | None = Query(default=None, alias="status"),
    limit: int = 50,
):
    # A `scan` is fine at catalog sizes in the hundreds/low thousands.
    # If this ever gets slow, add a GSI on `category` (and one on `status`)
    # and switch to `query` instead.
    filters = []
    if category:
        filters.append(Attr("category").eq(category))
    if status_filter:
        filters.append(Attr("status").eq(status_filter.value))

    filter_expression = None
    if filters:
        filter_expression = filters[0]
        for f in filters[1:]:
            filter_expression = filter_expression & f

    # DynamoDB's own `Limit` caps how many items are *scanned* before a
    # FilterExpression is applied, not how many survive it — a scan with
    # Limit=4 and a status filter can come back with fewer than 4 matches
    # even when far more than 4 matching items exist in the table, simply
    # because some of the 4 raw items it happened to examine didn't pass
    # the filter (e.g. "New Arrivals" on the homepage asking for
    # status=live&limit=4 was silently returning as few as 3 items despite
    # ~88 of the 100 seeded products being live). To actually return up to
    # `limit` matching items, keep paging through the table with
    # ExclusiveStartKey/LastEvaluatedKey until enough matches are collected
    # or the table is exhausted.
    items: list[dict] = []
    last_evaluated_key = None
    while len(items) < limit:
        scan_kwargs: dict = {}
        if filter_expression is not None:
            scan_kwargs["FilterExpression"] = filter_expression
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        result = products_table().scan(**scan_kwargs)
        items.extend(result.get("Items", []))

        last_evaluated_key = result.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return items[:limit]


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: str):
    result = products_table().get_item(Key={"product_id": product_id})
    item = result.get("Item")
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return item


@router.post("", response_model=Product, dependencies=[Depends(require_owner)])
def create_product(payload: ProductCreate):
    product = Product(product_id=str(uuid.uuid4()), status=ProductStatus.draft, **payload.model_dump())
    products_table().put_item(Item=to_item(product))
    return product


@router.patch("/{product_id}", response_model=Product, dependencies=[Depends(require_owner)])
def update_product(product_id: str, payload: ProductCreate):
    existing = products_table().get_item(Key={"product_id": product_id}).get("Item")
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    updated = Product(**{**existing, **payload.model_dump()})
    products_table().put_item(Item=to_item(updated))
    return updated


@router.patch("/{product_id}/status", response_model=Product, dependencies=[Depends(require_owner)])
def set_product_status(product_id: str, new_status: ProductStatus = Query(alias="status")):
    """Quick live/draft toggle for the dashboard — doesn't require resending
    the whole product body the way PATCH /{product_id} does."""
    existing = products_table().get_item(Key={"product_id": product_id}).get("Item")
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    updated = Product(**{**existing, "status": new_status})
    products_table().put_item(Item=to_item(updated))
    return updated


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_owner)])
def delete_product(product_id: str):
    existing = products_table().get_item(Key={"product_id": product_id}).get("Item")
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    products_table().delete_item(Key={"product_id": product_id})