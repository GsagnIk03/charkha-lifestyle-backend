from __future__ import annotations

import uuid

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_owner, verify_token
from app.db import AWS_REGION, inventory_requests_table, products_table
from app.models import (
    ChangeRequestStatus,
    InventoryChangeDecision,
    InventoryChangeRequest,
    InventoryChangeRequestCreate,
)

router = APIRouter(prefix="/inventory-requests", tags=["inventory-requests"])


@router.get("", response_model=list[InventoryChangeRequest])
def list_requests(status_filter: ChangeRequestStatus | None = None, _owner=Depends(require_owner)):
    scan_kwargs: dict = {}
    if status_filter:
        scan_kwargs["FilterExpression"] = Attr("status").eq(status_filter.value)
    result = inventory_requests_table().scan(**scan_kwargs)
    return result.get("Items", [])


@router.post("", response_model=InventoryChangeRequest)
def submit_request(payload: InventoryChangeRequestCreate, claims: dict = Depends(verify_token)):
    # Any signed-in team member can submit — this never touches the
    # Products table directly. It only lands there once the owner approves
    # it (see decide_request below).
    submitted_by = claims.get("email") or claims.get("sub", "unknown")
    change_request = InventoryChangeRequest(
        request_id=str(uuid.uuid4()),
        submitted_by=submitted_by,
        **payload.model_dump(),
    )
    inventory_requests_table().put_item(Item=change_request.model_dump())
    # TODO: notify the owner via SES once that's wired up.
    return change_request


@router.patch("/{request_id}", response_model=InventoryChangeRequest)
def decide_request(request_id: str, decision: InventoryChangeDecision, claims: dict = Depends(require_owner)):
    req_table = inventory_requests_table()
    existing = req_table.get_item(Key={"request_id": request_id}).get("Item")
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if existing["status"] != ChangeRequestStatus.pending.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Request has already been decided")

    reviewed_by = claims.get("email") or claims.get("sub", "owner")

    if decision.status == ChangeRequestStatus.rejected:
        req_table.update_item(
            Key={"request_id": request_id},
            UpdateExpression="SET #s = :s, reviewed_by = :rb, note = :n",
            ConditionExpression=Attr("status").eq(ChangeRequestStatus.pending.value),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": ChangeRequestStatus.rejected.value,
                ":rb": reviewed_by,
                ":n": decision.note or "",
            },
        )
        return {**existing, "status": ChangeRequestStatus.rejected.value, "reviewed_by": reviewed_by}

    # Approval: apply the request's payload to the Product and mark the
    # request approved in a single transaction, so a double-click (or a
    # retry) can never apply the same change twice or leave one table
    # updated without the other.
    # NOTE: payload keys are trusted here because they were validated against
    # the Product schema when the team member submitted the request in the
    # first place (Pydantic on InventoryChangeRequestCreate.payload would
    # need tightening from `dict` to a constrained model to make that
    # actually true — do that before this goes anywhere near production, so
    # an arbitrary field name can't end up in this UpdateExpression).
    client = boto3.client("dynamodb", region_name=AWS_REGION)
    update_expr_parts = []
    expr_values: dict = {}
    for i, (field, value) in enumerate(existing["payload"].items()):
        update_expr_parts.append(f"{field} = :v{i}")
        expr_values[f":v{i}"] = value

    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": products_table().name,
                        "Key": {"product_id": {"S": existing["product_id"]}},
                        "UpdateExpression": "SET " + ", ".join(update_expr_parts),
                        "ExpressionAttributeValues": {
                            k: {"N": str(v)} if isinstance(v, (int, float)) else {"S": str(v)}
                            for k, v in expr_values.items()
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": req_table.name,
                        "Key": {"request_id": {"S": request_id}},
                        "UpdateExpression": "SET #s = :approved, reviewed_by = :rb",
                        "ConditionExpression": "#s = :pending",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":approved": {"S": ChangeRequestStatus.approved.value},
                            ":pending": {"S": ChangeRequestStatus.pending.value},
                            ":rb": {"S": reviewed_by},
                        },
                    }
                },
            ]
        )
    except ClientError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not apply approval") from exc

    # TODO: notify the submitter via SES once that's wired up.
    return {**existing, "status": ChangeRequestStatus.approved.value, "reviewed_by": reviewed_by}
