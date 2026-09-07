# Atelier — Infrastructure (AWS SAM)

Defines every AWS resource in the [architecture blueprint](https://claude.ai/code/artifact/12f6ab68-e085-4a6e-a121-054fd3b25b0a):
the Lambda function (Function URL, no API Gateway), three DynamoDB tables
(provisioned capacity, not on-demand — see the comment at the top of
`template.yaml` for why that matters), a Cognito User Pool, and two
S3+CloudFront pairs (frontend build, product media).

This has been checked for valid YAML and reviewed resource-by-resource
against the SAM/CloudFormation reference, but **not yet deployed against a
real AWS account** — treat the first `sam deploy` as a test run, not a
sure thing, and expect to fix at least something minor.

## Prerequisites

1. Install the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and the AWS CLI, and run `aws configure` with your account's credentials.
2. **Turn on billing alerts once, manually**: AWS Console → Billing → Billing Preferences → "Receive Billing Alerts". This can't be set via CloudFormation, and the `BillingAlarm` resource in this template does nothing without it.
3. (Optional, for Google sign-in) Create an OAuth client in [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials. You'll need the Cognito domain's callback URL for that, which only exists after the first deploy — so deploy once without Google, add the redirect URI, then redeploy with `GoogleClientId`/`GoogleClientSecret` set.
4. A Razorpay account (test-mode keys are enough to start: Razorpay Dashboard → Settings → API Keys).

## Deploy

```bash
cd infra
sam build
sam deploy --guided
```

`--guided` will prompt for the parameters in `template.yaml` (Stage,
AllowedOrigin, Google/Razorpay credentials) and save them to
`samconfig.toml` for future deploys. After it finishes, note the Outputs:

- `ApiFunctionUrl` → set as `VITE_API_BASE_URL` in the **frontend repo's**
  `.env`.
- `FrontendUrl` → this is what `AllowedOrigin` should become on your
  *next* deploy (chicken-and-egg on the first one — deploy once, then
  redeploy with the real CloudFront URL so CORS and Cognito's callback
  URLs are correct).
- `UserPoolId`, `UserPoolClientId` → the frontend needs these for Cognito.
- `UserPoolHostedUiDomain` → use this for the Google OAuth redirect URI
  above: `<that domain>/oauth2/idpresponse`.

The frontend repo's `dist/` folder (from `npm run build` there) needs to
land in `FrontendBucket` — a small `aws s3 sync dist/ s3://<bucket>
--delete` step, run from the frontend repo's own CI once that exists,
using the bucket name and distribution ID this stack's Outputs give you.
Invalidate the CloudFront distribution afterward so the new build is
served immediately rather than waiting out the cache TTL.

## After the store owner signs up

Add her to the `owners` Cognito group — nothing in the app does this
automatically, it's a deliberate manual step so "who can approve
inventory changes" is never something the app itself can silently grant:

```bash
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <UserPoolId> \
  --username <her email> \
  --group-name owners
```

## What's simplified here, deliberately

- No custom domain / ACM certificate — everything runs on the default
  `*.cloudfront.net` and Lambda Function URL domains for now. Adding
  Route 53 + ACM is straightforward later but adds a per-month cost
  (~$0.50 for the hosted zone) and isn't needed to get the site running.
- One `Stage` parameter (`dev` by default) rather than separate
  dev/staging/prod stacks — fine for one person building solo, worth
  revisiting before a real production launch.
- SES isn't in this template yet — it needs a verified sending identity,
  which is more naturally a manual console step than something to encode
  here. Add it once the notification emails in the backend TODOs are
  ready to be built.
