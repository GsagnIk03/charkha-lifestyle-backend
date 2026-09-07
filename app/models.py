from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductStatus(str, Enum):
    live = "live"
    draft = "draft"


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    price: float
    stock: int
    description: str = ""
    image_keys: list[str] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.draft
    last_edited_by: Optional[str] = None


class ProductCreate(BaseModel):
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


class InventoryChangeRequestCreate(BaseModel):
    product_id: str
    change_type: ChangeType
    payload: dict


class InventoryChangeRequest(BaseModel):
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


class InventoryChangeDecision(BaseModel):
    status: ChangeRequestStatus
    note: Optional[str] = None


class OrderItem(BaseModel):
    product_id: str
    quantity: int
    size: Optional[str] = None


class OrderCreate(BaseModel):
    items: list[OrderItem]


class Order(BaseModel):
    order_id: str
    user_id: str
    items: list[OrderItem]
    amount: float
    currency: str = "INR"
    status: str = "created"
    razorpay_order_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
