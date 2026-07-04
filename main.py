import logging
import os
from dotenv import load_dotenv
load_dotenv()

# Minimal structured logging so errors are observable in Railway logs
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from fastapi import FastAPI
from api.routes import router

_REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "SERPER_API_KEY",
    "NEWSAPI_KEY",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
]

missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

app = FastAPI(
    title="Hades — Supplier Due Diligence Agent",
    description="Autonomous supplier vetting — sanctions, registry, LkSG/CSDDD, ESG, and Hermes intelligence. Part of the SpendLens procurement stack.",
    version="0.1.0",
)

app.include_router(router)


# No CORS middleware on purpose: the API is consumed server-to-server (Icarus/
# SpendLens), and without CORS headers browsers cannot read cross-origin
# responses — the safest default for an unauthenticated API.
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
