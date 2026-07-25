import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg

SQLITE_PATH = Path("data") / "flights.db"
_pool: asyncpg.Pool | None = None
_use_pg = False

_RE_DOLLAR = re.compile(r"\$(\d+)")


def _sqlite_sql(sql: str, args: tuple) -> tuple[str, tuple]:
    """Преобразует $1, $2 -> ? и переставляет args в порядке номеров."""
    order = [int(m) for m in _RE_DOLLAR.findall(sql)]
    sql = _RE_DOLLAR.sub("?", sql)
    ordered = tuple(args[i - 1] for i in order) if order else args
    return sql, ordered


class _ConnWrapper:
    """Единый интерфейс для asyncpg и aiosqlite."""

    def __init__(self, conn) -> None:
        self._c = conn
        self._is_pg = not isinstance(conn, aiosqlite.Connection)

    async def execute(self, sql: str, *args: Any) -> Any:
        if self._is_pg:
            return await self._c.execute(sql, *args)
        sql, args = _sqlite_sql(sql, args)
        return await self._c.execute(sql, args)

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        if self._is_pg:
            return await self._c.fetch(sql, *args)
        sql, args = _sqlite_sql(sql, args)
        cur = await self._c.execute(sql, args)
        return await cur.fetchall()

    async def fetchrow(self, sql: str, *args: Any) -> Any | None:
        if self._is_pg:
            return await self._c.fetchrow(sql, *args)
        sql, args = _sqlite_sql(sql, args)
        cur = await self._c.execute(sql, args)
        return await cur.fetchone()

    async def fetchval(self, sql: str, *args: Any) -> Any | None:
        if self._is_pg:
            return await self._c.fetchval(sql, *args)
        sql, args = _sqlite_sql(sql, args)
        cur = await self._c.execute(sql, args)
        row = await cur.fetchone()
        return row[0] if row else None


async def init_db(database_url: str) -> None:
    global _pool, _use_pg

    if database_url == "sqlite" or not database_url:
        _use_pg = False
        Path("data").mkdir(exist_ok=True)
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    last_price REAL,
                    passengers INTEGER NOT NULL DEFAULT 1,
                    baggage INTEGER NOT NULL DEFAULT 0,
                    notify_hour INTEGER DEFAULT 10,
                    last_checked TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_id INTEGER NOT NULL,
                    origin TEXT NOT NULL,
                    origin_code TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    dest_code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    transit_code TEXT,
                    transit_name TEXT,
                    min_layover INTEGER,
                    max_layover INTEGER,
                    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
                )
            """)
            await db.commit()
        logging.info("База данных инициализирована (SQLite)")
        return

    _use_pg = True
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                last_price DOUBLE PRECISION,
                passengers INTEGER NOT NULL DEFAULT 1,
                baggage INTEGER NOT NULL DEFAULT 0,
                notify_hour INTEGER DEFAULT 10,
                last_checked TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                id SERIAL PRIMARY KEY,
                route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
                origin TEXT NOT NULL,
                origin_code TEXT NOT NULL,
                destination TEXT NOT NULL,
                dest_code TEXT NOT NULL,
                date TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                transit_code TEXT,
                transit_name TEXT,
                min_layover INTEGER,
                max_layover INTEGER
            )
        """)
        logging.info("База данных инициализирована (PostgreSQL)")


@asynccontextmanager
async def get_db():
    if _use_pg:
        if _pool is None:
            raise RuntimeError("Database pool not initialized")
        async with _pool.acquire() as conn:
            yield _ConnWrapper(conn)
    else:
        async with aiosqlite.connect(SQLITE_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            yield _ConnWrapper(conn)
