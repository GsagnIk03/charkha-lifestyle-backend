"""
Charkha Lifestyle — backend infrastructure (CDK, Python).

Replaces the old AWS SAM template.yaml one-for-one on the AWS side, minus
the frontend hosting: the React app now deploys to Vercel (its own git
push → build → deploy pipeline, free, with its own custom-domain/HTTPS
handling), so there's no FrontendBucket/FrontendDistribution here anymore
— only what Vercel *can't* do: the API, the database, auth, and product
media storage.

Built entirely on AWS's permanent Always Free allowances (no EC2, no RDS,
no API Gateway, no NAT gateway) — see the architecture blueprint:
https://claude.ai/code/artifact/12f6ab68-e085-4a6e-a121-054fd3b25b0a

DynamoDB tables use PROVISIONED billing (not on-demand) on purpose —
on-demand mode has no free tier at all. Provisioned capacity across the
three tables here totals 15 RCU / 15 WCU, comfortably under the 25/25
free allowance shared per account per region. Traffic beyond that
throttles rather than bills — a deliberate trade-off for a hard $0
ceiling at MVP scale.

RemovalPolicy.DESTROY is used everywhere below (tables, buckets, the user
pool) rather than CDK's stateful-resource default of RETAIN. That's a
dev-stage choice, not an oversight: this stack gets torn down and rebuilt
while iterating, and a RETAINed table/bucket left behind after `cdk
destroy` still burns into the same account-wide free-tier ceiling this
whole design leans on. Revisit this (RETAIN, backups) before a `prod`
stage ever holds real customer data.
"""

from __future__ import annotations

import os
import time

from aws_cdk import CfnOutput, CustomResource, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import custom_resources as cr
from aws_cdk.aws_lambda_python_alpha import BundlingOptions, PythonFunction
from constructs import Construct

# The repo root — one level up from infra/ — is what gets pip-installed and
# zipped for the Lambda. lambda_handler.py and requirements.txt both live
# there; app/ is the FastAPI package they import.
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


class CharkhaStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        stage: str,
        allowed_origin: str,
        google_client_id: str = "",
        google_client_secret: str = "",
        razorpay_key_id: str = "",
        razorpay_key_secret: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # allowed_origin may be a single origin or a comma-separated list
        # (e.g. both the apex and www domains). The FastAPI app reads the
        # raw comma-joined string itself (ALLOWED_ORIGINS env var below) and
        # splits it in Python, but every AWS-native "allowed origins" list
        # (Lambda Function URL CORS, S3 bucket CORS, Cognito callback/logout
        # URLs) needs an actual list of individually-valid origins — passing
        # the whole joined string as a single list entry fails deploy with
        # "isn't a valid origin" the moment more than one origin is
        # configured, since AWS itself never splits on commas for you.
        allowed_origins = [o.strip() for o in allowed_origin.split(",") if o.strip()]

        # ---------- Database (provisioned, not on-demand — see module docstring) ----------

        products_table = dynamodb.Table(
            self,
            "ProductsTable",
            table_name=f"CharkhaLifestyle-Products-{stage}",
            partition_key=dynamodb.Attribute(name="product_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=5,
            write_capacity=5,
            removal_policy=RemovalPolicy.DESTROY,
        )

        inventory_requests_table = dynamodb.Table(
            self,
            "InventoryChangeRequestsTable",
            table_name=f"CharkhaLifestyle-InventoryChangeRequests-{stage}",
            partition_key=dynamodb.Attribute(name="request_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=5,
            write_capacity=5,
            removal_policy=RemovalPolicy.DESTROY,
        )

        orders_table = dynamodb.Table(
            self,
            "OrdersTable",
            table_name=f"CharkhaLifestyle-Orders-{stage}",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=5,
            write_capacity=5,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---------- Product catalog seed ----------
        # Runs as part of `cdk deploy` itself — locally or via CI, same
        # stack either way — not as a separate script anyone has to
        # remember to run. See infra/seed_products_lambda/index.py for the
        # "only seed an empty table" safety logic that makes it safe to
        # run on every single deploy, forever, without risking an owner's
        # real edits made through the dashboard.

        seed_products_lambda = _lambda.Function(
            self,
            "SeedProductsFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset(os.path.join(REPO_ROOT, "infra", "seed_products_lambda")),
            timeout=Duration.seconds(60),
            # AWS_REGION is deliberately not set here — it's a reserved
            # Lambda environment variable name (Lambda sets it
            # automatically; CloudFormation rejects trying to override it
            # yourself). index.py reads it via os.environ at runtime.
            environment={"PRODUCTS_TABLE": products_table.table_name},
        )
        products_table.grant_read_write_data(seed_products_lambda)

        seed_products_provider = cr.Provider(
            self,
            "SeedProductsProvider",
            on_event_handler=seed_products_lambda,
        )

        CustomResource(
            self,
            "SeedProductsResource",
            service_token=seed_products_provider.service_token,
            properties={
                # Custom resources only get re-invoked when their own
                # properties change — without this, CloudFormation would
                # run the seed Lambda once on the very first deploy and
                # then never again, even though the handler itself is
                # cheap/safe to call every time. A fresh value on every
                # synth forces an event on every deploy; the handler's own
                # "already has items? skip" check is what actually makes
                # that safe.
                "Timestamp": str(time.time()),
            },
        )

        # ---------- Auth ----------

        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"charkha-lifestyle-{stage}",
            # self_sign_up_enabled=True matches plain CloudFormation's default
            # (AdminCreateUserConfig.AllowAdminCreateUserOnly: false) — CDK's own
            # construct default is the opposite (admin-create-only), so this has
            # to be set explicitly to keep the same signup behaviour as before.
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True)
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_digits=True,
                require_symbols=False,
                require_uppercase=True,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        cognito.CfnUserPoolGroup(
            self,
            "UserPoolOwnersGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="owners",
            description=(
                "Members can approve/reject inventory change requests. "
                "Add the store owner's account here manually after signup."
            ),
        )

        user_pool_domain = user_pool.add_domain(
            "UserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"charkha-lifestyle-{stage}-{self.account}"),
        )

        # Google sign-in is optional — only created if google_client_id is
        # supplied (via infra/.env, see infra/README.md). Get these from
        # Google Cloud Console > APIs & Services > Credentials, with the
        # Cognito domain's redirect URI
        # (<user_pool_domain>/oauth2/idpresponse) registered there first —
        # that domain only exists after the *first* deploy, so: deploy once
        # without Google, register the redirect URI, then redeploy with
        # these set.
        has_google_idp = bool(google_client_id)
        supported_identity_providers = [cognito.UserPoolClientIdentityProvider.COGNITO]
        google_idp = None
        if has_google_idp:
            google_idp = cognito.UserPoolIdentityProviderGoogle(
                self,
                "UserPoolIdentityProviderGoogle",
                user_pool=user_pool,
                client_id=google_client_id,
                client_secret=google_client_secret,
                scopes=["email", "openid", "profile"],
                attribute_mapping=cognito.AttributeMapping(email=cognito.ProviderAttribute.GOOGLE_EMAIL),
            )
            supported_identity_providers.append(cognito.UserPoolClientIdentityProvider.GOOGLE)

        user_pool_client = user_pool.add_client(
            "UserPoolClient",
            user_pool_client_name=f"charkha-lifestyle-web-{stage}",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.EMAIL, cognito.OAuthScope.OPENID, cognito.OAuthScope.PROFILE],
                callback_urls=allowed_origins,
                logout_urls=allowed_origins,
            ),
            supported_identity_providers=supported_identity_providers,
        )
        if google_idp is not None:
            # The client lists Google as a supported IdP by name, not by a real
            # CloudFormation Ref — nothing forces CloudFormation to create the
            # identity provider before the client otherwise, which can 500 the
            # deploy if they land in the wrong order.
            user_pool_client.node.add_dependency(google_idp)

        # ---------- Compute ----------

        api_function = PythonFunction(
            self,
            "ApiFunction",
            entry=REPO_ROOT,
            index="lambda_handler.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "PRODUCTS_TABLE": products_table.table_name,
                "INVENTORY_REQUESTS_TABLE": inventory_requests_table.table_name,
                "ORDERS_TABLE": orders_table.table_name,
                "ALLOWED_ORIGINS": allowed_origin,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_APP_CLIENT_ID": user_pool_client.user_pool_client_id,
                "RAZORPAY_KEY_ID": razorpay_key_id,
                "RAZORPAY_KEY_SECRET": razorpay_key_secret,
            },
            bundling=BundlingOptions(
                # Everything under infra/ (including this CDK app itself,
                # cdk.out/, and .env) has no business in the Lambda zip, and
                # neither do local-dev-only files from the repo root.
                asset_excludes=[
                    "infra",
                    "infra/**",
                    ".git",
                    ".git/**",
                    ".venv",
                    ".venv/**",
                    "**/__pycache__",
                    "**/__pycache__/**",
                    "*.pyc",
                    ".env",
                    "requirements-dev.txt",
                    "local_dev.py",
                    "README.md",
                ],
                # Same fix as the SAM days for a slow/flaky path to PyPI from
                # inside the build container: give pip more than the 15s
                # default before it gives up on a chunk. See "Troubleshooting"
                # in infra/README.md if a build still stalls past this.
                environment={"PIP_DEFAULT_TIMEOUT": "120"},
            ),
        )

        function_url = api_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,  # auth is enforced inside FastAPI via Cognito JWT bearer tokens, not at the URL level
            cors=_lambda.FunctionUrlCorsOptions(
                allowed_origins=allowed_origins,
                # NOT HttpMethod.OPTIONS — CDK's HttpMethod enum happens to
                # list it, but Lambda Function URLs reject it at deploy time
                # ("OPTIONS is not a valid enum value..."). CORS preflight
                # (OPTIONS) is answered automatically at the platform level;
                # it's never something you list as an allowed method here.
                allowed_methods=[
                    _lambda.HttpMethod.GET,
                    _lambda.HttpMethod.POST,
                    _lambda.HttpMethod.PATCH,
                    _lambda.HttpMethod.DELETE,
                ],
                allowed_headers=["content-type", "authorization"],
            ),
        )

        products_table.grant_read_write_data(api_function)
        inventory_requests_table.grant_read_write_data(api_function)
        orders_table.grant_read_write_data(api_function)
        # grant_read_write_data doesn't include TransactWriteItems (same gap
        # DynamoDBCrudPolicy had in the old SAM template) — the approval flow
        # in inventory_requests.py needs it for its two-table transaction.
        api_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:TransactWriteItems"],
                resources=[products_table.table_arn, inventory_requests_table.table_arn],
            )
        )

        # ---------- Product media ----------

        media_bucket = _s3_bucket(self, "MediaBucket", f"charkha-lifestyle-media-{stage}-{self.account}", allowed_origins)

        media_distribution = cloudfront.Distribution(
            self,
            "MediaDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(media_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
        )

        # ---------- Outputs ----------

        CfnOutput(
            self,
            "ApiFunctionUrl",
            value=function_url.url,
            description="Base URL for the backend API — set as VITE_API_BASE_URL in the frontend (on Vercel).",
        )
        CfnOutput(self, "MediaUrl", value=f"https://{media_distribution.distribution_domain_name}")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(
            self,
            "UserPoolHostedUiDomain",
            # Not user_pool_domain.base_url() — it hardcodes us-east-1 into the
            # URL regardless of the stack's actual region (confirmed against
            # this exact CDK version by synthesizing and inspecting the output;
            # not documented anywhere obvious). Building it explicitly with
            # self.region matches the real per-region hosted UI domain format
            # and is what the old SAM template used too.
            value=f"https://{user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
        )


def _s3_bucket(scope: Construct, construct_id: str, bucket_name: str, allowed_origins: list) -> s3.Bucket:
    return s3.Bucket(
        scope,
        construct_id,
        bucket_name=bucket_name,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        cors=[
            s3.CorsRule(
                allowed_origins=allowed_origins,
                allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT],
                allowed_headers=["*"],
            )
        ],
        removal_policy=RemovalPolicy.DESTROY,
        auto_delete_objects=True,
    )