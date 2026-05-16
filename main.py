from fastapi import FastAPI
from api.routes import router

app = FastAPI(
    title="Supplier Due Diligence Agent",
    description="Autonomous supplier research — sanctions, registry, LkSG/CSDDD, ESG, Hermes intelligence.",
    version="0.1.0",
)

app.include_router(router)
