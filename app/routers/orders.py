from __future__ import annotations

import os
import uuid

import razorpay
from fastapi import APIRouter, Depends

from app.auth import verify_token
from app.db import orders_table, products_table
from app.models import Order, OrderCreate

router = APIRouter(prefix="/orders", tags=["orders"])

_client: razorpay.Client | None = None


def _razorpay_client() -> razorpay.Client:
    global _client
    if _client is None:
        _client = razorpay.Client(
            auth=(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
        )
    return _client


@router.post("", response_model=Order)
def create_order(payload: OrderCreate, claims: dict = Depends(verify_token)):
    # Price from the Products table, never from the client — the frontend
    # sends product_id + quantity only.
    amount = 0.0
    for item in payload.items:
        product = products_table().get_item(Key={"product_id": item.product_id}).get("Item")
        if product:
            amount += float(product["price"]) * item.quantity

    razorpay_order = _razorpay_client().order.create(
        {
            "amount": int(amount * 100),  # paise
            "currency": "INR",
            "payment_capture": 1,
        }
    )

    order = Order(
        order_id=str(uuid.uuid4()),
        user_id=claims.get("sub", "unknown"),
        items=payload.items,
        amount=amount,
        razorpay_order_id=razorpay_order["id"],
    )
    orders_table().put_item(Item=order.model_dump())
    return order


# TODO: a `/orders/webhook` endpoint that verifies Razorpay's webhook
# signature (see https://razorpay.com/docs/webhooks/) and marks the order
# paid — don't trust the frontend to report a successful payment on its
# own, always confirm server-side via the webhook.
