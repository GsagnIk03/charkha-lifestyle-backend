# Charkha Lifestyle — Backend

FastAPI app, deployed to AWS Lambda via a Function URL (no API Gateway —
see the [architecture blueprint](https://claude.ai/code/artifact/12f6ab68-e085-4a6e-a121-054fd3b25b0a)
for why). Runs the same either way: `uvicorn` locally, `lambda_handler.py`
(via [Mangum](https://github.com/jordaneremieff/mangum)) in AWS.

This repo also owns `infra/` — the AWS SAM template that defines every
resource for the whole project, including the S3 bucket and CloudFront
distribution that serve the **frontend** (a separate repo). That split is
deliberate: infrastructure lives with the backend/deploy tooling, and the
frontend repo just builds static files and ships them to the bucket this
repo's stack creates. See "Deploy" below for how the two connect.

## Local setup — against real AWS

```bash
python -m venv .venv
source .venv/bin/activate      # Windows Git Bash / PowerShell: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env           # fill in DynamoDB table names, Cognito pool, Razorpay keys
uvicorn app.main:app --reload
```

This talks to real DynamoDB tables and a real Cognito pool — deploy those
first (`sam deploy`, see `infra/README.md`) and copy their names/IDs into
`.env`.

## Local setup — fully offline (no AWS account needed)

For just clicking through the app without deploying anything:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows Git Bash / PowerShell: source .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt
python local_dev.py
```

`local_dev.py` fakes DynamoDB entirely in memory (via [moto](https://github.com/getmoto/moto)),
seeds four sample products, and bypasses Cognito auth — every request is
treated as a signed-in owner. Data resets every time you restart it. It's
for exercising the UI and the approval workflow only; don't mistake it for
how auth or persistence really behave once deployed.

## Structure

```
app/            FastAPI application code
infra/          AWS SAM template — every resource for the whole project
lambda_handler.py   Lambda entry point (Mangum-wrapped FastAPI app)
local_dev.py    Offline dev server (in-memory DB, bypassed auth)
```

- `app/main.py` — FastAPI app, CORS, router registration.
- `app/models.py` — Pydantic models for Product, InventoryChangeRequest,
  Order. Mirrors the **frontend** repo's `src/api/types.ts` — keep the two
  in sync by hand across repos until there's a shared schema.
- `app/db.py` — DynamoDB table handles (boto3 resource API).
- `app/auth.py` — Cognito JWT verification (`verify_token`) and an
  owner-only guard (`require_owner`) that checks the `cognito:groups`
  claim for an `owners` group. **Untested against a real User Pool yet.**
- `app/routers/products.py` — catalog reads, and direct owner writes.
- `app/routers/inventory_requests.py` — the approval workflow: team
  members POST here, never to `/products` directly; the owner's PATCH on
  approval applies the change to Products and marks the request approved
  in one DynamoDB transaction (see the code comment for why that matters).
- `app/routers/orders.py` — creates a Razorpay order server-side (price
  computed from the Products table, never trusted from the client).

## Not done yet

- Razorpay webhook signature verification (`app/routers/orders.py` has a
  TODO — payment confirmation must come from the webhook, not the
  frontend reporting success).
- SES notifications on submit/approve/reject.
- Tightening `InventoryChangeRequestCreate.payload` from a bare `dict` to
  a model that only allows editable Product fields (flagged inline in
  `inventory_requests.py` — needed before this is safe to expose beyond a
  trusted team).
- Automated tests (pytest + moto for mocked DynamoDB would be the natural
  choice here).

## Deploy

See `infra/README.md` for the full sequence and the one manual AWS
Console step (billing alerts) that can't be scripted. Broadly:

```bash
cd infra
sam build
sam deploy --guided
```

That creates the Lambda function, DynamoDB tables, Cognito pool, **and**
the frontend's S3 bucket + CloudFront distribution. Take the `Outputs` it
prints — `ApiFunctionUrl`, `FrontendUrl`, `UserPoolId`, `UserPoolClientId`
— and:

- Put `ApiFunctionUrl` into the **frontend** repo's `.env` as
  `VITE_API_BASE_URL`.
- The frontend repo's deploy step needs the `FrontendBucket` name and
  `FrontendDistribution` ID from this stack (`aws cloudformation
  describe-stacks` or the console) to run `aws s3 sync dist/
  s3://<bucket>` and invalidate the CloudFront cache — pass those in as
  secrets/env vars in whatever CI you set up there, since this repo's
  stack is the only place they're created.
  s3://<bucket>` and invalidate the CloudFront cache — pass those in as
  secrets/env vars in whatever CI you set up there, since this repo's
  stack is the only place they're created.
