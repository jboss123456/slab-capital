import os, re, json, time, statistics, requests
from bs4 import BeautifulSoup
from datetime import datetime

SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]
USD_TO_CAD = 1.36
MIN_COMPS = 3
BIG_UP = 1.5
BIG_DN = 0.6
CONFIRM_TOL = 0.20

def _bigger_img(u):
    return re.sub(r"s-l\d+", "s-l500", u) if u else u

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
    listings = []
    for it in soup.select("li.s-item, div.s-item"):
        if len(listings) >= 3:
            break
        pe = it.select_one(".s-item__price")
        te = it.select_one(".s-item__title")
        le = it.select_one("a.s-item__link")
        if not (pe and te and le):
            continue
        m = re.search(r"[$]([\d,]+\.\d{2})", pe.get_text(strip=True).split(" to ")[0])
        if not m:
            continue
        v = float(m.group(1).replace(",", ""))
        if not (floor < v < 5000):
            continue
        title = te.get_text(strip=True).replace("New Listing", "").strip()
        if not title or title.lower() == "shop on ebay":
            continue
        ie = it.select_one(".s-item__image img") or it.select_one("img")
        img = ""
        if ie:
            img = ie.get("src") or ie.get("data-src") or ""
        listings.append({"t": title[:90], "p": round(v * USD_TO_CAD), "u": le.get("href") or "", "img": _bigger_img(img)})
    if len(prices) < MIN_COMPS:
        print(query, "- only", len(prices), "comps - holding old price")
        return None
    recent = prices[:12]
    s = sorted(recent)
    if len(s) >= 5:
        s = s[1:-1]
    cad = round(statistics.median(s) * USD_TO_CAD, 2)
    print(query, "->", len(recent), "comps, trimmed median CAD", cad, "| listings:", len(listings))
    return cad, listings

def main():
    with open("data.json") as f:
        data = json.load(f)
    for card in data["holdings"]:
        if card.get("lock"):
            print("skip locked", card["name"]); continue
        result = get_comp(card["query"], card.get("floor", 10))
        if result is not None:
            price, listings = result
            prev = card.get("now", 0)
            big = prev and (price > prev * BIG_UP or price < prev * BIG_DN)
            accepted = False
            if not big:
                card["prev"] = card["now"]; card["now"] = price; card.pop("pending", None); accepted = True
            else:
                pend = card.get("pending")
                if pend and abs(price - pend) / pend <= CONFIRM_TOL:
                    print("CONFIRMED big move", card["name"], prev, "->", price)
                    card["prev"] = card["now"]; card["now"] = price; card.pop("pending", None); accepted = True
                else:
                    card["pending"] = round(price, 2)
                    print("STAGED big move", card["name"], prev, "->", price, "(awaiting confirmation next run)")
            if accepted and listings:
                card["listings"] = listings
                if listings[0].get("img"):
                    card["img"] = listings[0]["img"]
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
