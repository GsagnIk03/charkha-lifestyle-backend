#!/usr/bin/env bash
# One-time setup: lets GitHub Actions deploy this CDK stack via short-lived
# OIDC credentials — no AWS access keys stored in GitHub. Run this ONCE
# from your machine with the same AWS CLI credentials you use for
# `cdk deploy` (needs IAM permissions to create roles/OIDC providers).
#
# After this runs successfully, add the printed role ARN as the
# AWS_DEPLOY_ROLE_ARN secret (or repo variable) in your GitHub repo's
# Settings -> Secrets and variables -> Actions, so
# .github/workflows/deploy-backend.yml can use it.
#
# Safe to re-run: every step checks whether it already exists first.

set -euo pipefail

# ---- Fill these in ----
GITHUB_ORG="GsagnIk03"
GITHUB_REPO="charkha-lifestyle-backend"
# Restricts which branch is allowed to assume this role. Your repo's
# default branch is "master" (checked via github.com/GsagnIk03/charkha-lifestyle-backend).
GITHUB_BRANCH="master"
ROLE_NAME="github-actions-cdk-deploy-charkha"
# ------------------------

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS account: $ACCOUNT_ID"

OIDC_URL="token.actions.githubusercontent.com"
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_URL}"

if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1; then
  echo "GitHub OIDC provider already exists — reusing it."
else
  echo "Creating GitHub OIDC provider..."
  # This is GitHub's well-known OIDC thumbprint (documented by GitHub /
  # AWS); AWS also validates the cert chain itself, so this value is
  # effectively just a required field, not a secret you need to keep in
  # sync.
  aws iam create-open-id-connect-provider \
    --url "https://${OIDC_URL}" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1"
fi

TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "${OIDC_ARN}" },
      "Action": [
        "sts:AssumeRoleWithWebIdentity",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": { "${OIDC_URL}:aud": "sts.amazonaws.com" },
        "StringLike": {
          "${OIDC_URL}:sub": [
            "repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/${GITHUB_BRANCH}",
            "repo:${GITHUB_ORG}/${GITHUB_REPO}:environment:production"
          ]
        }
      }
    }
  ]
}
EOF
)
# Two allowed "sub" shapes on purpose: GitHub issues a DIFFERENT subject
# claim depending on whether the job targets a GitHub Environment.
#   - No `environment:` on the job -> repo:ORG/REPO:ref:refs/heads/BRANCH
#   - `environment: production` on the job (as deploy-backend.yml has,
#     for the optional manual-approval gate) -> repo:ORG/REPO:environment:production
# deploy-backend.yml sets `environment: production`, so in practice only
# the second one is ever actually issued today -- but keeping both here
# means this still works if that `environment:` line is ever removed.
#
# sts:TagSession is in the Action list because aws-actions/configure-aws-
# credentials@v4 attaches session tags (repo/workflow/actor/branch, etc.)
# to the AssumeRoleWithWebIdentity call by default. STS rejects the ENTIRE
# call -- with the same generic "Not authorized to perform
# sts:AssumeRoleWithWebIdentity" error, not a tagging-specific one -- if
# the trust policy doesn't also allow sts:TagSession. Without this, you'd
# see the exact right OIDC provider, exact right `sub` match, and exact
# right role ARN all still fail.

# Least-privilege for CDK: this role only gets permission to assume the
# CDK bootstrap roles (created by `cdk bootstrap`, already present since
# you've deployed this stack manually before) — not direct AWS service
# permissions. Those bootstrap roles are what actually touch CloudFormation/
# Lambda/S3/etc.
PERMISSIONS_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::${ACCOUNT_ID}:role/cdk-hnb659fds-*"
    }
  ]
}
EOF
)

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "Role $ROLE_NAME already exists — updating its trust policy."
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" --policy-document "$TRUST_POLICY"
else
  echo "Creating role $ROLE_NAME..."
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$TRUST_POLICY" \
    --description "Assumed by GitHub Actions (OIDC) to cdk deploy the Charkha Lifestyle backend"
fi

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "AssumeCdkBootstrapRoles" \
  --policy-document "$PERMISSIONS_POLICY"

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)

echo
echo "Done. Add this as a GitHub Actions secret named AWS_DEPLOY_ROLE_ARN:"
echo "  $ROLE_ARN"
echo
echo "(Settings -> Secrets and variables -> Actions -> New repository secret, in the ${GITHUB_ORG}/${GITHUB_REPO} repo.)"