from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CamelModel(BaseModel):
    """Base for every request/response model.

    Python code and DynamoDB items stay snake_case (product_id, image_keys,
    ...) but everything that crosses HTTP is camelCase (productId,
    imageKeys, ...), matching the frontend's api/types.ts. populate_by_name
    means internal code can still build these with snake_case keyword args
    (Product(product_id=...)) and .model_dump() still returns snake_case
    keys for writing to DynamoDB — only the JSON that FastAPI sends/accepts
    over the wire is affected (response_model_by_alias defaults to True).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProductStatus(str, Enum):
    live = "live"
    draft = "draft"


class Product(CamelModel):
    product_id: str
    name: str
    category: str
    price: float
    stock: int
    description: str = ""
    image_keys: list[str] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.draft
    last_edited_by: Optional[str] = None


class ProductCreate(CamelModel):
    name: str
    category: str
    price: float
    stock: int
    description: str = ""
    image_keys: list[str] = Field(default_factory=list)


class ChangeType(str, Enum):
    price_update = "price_update"
    stock_update = "stock_update"
    description_update = "description_update"
    new_listing = "new_listing"


class ChangeRequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class InventoryChangeRequestCreate(CamelModel):
    product_id: str
    change_type: ChangeType
    payload: dict


class InventoryChangeRequest(CamelModel):
    request_id: str
    product_id: str
    submitted_by: str
    change_type: ChangeType
    payload: dict
    status: ChangeRequestStatus = ChangeRequestStatus.pending
    reviewed_by: Optional[str] = None
    note: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    decided_at: Optional[str] = None


class InventoryChangeDecision(CamelModel):
    status: ChangeRequestStatus
    note: Optional[str] = None


class OrderItem(CamelModel):
    product_id: str
    quantity: int
    size: Optional[str] = None


class OrderCreate(CamelModel):
    items: list[OrderItem]


class Order(CamelModel):
    order_id: str
    user_id: str
    items: list[OrderItem]
    amount: float
    currency: str = "INR"
    status: str = "created"
    razorpay_order_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)