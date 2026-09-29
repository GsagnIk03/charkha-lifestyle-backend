# Charkha Lifestyle — Infrastructure (AWS CDK, Python)

Defines the AWS side of the [architecture blueprint](https://claude.ai/code/artifact/12f6ab68-e085-4a6e-a121-054fd3b25b0a):
the Lambda function (Function URL, no API Gateway), three DynamoDB tables
(provisioned capacity, not on-demand — see the comment at the top of
`charkha_lifestyle/charkha_stack.py` for why that matters), a Cognito User
Pool, and an S3+CloudFront pair for product media.

**The frontend is not here anymore.** It deploys to
[Vercel](https://vercel.com) instead of S3+CloudFront — Vercel builds and
deploys the React app straight from GitHub on every push, for free, and
handles the custom domain/HTTPS itself. This stack only covers what Vercel
can't do: the API, the database, auth, and product image storage. See
"The frontend: Vercel" and "Your domain: GoDaddy" below.

This replaced an AWS SAM template that deployed successfully as
`charkha-lifestyle-dev` — see "Migrating from the old SAM stack" below for
the one-time cutover if you still have that stack around.

## Why CDK over SAM

Real, code-checked infrastructure instead of hand-written YAML: every
construct below was actually synthesized and its generated CloudFormation
inspected before this was handed to you (not just "should work" — the
region defaulting bug a few lines down was caught exactly that way). CDK
also gives you `cdk diff` (see exactly what a deploy will change _before_
it changes anything) and native TypeScript/Python instead of YAML
Conditions/Fn::If for things like the optional Google identity provider.

**One thing does not change**: `pydantic_core` (FastAPI's compiled
dependency) still needs to be built for Lambda's Linux runtime, so Docker
Desktop is still required to deploy from Windows/macOS — this isn't a SAM
quirk, it's inherent to shipping compiled Python dependencies to Lambda.
CDK's Python bundling uses the same base build image SAM did
(`public.ecr.aws/sam/build-python3.12`), so the Docker-networking
troubleshooting below will look familiar.

## Prerequisites

1. Install [Node.js](https://nodejs.org/) (needed for the `cdk` CLI itself — CDK's CLI is a Node tool even for a Python app) and the AWS CDK CLI: `npm install -g aws-cdk`.
2. Install the AWS CLI and run `aws configure` with your account's credentials, if you haven't already.
3. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and make sure it's running before you build/deploy — same `pydantic_core` reason as the old SAM setup.
4. **Set up the real spend trip-wire once, manually — do this before your first deploy** (skip if you already did this for the SAM stack): AWS Console → Billing and Cost Management → **Budgets** → Create budget → "Zero spend budget" (or a Cost budget with a $1 threshold) → add your email as an alert recipient. Also tick **"Receive AWS Free Tier Usage Alerts"** in Billing Preferences on the same page.
5. Bootstrap CDK in your account/region — a one-time step per account+region that sets up the S3 bucket CDK uses to stage deployment assets:
   ```bash
   cdk bootstrap aws://<your-account-id>/ap-south-1
   ```
6. (Optional, for Google sign-in) Create an OAuth client in [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials. You'll need the Cognito domain's callback URL for that, which only exists after the first deploy — deploy once without Google, add the redirect URI, then redeploy with `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` set.
7. A Razorpay account (test-mode keys are enough to start: Razorpay Dashboard → Settings → API Keys).

## Set up the CDK app itself

```bash
cd infra
python -m venv .venv
source .venv/bin/activate      # Windows Git Bash / PowerShell: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env           # fill in Razorpay keys, Google OAuth (optional), etc. — see the comments in the file
```

`infra/.env` is what configures a deploy — not interactive prompts, not
CloudFormation Parameters. That's a deliberate difference from SAM's
`--guided` flow: no NoEcho masked double-entry, no re-typing secrets on
every deploy, and `cdk diff`/`cdk deploy` behave predictably since values
are fixed before synth even starts. It's gitignored; never commit it.

## Deploy

```bash
cd infra
cdk diff      # optional but recommended — see exactly what would change
cdk deploy
```

That's the whole command, every time — no separate build step (CDK builds
the Lambda bundle as part of `cdk deploy`/`cdk synth` automatically) and
no `--guided` flag to remember. Tags (`app-1=charkha-lifestyle`, for Cost
Explorer filtering) and the target region are already set in `app.py` —
nothing to pass on the command line.

After it finishes, note the Outputs:

- `ApiFunctionUrl` → set as `VITE_API_BASE_URL` in the **frontend repo's**
  Vercel project environment variables.
- `UserPoolId`, `UserPoolClientId` → the frontend needs these for Cognito.
- `UserPoolHostedUiDomain` → use this for the Google OAuth redirect URI
  above: `<that domain>/oauth2/idpresponse`.
- `MediaUrl` → where product images are served from.

There's no `FrontendUrl` output anymore — that's now whatever domain
Vercel gives your project (see below). Once you know it, set it as
`ALLOWED_ORIGIN` in `infra/.env` and redeploy so CORS and Cognito's
callback URLs are correct (the same chicken-and-egg the old SAM setup
had on its first deploy).

## The frontend: Vercel

1. Push the frontend repo to GitHub if it isn't already.
2. In the [Vercel dashboard](https://vercel.com/new), import that GitHub
   repo. Vercel auto-detects a Vite/React app; no config file needed for a
   default setup.
3. Add `VITE_API_BASE_URL` (this stack's `ApiFunctionUrl` output) and any
   other `VITE_*` variables the frontend needs, under Project Settings →
   Environment Variables.
4. Deploy. Every push to your main branch auto-deploys from here on —
   this is your CI/CD, free, no CodePipeline/CodeBuild involved.
5. Copy the `*.vercel.app` URL (or your custom domain once step below is
   done) into `ALLOWED_ORIGIN` in `infra/.env` and `cdk deploy` again.

## Your domain: GoDaddy

Your domain stays registered at GoDaddy — nothing needs to move to Route
53 or anywhere else. You're only ever adding DNS records at GoDaddy that
point at services hosted elsewhere.

**For the frontend (Vercel):**

1. In the Vercel project → Settings → Domains, add your domain (e.g.
   `charkhalifestyle.com` or `www.charkhalifestyle.com`).
2. Vercel shows you the exact record(s) to add — usually an `A` record
   (for the bare/apex domain, e.g. `charkhalifestyle.com`) or a `CNAME`
   (for a subdomain, e.g. `www.charkhalifestyle.com`) pointing at Vercel's
   servers.
3. At GoDaddy: My Products → your domain → DNS → Manage Zones, and add
   exactly the record(s) Vercel showed you. DNS propagation is usually
   minutes, sometimes up to ~48 hours worst case.
4. Vercel issues and renews the HTTPS certificate automatically once the
   record is live — nothing to do on the AWS side for this.
5. Update `ALLOWED_ORIGIN` in `infra/.env` to the real domain and
   redeploy once it's working.

**For the API** (optional — `ApiFunctionUrl`'s raw `*.lambda-url.ap-south-1.on.aws`
address works fine as-is, this is purely cosmetic): a Lambda Function URL
can't take a custom domain directly. You'd need a CloudFront distribution
in front of it with an ACM certificate (ACM certs for CloudFront must be
requested in **us-east-1**, regardless of which region the rest of the
stack lives in — the same regional quirk that broke the old billing
alarm). This is a real chunk of additional infrastructure, so it's left
out for now; ask if you want it added once the store is otherwise live.

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

## Migrating from the old SAM stack

Table names, the S3 bucket names, and the Cognito domain prefix are all
identical to what the SAM template used (deliberately, to keep things
recognizable) — which means the two stacks **cannot coexist**; deploying
this one while the SAM stack still exists will fail on name collisions.
Since the SAM stack never held any real customer data, delete it first:

```bash
cd infra   # the OLD infra/ checkout, before this migration, if you kept a copy
sam delete
```

Then follow "Deploy" above from a clean slate.

## Troubleshooting / operating notes

Carried over from the SAM days — still relevant, since the underlying
Docker/Lambda-bundling mechanics didn't change:

- **`cdk build --use-container`-equivalent bundling hanging or failing
  with `ReadTimeoutError`**: almost always Docker Desktop's WSL2
  networking, not a broken package. Fix, in order: (1) `wsl --shutdown`
  in an elevated PowerShell, then fully quit and relaunch Docker Desktop;
  (2) `PIP_DEFAULT_TIMEOUT=120` is already baked into the bundling
  environment in `charkha_stack.py`, so this shouldn't need repeating,
  but if it still stalls, a VPN or MTU mismatch is next — try
  disconnecting any VPN, or set `networkingMode=mirrored` in
  `%UserProfile%\.wslconfig` and repeat step 1.
- **Windows: run `cdk` commands from PowerShell if Git Bash gives you a
  "Fatal error in launcher"** — the same Node-CLI-on-Windows launcher
  quirk SAM's CLI had. `cdk --version` working in PowerShell and failing
  in Git Bash is the tell.
- **Keep the repo root's `requirements.txt` (the Lambda's, not
  `infra/requirements.txt`) minimal.** `boto3`/`botocore` are preinstalled
  in every Lambda Python runtime and don't belong there; neither does
  `uvicorn` (Lambda uses `lambda_handler.py` via Mangum). Both live in
  `requirements-dev.txt` for local runs only. Every package added to the
  Lambda's `requirements.txt` is one more thing the bundler has to fetch
  from PyPI on every deploy.
- **Before adding any new resource reference**, check the attribute/
  property actually exists on that CDK construct — don't assume. This
  bit the old SAM template once already (`AWS::Lambda::Function` has no
  `FunctionUrl` attribute) and would have bitten this migration too, in a
  different spot: `UserPoolDomain.base_url()` in this CDK version
  hardcodes `us-east-1` into the URL regardless of the stack's actual
  region — confirmed by actually synthesizing the stack and inspecting
  the generated template, not by reading docs. `charkha_stack.py` builds
  that URL explicitly instead; don't revert it back to `base_url()`
  without re-checking.
- **`infra/.env` needs `AWS_REGION=ap-south-1` set explicitly.** Without
  it, the region silently falls back to whatever your AWS CLI's default
  profile region is — which may not be `ap-south-1` (yours defaults to
  `us-east-1`) — and a deploy would go to the wrong region without any
  error. `.env.example` already has this set; just don't delete the line.

## What's simplified here, deliberately

- No custom domain on the API itself (see "Your domain" above) — adding
  Route 53 + ACM + a CloudFront front door for the Function URL is
  straightforward later but isn't needed to get the site running.
- No AWS-native CI/CD (CodePipeline/CodeBuild): its free tier is limited
  to an account's first 12 months, not the Always Free list, which
  conflicts with this project's zero-charge requirement. Vercel's own
  git-push deploy covers the frontend for free; the backend deploys
  manually via `cdk deploy` for now. Revisit with GitHub Actions (free
  for reasonable usage, runs `cdk deploy` from CI) if/when automating the
  backend deploy is worth it.
- One `Stage` value (`dev` by default, via `infra/.env`) rather than
  separate dev/staging/prod stacks — fine for one person building solo,
  worth revisiting before a real production launch.
- SES isn't in this stack yet — it needs a verified sending identity,
  which is more naturally a manual console step than something to encode
  here. Add it once the notification emails in the backend TODOs are
  ready to be built.
