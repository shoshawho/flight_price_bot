import logging
from pathlib import Path

import aiosqlite

DB_DIR = Path("data")
DB_PATH = DB_DIR / "flights.db"


async def init_db() -> None:
    DB_DIR.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
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
                FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
            )
        """)

        for col in ("baggage",):
            try:
                await db.execute(f"ALTER TABLE routes ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            except aiosqlite.OperationalError:
                pass

        await db.commit()
        logging.info("База данных инициализирована")


def get_db() -> aiosqlite.Connection:
    return aiosqlite.connect(DB_PATH)
