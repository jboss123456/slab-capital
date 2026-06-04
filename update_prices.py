import os, re, json, time, statistics, requests
from bs4 import BeautifulSoup
from datetime import datetime

SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]
USD_TO_CAD = 1.36

def get_comp(query, floor=10):
    url = "https://www.ebay.com/sch/i.html?_nkw=" + query.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000&_sop=13"
    try:
        resp = requests.get("http://api.scraperapi.com/", params={"api_key": SCRAPER_API_KEY, "url": url, "render": "false"}, timeout=30)
        if resp.status_code != 200:
            return None
    except Exception as e:
        print("request failed:", e); return None
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    prices = []
    for tag in (soup.select(".s-item__price") or soup.select("[class*=price]") or []):
        m = re.search(r"[$]([\d,]+\.\d{2})", tag.get_text(strip=True).split(" to ")[0])
        if m:
            v = float(m.group(1).replace(",", ""))
            if floor < v < 5000:
                prices.append(v)
    if not prices:
        for p in re.findall(r'US\s*\$([\d,]+\.\d{2})', html)[:30]:
            try:
                v = float(p.replace(",", ""))
                if floor < v < 5000: prices.append(v)
            except: pass
    if not prices:
        print("no comps above floor for", query); return None
    cad = round(statistics.median(prices[:10]) * USD_TO_CAD, 2)
    print(query, "->", len(prices[:10]), "comps -> CAD", cad)
    return cad

def main():
    with open("data.json") as f:
        data = json.load(f)
    for card in data["holdings"]:
        if card.get("lock"):
            print("skip locked", card["name"]); continue
        price = get_comp(card["query"], card.get("floor", 10))
        if price is not None:
            card["prev"] = card["now"]; card["now"] = price
        time.sleep(1)
    data["updated"] = datetime.utcnow().strftime("%b %d %Y")
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("done")

if __name__ == "__main__":
    main()
