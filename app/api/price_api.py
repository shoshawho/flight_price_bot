import logging
from datetime import datetime
from typing import Optional

import aiohttp

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _fmt_date(d: str) -> str:
    """Преобразует ДД.ММ.ГГГГ → ГГГГ-ММ-ДД"""
    parts = d.strip().split(".")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return d


async def fetch_price(
    origin_code: str,
    dest_code: str,
    date_from: str,
    token: str,
    passengers: int = 1,
    date_to: str | None = None,
    one_way: bool = False,
    baggage: int = 0,
    transit_code: str | None = None,
    min_layover: int | None = None,
    max_layover: int | None = None,
) -> Optional[float]:
    params = {
        "origin": origin_code,
        "destination": dest_code,
        "departure_at": _fmt_date(date_from),
        "one_way": "true" if one_way else "false",
        "sorting": "price",
        "direct": "false",
        "currency": "rub",
        "limit": 1,
        "token": token,
    }
    if baggage == 1:
        params["baggage"] = "1"
    if date_to and not one_way:
        params["return_at"] = _fmt_date(date_to)

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
        logging.info("Нет цен для %s-%s на %s", origin_code, dest_code, date_from)
        return None

    # Если указана пересадка – фильтруем результаты
    if transit_code:
        filtered = [
            r for r in data
            if _matches_transit(r, transit_code, min_layover, max_layover)
        ]
        if not filtered:
            logging.info(
                "Нет цен с пересадкой через %s для %s-%s",
                transit_code, origin_code, dest_code,
            )
            return None
        data = filtered

    best = data[0]
    price = best.get("price") or best.get("total")
    if price is None:
        return None

    return float(price) * passengers


def _matches_transit(
    route: dict,
    transit_code: str,
    min_layover: int | None,
    max_layover: int | None,
) -> bool:
    segments = route.get("segments") or []
    if not segments:
        return False

    # Проверяем, что есть сегмент с пересадкой в указанном городе
    for i, seg in enumerate(segments[:-1]):
        dest = (seg.get("destination") or "").upper()
        if dest == transit_code.upper():
            if min_layover or max_layover:
                next_seg = segments[i + 1]
                dep_next = _parse_iso(next_seg.get("departure"))
                arr_this = _parse_iso(seg.get("arrival"))
                if dep_next and arr_this:
                    delta = int((dep_next - arr_this).total_seconds() // 60)
                    if min_layover and delta < min_layover:
                        continue
                    if max_layover and delta > max_layover:
                        continue
            return True
    return False


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
