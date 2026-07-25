import logging
from typing import Optional

import aiohttp

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


async def fetch_price(
    origin_code: str,
    dest_code: str,
    date_from: str,
    date_to: str,
    token: str,
    passengers: int = 1,
) -> Optional[float]:
    params = {
        "origin": origin_code,
        "destination": dest_code,
        "departure_at": date_from,
        "return_at": date_to,
        "one_way": "false",
        "sorting": "price",
        "direct": "false",
        "currency": "rub",
        "limit": 1,
        "token": token,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=params, timeout=15) as resp:
                if resp.status != 200:
                    logging.error("API вернул %d: %s", resp.status, await resp.text())
                    return None
                body = await resp.json()
    except (aiohttp.ClientError, TimeoutError) as e:
        logging.error("Ошибка запроса к Aviasales API: %s", e)
        return None

    data = body.get("data") or []
    if not data:
        logging.info("Нет цен для %s-%s на %s..%s", origin_code, dest_code, date_from, date_to)
        return None

    best = data[0]
    price = best.get("price") or best.get("total")
    if price is None:
        return None

    return float(price) * passengers
