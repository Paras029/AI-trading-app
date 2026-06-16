from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import engine, Base
from app.db import models   # noqa: F401 — ensure models are registered
from app.core import redis_client
from app.tasks.runner import start_all, stop_all
from app.services.knowledge_seeder import seed_knowledge_base
from app.services.strategy_engine import seed_strategies
from app.db.session import AsyncSessionLocal
from app.routers import ws, overview, positions, episodes, evolution, strategies, world, lessons, trades
from app.routers.settings import router as settings_router, costs_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("apex_trading_bot_starting")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed knowledge base + strategies for all markets
    async with AsyncSessionLocal() as db:
        await seed_knowledge_base(db)
        for market in ["crypto", "us_stocks", "india_stocks", "forex"]:
            await seed_strategies(db, market)

    # Start background tasks
    await start_all()
    log.info("apex_trading_bot_ready")

    yield

    log.info("apex_trading_bot_stopping")
    await stop_all()
    await redis_client.close_pool()


app = FastAPI(
    title="Apex Trading Bot",
    version="1.0.0",
    description="Self-evolving AI trading bot — simulation on real live prices",
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
app.include_router(overview.router)
app.include_router(positions.router)
app.include_router(episodes.router)
app.include_router(evolution.router)
app.include_router(strategies.router)
app.include_router(world.router)
app.include_router(lessons.router)
app.include_router(trades.router)
app.include_router(settings_router)
app.include_router(costs_router)


@app.get("/health")
async def health():
    return {"status": "ok", "bot": "Apex Trading Bot v1"}
