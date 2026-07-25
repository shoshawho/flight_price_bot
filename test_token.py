import json, urllib.request
t = "d8503486f89dfe15ad6ee484a12f6ec8"
url = f"https://api.travelpayouts.com/aviasales/v3/prices_for_dates?origin=MOW&destination=BKK&departure_at=2026-08-20&return_at=2026-08-27&one_way=false&sorting=price&currency=rub&limit=1&token={t}"
try:
    r = json.load(urllib.request.urlopen(url, timeout=15))
    if r.get("data"): print("OK, цена:", r["data"][0].get("price"))
    else: print("Нет данных:", json.dumps(r, ensure_ascii=False)[:300])
except Exception as e: print(f"Ошибка: {e}")
