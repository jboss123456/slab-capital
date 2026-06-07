import os, re, json, time, statistics, requests
from bs4 import BeautifulSoup
from datetime import datetime

SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]
USD_TO_CAD = 1.36
MIN_COMPS = 3
BIG_UP = 1.5
BIG_DN = 0.6
CONFIRM_TOL = 0.20

def get_comp(query, floor=10):
    url = "https://www.ebay.com/sch/i.html?_nkw=" + query.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000&_sop=13"
    try:
        resp = requests.get("http://api.scraperapi.com/", params={"api_key": SCRAPER_API_KEY, "url": url, "render": "false"}, timeout=30)
        if resp.status_code != 200:
            return None
    except Exception as e:
        print("request failed:", e); return None
    soup = BeautifulSoup(resp.text, "html.parser")
    prices = []
    for tag in (soup.select(".s-item__price") or soup.select("[class*=price]") or []):
        m = re.search(r"[$]([\d,]+\.\d{2})", tag.get_text(strip=True).split(" to ")[0])
        if m:
            v = float(m.group(1).replace(",", ""))
            if floor < v < 5000:
                prices.append(v)
    if len(prices) < MIN_COMPS:
        print(query, "- only", len(prices), "comps - holding old price")
        return None
    recent = prices[:12]
    s = sorted(recent)
    if len(s) >= 5:
        s = s[1:-1]
    cad = round(statistics.median(s) * USD_TO_CAD, 2)
    print(query, "->", len(recent), "comps, trimmed median CAD", cad)
    return cad

def main():
    with open("data.json") as f:
        data = json.load(f)
    for card in data["holdings"]:
        if card.get("lock"):
            print("skip locked", card["name"]); continue
        price = get_comp(card["query"], card.get("floor", 10))
        if price is not None:
            prev = card.get("now", 0)
            big = prev and (price > prev * BIG_UP or price < prev * BIG_DN)
            if not big:
                card["prev"] = card["now"]; card["now"] = price; card.pop("pending", None)
            else:
                pend = card.get("pending")
                if pend and abs(price - pend) / pend <= CONFIRM_TOL:
                    print("CONFIRMED big move", card["name"], prev, "->", price)
                    card["prev"] = card["now"]; card["now"] = price; card.pop("pending", None)
                else:
                    card["pending"] = round(price, 2)
                    print("STAGED big move", card["name"], prev, "->", price, "(awaiting confirmation next run)")
        time.sleep(1)
    data["updated"] = datetime.utcnow().strftime("%b %d %Y")
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("done")

def log_history():
    import json, datetime, pathlib
    p = pathlib.Path(__file__).parent / "data.json"
    d = json.loads(p.read_text())
    total = round(sum(h.get("now", 0) for h in d.get("holdings", [])))
    cards = {h.get("name", "").split(" · ")[0].strip(): round(h.get("now", 0)) for h in d.get("holdings", [])}
    today = datetime.date.today().strftime("%b %d %Y")
    hist = d.get("history", [])
    entry = {"d": today, "v": total, "cards": cards}
    if hist and hist[-1].get("d") == today:
        hist[-1] = entry
    else:
        hist.append(entry)
    d["history"] = hist
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    print("logged history", today, total)

if __name__ == "__main__":
    main()
    log_history()
