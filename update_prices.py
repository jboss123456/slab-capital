import os, re, json, sys, time, statistics, operator, requests

from bs4 import BeautifulSoup

from datetime import datetime

SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]

USD_TO_CAD = 1.36

MIN_COMPS = 3

BIG_UP = 1.5

BIG_DN = 0.6

CONFIRM_TOL = 0.20

def bigger_img(u):

    return re.sub(r"s-l\d+", "s-l500", u) if u else u

def fetch_one(query, floor, ceil):

    url = "https://www.ebay.com/sch/i.html?_nkw=" + query.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1&_sop=13"

    try:

        resp = requests.get("http://api.scraperapi.com/", params={"api_key": SCRAPER_API_KEY, "url": url, "render": "false", "premium": "true"}, timeout=30)

        if resp.status_code != 200:

            print("  bad status", resp.status_code, "for", query); return []

    except Exception as e:

        print("  request failed:", e); return []

    soup = BeautifulSoup(resp.text, "html.parser")

    items = []

    for it in soup.select(".s-item"):

        pe = it.select_one(".s-item__price")

        if pe is None:

            continue

        m = re.search(r"[$]([\d,]+\.\d{2})", pe.get_text(strip=True).split(" to ")[0])

        if not m:

            continue

        v = float(m.group(1).replace(",", ""))

        if not (floor < v < ceil):

            continue

        te = it.select_one(".s-item__title")

        title = te.get_text(strip=True) if te else ""

        title = title.replace("New Listing", "").strip()

        if not title or title.lower() == "shop on ebay":

            continue

        le = it.select_one("a.s-item__link") or it.select_one('a[href*="/itm/"]')

        link = le.get("href") if le else ""

        ie = it.select_one(".s-item__image img") or it.select_one("img")

        img = ""

        if ie is not None:

            img = ie.get("src") or ie.get("data-src") or ""

        items.append({"t": title[:90], "p": round(operator.mul(v, USD_TO_CAD)), "u": link, "img": bigger_img(img), "usd": v})

    print("  variation:", query, "| qualifying sold items:", len(items))

    return items[:10]

def get_comp(queries, floor=10, ceil=5000):

    pool = []

    for q in queries:

        pool.extend(fetch_one(q, floor, ceil))

        time.sleep(1)

    listings = [{"t": i["t"], "p": i["p"], "u": i["u"], "img": i["img"]} for i in pool[:3]]

    if len(pool) < MIN_COMPS:

        print("  pooled only", len(pool), "comps - holding old price")

        return None, listings

    prices = sorted(i["usd"] for i in pool)

    if len(prices) >= 5:

        cut = max(1, len(prices) // 10)

        prices = prices[cut:len(prices) - cut]

    cad = round(operator.mul(statistics.median(prices), USD_TO_CAD), 2)

    print("  pooled", len(pool), "sold items ->", cad, "CAD (showing", len(listings), "recent)")

    return cad, listings

def main():

    with open("data.json") as f:

        data = json.load(f)

    today = datetime.utcnow().strftime("%b %d %Y")

    if data.get("updated") == today and os.environ.get("GITHUB_EVENT_NAME") == "schedule":

        print("already updated for", today, "- skipping scheduled run")

        sys.exit(0)

    for card in data["holdings"]:

        if card.get("lock"):

            print("skip locked", card["name"]); continue

        qs = card.get("queries") or [card.get("query", "")]

        qs = [q for q in qs if q]

        print("CARD", card["name"])

        price, listings = get_comp(qs, card.get("floor", 10), card.get("ceil", 5000))

        if price is not None:

            prev = card.get("now", 0)

            big = prev and (price / prev > BIG_UP or price / prev < BIG_DN)

            if not big:

                card["prev"] = card["now"]; card["now"] = price; card.pop("pending", None)

            else:

                pend = card.get("pending")

                if pend and abs(price - pend) / pend <= CONFIRM_TOL:

                    print("  CONFIRMED big move", prev, "->", price)

                    card["prev"] = card["now"]; card["now"] = price; card.pop("pending", None)

                else:

                    card["pending"] = round(price, 2)

                    print("  STAGED big move", prev, "->", price)

        if listings:

            card["listings"] = listings

            if listings[0].get("img"):

                card["img"] = listings[0]["img"]

    data["updated"] = datetime.utcnow().strftime("%b %d %Y")

    with open("data.json", "w") as f:

        json.dump(data, f, indent=2, ensure_ascii=False)

    print("done")

def log_history():

    d = json.loads(open("data.json").read())

    total = round(sum(h.get("now", 0) for h in d.get("holdings", [])))

    cards = {h.get("name", "").split(" \u00b7 ")[0].strip(): round(h.get("now", 0)) for h in d.get("holdings", [])}

    today = datetime.today().strftime("%b %d %Y")

    hist = d.get("history", [])

    entry = {"d": today, "v": total, "cards": cards}

    if hist and hist[-1].get("d") == today:

        hist[-1] = entry

    else:

        hist.append(entry)

    d["history"] = hist

    open("data.json", "w").write(json.dumps(d, indent=2, ensure_ascii=False))

    print("logged history", today, total)

main()

log_history()
