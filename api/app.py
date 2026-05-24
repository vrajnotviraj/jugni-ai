from fastapi import FastAPI

from api.lifespan import lifespan
from api.routes import backfill, health, summary, telegram_webhook, upload

app = FastAPI(title="Food Summary Bot", lifespan=lifespan)

app.include_router(health.router)
app.include_router(telegram_webhook.router)
app.include_router(upload.router)
app.include_router(summary.router)
app.include_router(backfill.router)
