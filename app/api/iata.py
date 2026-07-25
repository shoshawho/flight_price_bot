import logging
from collections import Counter
from typing import Optional

import aiohttp

CITIES_URL = "https://api.travelpayouts.com/data/ru/cities.json"
COUNTRIES_URL = "https://api.travelpayouts.com/data/ru/countries.json"
_name_cache: dict[str, str] | None = None
_country_code_cache: dict[str, str] | None = None
_cities_by_country: dict[str, str] | None = None


async def _load_all() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    global _name_cache, _country_code_cache, _cities_by_country
    if _name_cache and _country_code_cache and _cities_by_country:
        return _name_cache, _country_code_cache, _cities_by_country

    async with aiohttp.ClientSession() as session:
        async with session.get(CITIES_URL, timeout=15) as resp:
            cities_raw = await resp.json()
        async with session.get(COUNTRIES_URL, timeout=15) as resp:
            countries_raw = await resp.json()

    _name_cache = {}
    country_airports: dict[str, list[str]] = {}
    for city in cities_raw:
        name = city.get("name") or city.get("city_name", "")
        code = city.get("code", "")
        country_code = city.get("country_code", "")
        if name and code:
            _name_cache[name.lower().strip()] = code
            if city.get("city_case"):
                _name_cache[city["city_case"].lower().strip()] = code
        if country_code and code:
            country_airports.setdefault(country_code.upper(), []).append(code)

    _cities_by_country = {}
    for cc, codes in country_airports.items():
        _cities_by_country[cc] = Counter(codes).most_common(1)[0][0]

    _country_code_cache = {}
    for c in countries_raw:
        country_name = c.get("name", "").lower().strip()
        code = c.get("code", "")
        if country_name and code:
            _country_code_cache[country_name] = code.upper()
        tr = c.get("name_translations", {})
        for lang, tname in tr.items():
            key = tname.lower().strip()
            if key and code:
                _country_code_cache[key] = code.upper()

    logging.info("Загружено %d городов, %d стран",
                 len(_name_cache), len(_country_code_cache))
    return _name_cache, _country_code_cache, _cities_by_country


async def resolve_city(name: str) -> Optional[str]:
    names, country_names, cities_by_country = await _load_all()
    key = name.lower().strip()

    code = names.get(key)
    if code:
        return code

    country_code = country_names.get(key)
    if country_code:
        airport = cities_by_country.get(country_code)
        if airport:
            logging.info("'%s' → страна %s → аэропорт %s", name, country_code, airport)
            return airport

    matches = {k: v for k, v in names.items() if key in k}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        logging.warning("Несколько кандидатов для '%s': %s", name, list(matches.keys()))

    return None


async def clear_cache() -> None:
    global _name_cache, _country_code_cache, _cities_by_country
    _name_cache = None
    _country_code_cache = None
    _cities_by_country = None
