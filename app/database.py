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

        for migration in (
            "CREATE TABLE IF NOT EXISTS routes_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, last_price REAL, passengers INTEGER NOT NULL DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users(id))",
            "INSERT OR IGNORE INTO routes_v2 SELECT id, user_id, last_price, passengers FROM routes",
            "CREATE TABLE IF NOT EXISTS segments (id INTEGER PRIMARY KEY AUTOINCREMENT, route_id INTEGER NOT NULL, origin TEXT NOT NULL, origin_code TEXT NOT NULL, destination TEXT NOT NULL, dest_code TEXT NOT NULL, date TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE)",
        ):
            try:
                await db.execute(migration)
            except aiosqlite.OperationalError:
                pass

        await db.commit()
        logging.info("База данных инициализирована")


def get_db() -> aiosqlite.Connection:
    return aiosqlite.connect(DB_PATH)
