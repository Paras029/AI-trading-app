"""One-time startup cleanup: drop tables from the old technical-indicator episode-trading
architecture that have no replacement mapping in the new prediction-market schema.

There are no Alembic migrations in active use for this project (schema is managed via
`Base.metadata.create_all` in `main.py`'s lifespan), so this is a plain DROP TABLE step
rather than a migration. Since there's no production data worth preserving across this
rewrite, we just drop the old tables outright.

NOT wired into main.py yet — whoever wires this up should call:

    async with engine.begin() as conn:
        await drop_legacy_tables(conn)
        await conn.run_sync(Base.metadata.create_all)

i.e. call `drop_legacy_tables(conn)` BEFORE `create_all`, using the same connection/engine
already set up in `app.db.session`.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = structlog.get_logger()

# Real __tablename__ values from the deleted model files (verified before deletion):
#   episode.py   -> Episode    -> "episodes"
#   generation.py -> Generation -> "generations"
#   strategy.py  -> Strategy   -> "strategies"
#   lesson.py    -> Lesson     -> "lessons"
#   signal.py    -> AISignal   -> "ai_signals"
#   position.py  -> Position   -> "positions"
LEGACY_TABLES = [
    "episodes",
    "generations",
    "strategies",
    "lessons",
    "ai_signals",
    "positions",
]


async def drop_legacy_tables(conn: AsyncConnection) -> None:
    """Drops all legacy tables from the old episode/strategy/indicator architecture.

    Safe to call repeatedly (uses IF EXISTS) and safe on a fresh DB with no legacy tables.
    Must be called inside an `engine.begin()` transaction, before `Base.metadata.create_all`.
    """
    for table_name in LEGACY_TABLES:
        logger.info("dropping_legacy_table", table=table_name)
        await conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
