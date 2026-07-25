import logging
from collections import Counter
from typing import Optional

import aiohttp

CITIES_URL = "https://api.travelpayouts.com/data/ru/cities.json"
_name_cache: dict[str, str] | None = None
_countries_cache: dict[str, str] | None = None


async def _load_cities() -> tuple[dict[str, str], dict[str, str]]:
    global _name_cache, _countries_cache
    if _name_cache is not None and _countries_cache is not None:
        return _name_cache, _countries_cache

    async with aiohttp.ClientSession() as session:
        async with session.get(CITIES_URL, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Не удалось загрузить города: HTTP {resp.status}")
            raw = await resp.json()

    _name_cache = {}
    country_codes: dict[str, list[str]] = {}

    for city in raw:
        name: str = city.get("name") or city.get("city_name", "")
        code: str = city.get("code", "")
        country_name: str = city.get("country_name", "")
        if name and code:
            _name_cache[name.lower().strip()] = code
            if city.get("city_case"):
                _name_cache[city["city_case"].lower().strip()] = code
        if country_name and code:
            cn = country_name.lower().strip()
            country_codes.setdefault(cn, []).append(code)

    _countries_cache = {}
    for cn, codes in country_codes.items():
        most_common = Counter(codes).most_common(1)[0][0]
        _countries_cache[cn] = most_common

    logging.info("Загружено %d городов, %d стран", len(_name_cache), len(_countries_cache))
    return _name_cache, _countries_cache


async def resolve_city(name: str) -> Optional[str]:
    names, countries = await _load_cities()
    key = name.lower().strip()

    code = names.get(key)
    if code:
        return code

    code = countries.get(key)
    if code:
        logging.info("'%s' найден как страна → аэропорт %s", name, code)
        return code

    matches = {k: v for k, v in names.items() if key in k}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        logging.warning("Несколько кандидатов для '%s': %s", name, list(matches.keys()))

    return None


async def clear_cache() -> None:
    global _name_cache, _countries_cache
    _name_cache = None
    _countries_cache = None
