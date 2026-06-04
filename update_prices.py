import os
import re
import json
import time
import statistics
import requests
from bs4 import BeautifulSoup
from datetime import datetime

SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]
USD_TO_CAD = 1.36 # update this value periodically or fetch live if you prefer

def get_comp(query: str) -> float | None:
    """
    Returns the MEDIAN of the 10 most recent eBay SOLD prices for `query`, in CAD.
    Adapted from card-briefing/main.py -> get_ebay_graded_price().
    """
    encoded_query = query.replace(" ", "+")
    ebay_url = (
        "https://www.ebay.com/sch/i.html"
        "?_nkw=" + encoded_query +
        "&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000&_sop=13"
    )
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": ebay_url,
        "render": "false",
    }

    print(f" [{query}] fetching eBay sold listings via ScraperAPI...")
    try:
        resp = requests.get("http://api.scraperapi.com/", params=params, timeout=30)
        print(f" [{query}] status={resp.status_code} len={len(resp.text)}")
        if resp.status_code != 200:
            raise ValueError(f"ScraperAPI returned {resp.status_code}")
    except Exception as e:
        print(f" [WARN] Request failed for '{query}': {e}")
        return None

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    price_elements = (
        soup.select(".s-item__price") or
        soup.select("[class*=price]") or
        soup.select(".item__price") or
        []
    )

    prices_usd = []
    for tag in price_elements:
        text = tag.get_text(strip=True)
        text = text.split(" to ")[0]
        m = re.search(r"[$]([\d,]+\.\d{2})", text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 10 < val < 5000 and val != 20.00:
                prices_usd.append(val)

    if not prices_usd:
        raw_prices = re.findall(r'"soldPrice"\s*:\s*\{[^}]*"value"\s*:\s*"([\d.]+)"', html)
        if not raw_prices:
            raw_prices = re.findall(r'"price"\s*:\s*"([\d.]+)"', html)
        if not raw_prices:
            raw_prices = re.findall(r'US\s*\$([\d,]+\.\d{2})', html)
        for p in raw_prices[:20]:
            try:
                val = float(str(p).replace(",", ""))
                if 10 < val < 5000 and val != 20.00:
                    prices_usd.append(val)
            except Exception:
                pass

    print(f" [{query}] raw USD prices found: {prices_usd[:10]}")

    if not prices_usd:
        print(f" [WARN] No sold comps found for '{query}'")
        return None

    sample = prices_usd[:10]
    median_usd = statistics.median(sample)
    median_cad = round(median_usd * USD_TO_CAD, 2)

    print(f" [{query}] {len(sample)} comps -> median USD ${median_usd:.2f} -> CAD ${median_cad:.2f}")
    return median_cad

def main():
    with open("data.json", "r") as f:
        data = json.load(f)

    for card in data["holdings"]:
        print(f"\nProcessing: {card['name']}")
        price = get_comp(card["query"])
        if price is not None:
            card["prev"] = card["now"]
            card["now"] = price
        else:
            print(f" Keeping existing price: {card['now']}")
        time.sleep(1)

    data["updated"] = datetime.utcnow().strftime("%b %d %Y")

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nOK data.json updated at {datetime.utcnow().isoformat()}Z")

if __name__ == "__main__":
    main()
