from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import engine, Base, AsyncSessionLocal
from app.db import models   # noqa: F401 — ensure models are registered
from app.db.cleanup_legacy_tables import drop_legacy_tables
from app.core import redis_client
from app.tasks.runner import start_all, stop_all
from app.services.knowledge_seeder import seed_knowledge_base
from app.routers import (
    ws, dashboard, scanner, research, prediction, risk, postmortem, trades,
)
from app.routers.settings import router as settings_router, costs_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("apex_trading_bot_starting")

    # Drop legacy (pre-rewrite) tables, then create the current schema.
    async with engine.begin() as conn:
        await drop_legacy_tables(conn)
        await conn.run_sync(Base.metadata.create_all)

    # Seed the knowledge base with domain-general risk-discipline frameworks.
    async with AsyncSessionLocal() as db:
        await seed_knowledge_base(db)

    # Initialise bot config — write defaults only if absent, never clobber a live operator's
    # edits, and never let live_armed default to anything but False.
    from app.config import DEFAULT_BOT_CONFIG
    existing = await redis_client.get_json("bot:config")
    if not existing:
        await redis_client.set_json("bot:config", dict(DEFAULT_BOT_CONFIG))
        log.info("bot_config_initialised")
    elif "live_armed" not in existing:
        existing["live_armed"] = False
        await redis_client.set_json("bot:config", existing)

    # Start background tasks (5-stage pipeline + WS Redis listener)
    await start_all()
    log.info("apex_trading_bot_ready")

    yield

    log.info("apex_trading_bot_stopping")
    await stop_all()
    await redis_client.close_pool()


app = FastAPI(
    title="Apex Prediction Bot",
    version="2.0.0",
    description="Self-evolving multi-agent AI bot — paper/live trading on Polymarket prediction markets",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002", "http://127.0.0.1:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(ws.router)
app.include_router(dashboard.router)
app.include_router(scanner.router)
app.include_router(research.router)
app.include_router(prediction.router)
app.include_router(risk.router)
app.include_router(postmortem.router)
app.include_router(trades.router)
app.include_router(settings_router)
app.include_router(costs_router)


@app.get("/health")
async def health():
    return {"status": "ok", "bot": "Apex Prediction Bot v2"}
