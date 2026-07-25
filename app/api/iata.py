import logging
from typing import Optional

import aiohttp

CITIES_URL = "https://api.travelpayouts.com/data/ru/cities.json"
_cache: dict[str, str] | None = None


async def _load_cities() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache

    async with aiohttp.ClientSession() as session:
        async with session.get(CITIES_URL, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Не удалось загрузить города: HTTP {resp.status}")
            data = await resp.json()

    _cache = {}
    for city in data:
        name: str = city.get("name") or city.get("city_name", "")
        code: str = city.get("code", "")
        if name and code:
            _cache[name.lower().strip()] = code
            if city.get("city_case"):
                _cache[city["city_case"].lower().strip()] = code
    logging.info("Загружено %d городов", len(_cache))
    return _cache


async def resolve_city(name: str) -> Optional[str]:
    cities = await _load_cities()
    key = name.lower().strip()
    code = cities.get(key)
    if code:
        return code

    matches = {k: v for k, v in cities.items() if key in k}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        logging.warning("Несколько кандидатов для '%s': %s", name, list(matches.keys()))
    return None


async def clear_cache() -> None:
    global _cache
    _cache = None
