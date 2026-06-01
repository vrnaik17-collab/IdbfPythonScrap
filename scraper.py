"""
IDBF Bangalore Business Scraper
Extracts: Business Name, Address, Phone Number
Output:   idbf_businesses.csv + idbf_businesses.xlsx
"""

import time
import random
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

BASE_URL = "https://bangalore.idbf.in"

CATEGORY_SLUGS = [
    "restaurants",
    "hotels",
    "hospitals",
    "schools",
    "computer-shops",
    "electrical-shops",
    "plumber",
    "tailors",
    "gym",
    "beauty-parlour",
    # Add more slugs here (copy from the site URL)
]

MAX_PAGES  = 5     # Pages per category
DELAY_MIN  = 2.0   # Min seconds between requests
DELAY_MAX  = 4.0   # Max seconds between requests

OUTPUT_CSV   = "idbf_businesses.csv"
OUTPUT_EXCEL = "idbf_businesses.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://bangalore.idbf.in/",
}

# ── HELPERS ────────────────────────────────────────────────────────────────────

def get_page(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            elif r.status_code == 404:
                return None
            print(f"  HTTP {r.status_code} for {url}")
        except Exception as e:
            print(f"  Error attempt {attempt+1}: {e}")
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    return None

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def get_links(soup):
    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if re.search(r"/\d{5,}/", href):
            full = href if href.startswith("http") else BASE_URL + href
            if full not in links:
                links.append(full)
    return links

def has_next(soup):
    for a in soup.select("a"):
        txt = a.get_text(strip=True).lower()
        if txt in ("next", "»", ">", "next page") or "next" in (a.get("rel") or []):
            return True
    return False

def parse_biz(soup, url, category):
    d = {
        "Business Name": "",
        "Address": "",
        "Phone": "",
        "Category": category,
        "URL": url,
    }

    # Name
    for sel in ["h1", ".biz-name", ".business-name"]:
        el = soup.select_one(sel)
        if el:
            d["Business Name"] = clean(el.get_text())
            break

    # Address
    for sel in [".address", ".biz-address", "[itemprop='address']", ".location"]:
        el = soup.select_one(sel)
        if el:
            d["Address"] = clean(el.get_text())
            break
    if not d["Address"]:
        m = re.search(r"Location\s*[-–]\s*(.+?)(?:\n|$)", soup.get_text(), re.I)
        if m:
            d["Address"] = clean(m.group(1))

    # Phone — method 1: tel: link
    tel = soup.select_one("a[href^='tel:']")
    if tel:
        d["Phone"] = clean(tel["href"].replace("tel:", ""))

    # Phone — method 2: class selectors
    if not d["Phone"]:
        for sel in [".phone", ".biz-phone", "[itemprop='telephone']", ".mobile"]:
            el = soup.select_one(sel)
            if el:
                nums = re.findall(r"[\d\s\-\+]{7,}", el.get_text())
                if nums:
                    d["Phone"] = nums[0].strip()
                    break

    # Phone — method 3: regex on full page
    if not d["Phone"]:
        nums = re.findall(r"(?:(?:\+91|0)?[\s\-]?)?[6-9]\d{9}", soup.get_text())
        if nums:
            d["Phone"] = nums[0].strip()

    return d

# ── MAIN ───────────────────────────────────────────────────────────────────────

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
            print(f"  [Page {page_num}] {url}")
            soup = get_page(url)
            if not soup:
                print("  ⚠ Could not fetch. Stopping category.")
                break

            links = get_links(soup)
            print(f"  → {len(links)} listings found")
            if not links:
                break

            for i, biz_url in enumerate(links, 1):
                biz_soup = get_page(biz_url)
                if biz_soup:
                    rec = parse_biz(biz_soup, biz_url, slug)
                    all_records.append(rec)
                    cat_count += 1
                    print(f"     ✓ [{i}] {rec['Business Name'] or '(no name)'} | {rec['Phone'] or 'no phone'}")
                else:
                    print(f"     ✗ [{i}] Skipped")
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            if not has_next(soup):
                break
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        print(f"  → {cat_count} records from '{slug}'")

    print(f"\n{'='*55}")
    print(f"  TOTAL RECORDS: {len(all_records)}")
    print(f"  Time taken: {datetime.now() - start}")
    print(f"{'='*55}")

    if not all_records:
        print("\n⚠ No data collected.")
        return

    df = pd.DataFrame(all_records)
    df.drop_duplicates(subset=["Business Name", "Phone"], inplace=True)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n📄 CSV saved: {OUTPUT_CSV}")

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Businesses")
        ws = w.sheets["Businesses"]
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in col) + 4, 60
            )
    print(f"📊 Excel saved: {OUTPUT_EXCEL}")

if __name__ == "__main__":
    main()
