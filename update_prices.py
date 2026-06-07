import os, re, json, time, statistics, operator, requests
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

def get_listings(soup, floor):
    out = []
    seen = set()
    for a in soup.select('a[href*="/itm/"]'):
        if len(out) >= 3:
            break
        href = a.get("href") or ""
        key = href.split("?")[0]
        if not key or key in seen:
            continue
        cont = None
        node = a
        for _ in range(4):
            node = node.parent
            if node is None:
                break
            if re.search(r"[$][\d,]+\.\d{2}", node.get_text(" ", strip=True)):
                cont = node
                break
        if cont is None:
            continue
        m = re.search(r"[$]([\d,]+\.\d{2})", cont.get_text(" ", strip=True))
        if not m:
            continue
        v = float(m.group(1).replace(",", ""))
        if not (floor < v < 5000):
            continue
        title = a.get_text(strip=True)
        if not title:
            te = cont.select_one(".s-item__title")
            title = te.get_text(strip=True) if te else ""
        title = re.sub(r"[$][\d,]+\.\d{2}.*", "", title)
        title = title.replace("New Listing", "").strip()
        if not title or title.lower() == "shop on ebay":
            continue
        ie = cont.select_one("img")
        img = ""
        if ie:
            img = ie.get("src") or ie.get("data-src") or ""
        seen.add(key)
        out.append({"t": title[:90], "p": round(operator.mul(v, USD_TO_CAD)), "u": href, "img": bigger_img(img)})
    return out

def get_comp(query, floor=10):
    url = "https://www.ebay.com/sch/i.html?_nkw=" + query.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000&_sop=13"
    try:
        resp = requests.get("http://api.scraperapi.com/", params={"api_key": SCRAPER_API_KEY, "url": url, "render": "false"}, timeout=30)
        if resp.status_code != 200:
            return None, []
    except Exception as e:
        print("request failed:", e); return None, []
    soup = BeautifulSoup(resp.text, "html.parser")
    prices = []
    for tag in (soup.select(".s-item__price") or soup.select("[class*=price]") or []):
        m = re.search(r"[$]([\d,]+\.\d{2})", tag.get_text(strip=True).split(" to ")[0])
        if m:
            v = float(m.group(1).replace(",", ""))
            if floor < v < 5000:
                prices.append(v)
    listings = get_listings(soup, floor)
    print(query, "| listings parsed:", len(listings), "| price comps:", len(prices))
    if len(prices) < MIN_COMPS:
        print(query, "- only", len(prices), "comps - holding old price")
        return None, listings
    recent = prices[:12]
    s = sorted(recent)
    if len(s) >= 5:
        s = s[1:-1]
    cad = round(operator.mul(statistics.median(s), USD_TO_CAD), 2)
    print(query, "->", len(recent), "comps, trimmed median CAD", cad)
    return cad, listings

def main():
    with open("data.json") as f:
        data = json.load(f)
    for card in data["holdings"]:
        if card.get("lock"):
            print("skip locked", card["name"]); continue
        price, listings = get_comp(card["query"], card.get("floor", 10))
        staged = False
        if price is not None:
            prev = card.get("now", 0)
            big = prev and (price / prev > BIG_UP or price / prev < BIG_DN)
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
                    staged = True
        if listings and not staged:
            card["listings"] = listings
            if listings[0].get("img"):
                card["img"] = listings[0]["img"]
        time.sleep(1)
    data["updated"] = datetime.utcnow().strftime("%b %d %Y")
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("done")

def log_history():
    d = json.loads(open("data.json").read())
    total = round(sum(h.get("now", 0) for h in d.get("holdings", [])))
    cards = {h.get("name", "").split(" · ")[0].strip(): round(h.get("now", 0)) for h in d.get("holdings", [])}
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
