"""
Fully offline local run — no AWS account, no Docker, nothing to deploy.

Uses moto to fake DynamoDB entirely in memory, seeds a few sample
products, and bypasses Cognito auth (you're always treated as a signed-in
owner — see LOCAL_DEV in app/auth.py). Data resets every time you restart
this script. This is for clicking through the app only; none of this
reflects how auth or the database really behave once deployed.

Usage:
    pip install -r requirements.txt -r requirements-dev.txt
    python local_dev.py
Then point the frontend (the separate charkha-lifestyle-frontend repo) at
http://localhost:8000 — its .env.example already defaults to that.
"""

import os

os.environ["LOCAL_DEV"] = "true"
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("PRODUCTS_TABLE", "CharkhaLifestyleProducts")
os.environ.setdefault("INVENTORY_REQUESTS_TABLE", "CharkhaLifestyleInventoryChangeRequests")
os.environ.setdefault("ORDERS_TABLE", "CharkhaLifestyleOrders")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_local")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "local_dev_only")

from moto import mock_aws  # noqa: E402

_mock = mock_aws()
_mock.start()  # must start before boto3 (via app.db) ever touches DynamoDB

import boto3  # noqa: E402


def _create_tables() -> None:
    client = boto3.client("dynamodb", region_name=os.environ["AWS_REGION"])
    for table_name, key_name in [
        (os.environ["PRODUCTS_TABLE"], "product_id"),
        (os.environ["INVENTORY_REQUESTS_TABLE"], "request_id"),
        (os.environ["ORDERS_TABLE"], "order_id"),
    ]:
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=[{"AttributeName": key_name, "AttributeType": "S"}],
            KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",  # moto doesn't care; real deploys use infra/template.yaml's provisioned tables
        )


_create_tables()

from app.db import products_table  # noqa: E402

SAMPLE_PRODUCTS = [
    {
        "product_id": "p1",
        "name": "Wrap Midi Dress",
        "category": "Women",
        "price": 3150,
        "stock": 48,
        "description": "A wrap-front midi dress in washed cotton twill.",
        "image_keys": [],
        "status": "live",
        "last_edited_by": None,
    },
    {
        "product_id": "p2",
        "name": "Tailored Cotton Shirt",
        "category": "Men",
        "price": 1890,
        "stock": 6,
        "description": "A crisp, tailored cotton shirt with a clean collar.",
        "image_keys": [],
        "status": "live",
        "last_edited_by": None,
    },
    {
        "product_id": "p3",
        "name": "Merino Crew Sweater",
        "category": "Men",
        "price": 2990,
        "stock": 32,
        "description": "A soft, fully-fashioned merino sweater with a ribbed crew neckline.",
        "image_keys": [],
        "status": "live",
        "last_edited_by": None,
    },
    {
        "product_id": "p4",
        "name": "Pleated Midi Skirt",
        "category": "Women",
        "price": 2450,
        "stock": 21,
        "description": "A pleated midi skirt in olive twill.",
        "image_keys": [],
        "status": "live",
        "last_edited_by": None,
    },
]
for item in SAMPLE_PRODUCTS:
    products_table().put_item(Item=item)


if __name__ == "__main__":
    import uvicorn

    from app.main import app

    print("\n--- Charkha Lifestyle backend: LOCAL DEV MODE ---")
    print("In-memory fake DynamoDB (moto), seeded with 4 sample products.")
    print("Auth is bypassed — every request is treated as a signed-in owner.")
    print("Data resets on restart. Never run with LOCAL_DEV=true anywhere real.\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
