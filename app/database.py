import aiosqlite

DB_PATH = "data/flights.db"


async def init_db() -> None:
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
                origin TEXT NOT NULL,
                origin_code TEXT NOT NULL,
                destination TEXT NOT NULL,
                dest_code TEXT NOT NULL,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                passengers INTEGER NOT NULL DEFAULT 1,
                last_price REAL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.commit()


def get_db() -> aiosqlite.Connection:
    return aiosqlite.connect(DB_PATH)
