"""
Lambda entry point. Deployed behind a Function URL (no API Gateway) so the
whole backend stays on Lambda's Always Free allowance — see the
architecture blueprint for why that distinction matters:
https://claude.ai/code/artifact/12f6ab68-e085-4a6e-a121-054fd3b25b0a
"""

from mangum import Mangum

from app.main import app

handler = Mangum(app)
