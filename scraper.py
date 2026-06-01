"""
IDBF Bangalore Business Scraper v3
- Removed session warmup (was hanging)
- Uses cloudscraper to bypass Cloudflare/bot detection
- Scrapes name, address, phone from listing pages
"""

import time
import random
import re
import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

BASE_URL = "https://bangalore.idbf.in"

CATEGORY_SLUGS = [
    "gym",
    "beauty-parlour",
    "school",
    "hospitals",
    "hotels",
    "restaurants",
    "blood-banks",
    "pharmacy",
    "clinic",
    "dentist",
    "bakery",
    "supermarket",
    "hardware",
    "plumber",
    "tailors",
    "computer",
    "electrical",
    "library",
    "plywood",
    "maths-academy",
]

MAX_PAGES  = 10
DELAY_MIN  = 3.0
DELAY_MAX  = 6.0

OUTPUT_CSV   = "idbf_businesses.csv"
OUTPUT_EXCEL = "idbf_businesses.xlsx"

# ── SCRAPER SETUP ─────────────────────────────────────────────────────────────

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

def get_page(url, retries=4):
    for attempt in range(retries):
        try:
            print(f"    Fetching (attempt {attempt+1}): {url}")
            r = scraper.get(url, timeout=20)
            print(f"    Status: {r.status_code}")
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            elif r.status_code == 404:
                return None
            elif r.status_code in (500, 429, 503):
                wait = 20 * (attempt + 1)
                print(f"    HTTP {r.status_code} — waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    HTTP {r.status_code} — skipping")
                return None
        except Exception as e:
            print(f"    Error: {e} — waiting 10s...")
            time.sleep(10)
    return None

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def extract_phone(text):
    nums = re.findall(r"[6-9]\d{9}", text)
    return nums[0] if nums else ""

def parse_listing(soup, category):
    records = []

    # Try common listing containers
    items = (
        soup.select("ul li") or
        soup.select(".listing li") or
        soup.select(".business-list li") or
        soup.select("table tr") or
        []
    )

    for item in items:
        text = item.get_text(separator=" ")
        phone = extract_phone(text)
        if not phone:
            continue  # Skip items with no phone — likely nav/footer junk

        # Name: first link or heading text
        name = ""
        for sel in ["a", "h2", "h3", "strong", "b"]:
            el = item.select_one(sel)
            if el and len(el.get_text(strip=True)) > 2:
                name = clean(el.get_text())
                break

        # Address: look for Bangalore/locality keywords
        address = ""
        addr_match = re.search(
            r"((?:No|#)?\s*[\w\s,/\-\.]+(?:Road|Layout|Nagar|Stage|Main|Cross|Street|Colony|Block|Circle|Bangalore)[^\n]{0,80})",
            text, re.I
        )
        if addr_match:
            address = clean(addr_match.group(1))

        if name:
            records.append({
                "Business Name": name,
                "Address": address,
                "Phone": phone,
                "Category": category,
            })

    return records

def parse_biz_links(soup):
    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if re.search(r"/\d{5,}/", href):
            full = href if href.startswith("http") else BASE_URL + href
            if full not in links:
                links.append(full)
    return links

def parse_biz_detail(soup, url, category):
    d = {"Business Name": "", "Address": "", "Phone": "", "Category": category}
    for sel in ["h1", ".biz-name", "h2"]:
        el = soup.select_one(sel)
        if el:
            d["Business Name"] = clean(el.get_text()); break

    text = soup.get_text()
    addr = re.search(
        r"(?:Address|Location)\s*[:\-–]?\s*([^\n]{10,120})", text, re.I
    )
    if addr:
        d["Address"] = clean(addr.group(1))

    tel = soup.select_one("a[href^='tel:']")
    if tel:
        d["Phone"] = clean(tel["href"].replace("tel:", ""))
    if not d["Phone"]:
        d["Phone"] = extract_phone(text)

    return d

def has_next(soup):
    for a in soup.select("a"):
        txt = a.get_text(strip=True).lower()
        if txt in ("next", "»", ">", "next page", "next »"):
            return True
    return False

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    all_records = []
    start = datetime.now()

    for slug in CATEGORY_SLUGS:
        print(f"\n{'='*55}")
        print(f"  Category: {slug}")
        print(f"{'='*55}")
        cat_count = 0

        for page_num in range(1, MAX_PAGES + 1):
            url = (
                f"{BASE_URL}/{slug}"
                if page_num == 1
                else f"{BASE_URL}/{slug}?page={page_num}"
            )
            print(f"\n  [Page {page_num}]")
            soup = get_page(url)

            if not soup:
                print("  Could not fetch — stopping this category.")
                break

            # Try listing parse first
            records = parse_listing(soup, slug)

            if records:
                print(f"  → Got {len(records)} records from listing page")
                for r in records:
                    print(f"     ✓ {r['Business Name']} | {r['Phone']}")
                all_records.extend(records)
                cat_count += len(records)
            else:
                # Fallback: visit individual business pages
                links = parse_biz_links(soup)
                print(f"  → Listing parse got 0 records, trying {len(links)} detail pages...")
                for i, biz_url in enumerate(links, 1):
                    biz_soup = get_page(biz_url)
                    if biz_soup:
                        rec = parse_biz_detail(biz_soup, biz_url, slug)
                        if rec["Business Name"]:
                            all_records.append(rec)
                            cat_count += 1
                            print(f"     ✓ [{i}] {rec['Business Name']} | {rec['Phone']}")
                    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            if not has_next(soup):
                break

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        print(f"\n  Done: {cat_count} records from '{slug}'")
        time.sleep(random.uniform(4, 8))  # pause between categories

    # ── Save ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  TOTAL: {len(all_records)} records")
    print(f"  Time : {datetime.now() - start}")
    print(f"{'='*55}")

    if not all_records:
        print("\nNo data collected. Check the logs above for errors.")
        return

    df = pd.DataFrame(all_records)
    df.drop_duplicates(subset=["Business Name", "Phone"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nCSV   saved: {OUTPUT_CSV}  ({len(df)} rows)")

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Businesses")
        ws = w.sheets["Businesses"]
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in col) + 4, 60
            )
    print(f"Excel saved: {OUTPUT_EXCEL}  ({len(df)} rows)")

if __name__ == "__main__":
    main()
