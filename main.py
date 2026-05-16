import os
from dotenv import load_dotenv
load_dotenv()

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
