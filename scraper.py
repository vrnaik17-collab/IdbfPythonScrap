"""
IDBF Bangalore Business Scraper - Fixed Version
Extracts: Business Name, Address, Phone Number
Output:   idbf_businesses.csv + idbf_businesses.xlsx

Changes from v1:
 - Longer retry delays (server was rate-limiting / returning 500s)
 - Session with cookies to appear more human
 - Correct category slugs confirmed from live site
 - Scrapes data directly from listing pages (faster, no per-business requests needed)
 - Falls back to visiting individual business pages if listing parse fails
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

# These slugs are confirmed working from the live site
CATEGORY_SLUGS = [
    "gym",
    "beauty-parlour",
    "school",
    "plywood",
    "hospitals",
    "hotels",
    "restaurants",
    "blood-banks",
    "library",
    "maths-academy",
    "computer",
    "electrical",
    "plumber",
    "tailors",
    "bakery",
    "pharmacy",
    "clinic",
    "dentist",
    "supermarket",
    "hardware",
    # Add more — just copy the slug from bangalore.idbf.in/SLUG
]

MAX_PAGES   = 10    # Pages per category
DELAY_MIN   = 4.0   # Increased to avoid 500 rate-limit errors
DELAY_MAX   = 8.0
RETRY_WAIT  = 15.0  # Wait after a 500 error before retrying

OUTPUT_CSV   = "idbf_businesses.csv"
OUTPUT_EXCEL = "idbf_businesses.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── SESSION SETUP ─────────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update(HEADERS)

def warm_up_session():
    """Visit homepage first to get cookies, like a real browser."""
    try:
        print("  Warming up session (visiting homepage)...")
        r = session.get(BASE_URL, timeout=15)
        print(f"  Homepage status: {r.status_code}")
        time.sleep(random.uniform(3, 5))
    except Exception as e:
        print(f"  Warmup failed (continuing anyway): {e}")

# ── PAGE FETCHER ──────────────────────────────────────────────────────────────

def get_page(url, retries=4):
    for attempt in range(retries):
        try:
            # Add random Referer to look human
            referer = BASE_URL if attempt == 0 else f"{BASE_URL}/gym"
            session.headers.update({"Referer": referer})

            r = session.get(url, timeout=20)

            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")

            elif r.status_code == 500:
                wait = RETRY_WAIT * (attempt + 1)
                print(f"  [!] HTTP 500 — server overloaded. Waiting {wait}s before retry {attempt+1}/{retries}...")
                time.sleep(wait)

            elif r.status_code == 404:
                print(f"  [!] 404 Not Found: {url}")
                return None

            elif r.status_code == 429:
                wait = 60
                print(f"  [!] Rate limited (429). Waiting {wait}s...")
                time.sleep(wait)

            else:
                print(f"  [!] HTTP {r.status_code} for {url}")
                time.sleep(random.uniform(5, 10))

        except requests.exceptions.Timeout:
            print(f"  [!] Timeout on attempt {attempt+1}")
            time.sleep(10)
        except Exception as e:
            print(f"  [!] Error on attempt {attempt+1}: {e}")
            time.sleep(5)

    print(f"  [✗] All {retries} attempts failed for {url}")
    return None

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

# ── LISTING PAGE PARSER ───────────────────────────────────────────────────────
# The site shows business name + address directly on the listing/category page.
# Each business is a block with name, address, and sometimes phone.

def parse_listing_page(soup, category):
    """Extract all business entries directly from a listing/category page."""
    records = []

    # Strategy 1: Look for structured business cards/list items
    # Common patterns in directory sites
    candidates = (
        soup.select(".business-list li") or
        soup.select(".biz-list li") or
        soup.select("ul.list li") or
        soup.select(".listing-item") or
        soup.select(".business-item") or
        soup.select("table tr") or
        []
    )

    if candidates:
        for item in candidates:
            name = ""
            address = ""
            phone = ""

            # Name: usually a link or heading
            for sel in ["h2", "h3", "a.biz-name", ".name", "strong", "b"]:
                el = item.select_one(sel)
                if el and el.get_text(strip=True):
                    name = clean(el.get_text())
                    break

            # Address
            for sel in [".address", ".location", "span.addr", "p"]:
                el = item.select_one(sel)
                if el:
                    address = clean(el.get_text())
                    break

            # Phone
            tel = item.select_one("a[href^='tel:']")
            if tel:
                phone = clean(tel["href"].replace("tel:", ""))
            if not phone:
                nums = re.findall(r"[6-9]\d{9}", item.get_text())
                if nums:
                    phone = nums[0]

            if name:
                records.append({
                    "Business Name": name,
                    "Address": address,
                    "Phone": phone,
                    "Category": category,
                })

    # Strategy 2: Regex scan the full page text for "Name · Address" patterns
    # This catches sites that embed data in plain text blocks
    if not records:
        full_text = soup.get_text(separator="\n")
        # Look for Indian phone numbers near names
        phone_pattern = re.compile(r"[6-9]\d{9}")
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]
            phones = phone_pattern.findall(line)
            if phones:
                # Phone found — look back for name/address
                name = lines[i-2] if i >= 2 else ""
                address = lines[i-1] if i >= 1 else ""
                if name and len(name) > 3:
                    records.append({
                        "Business Name": name,
                        "Address": address,
                        "Phone": phones[0],
                        "Category": category,
                    })
            i += 1

    return records


def get_biz_links(soup):
    """Get individual business page links from a listing page."""
    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        # Business URLs: /123456/business-name or /bangalore/123456/business-name
        if re.search(r"/\d{5,}/[a-z]", href):
            full = href if href.startswith("http") else BASE_URL + href
            if full not in links:
                links.append(full)
    return links


def parse_biz_detail(soup, url, category):
    """Extract data from an individual business detail page."""
    d = {"Business Name": "", "Address": "", "Phone": "", "Category": category, "URL": url}

    for sel in ["h1", ".biz-name", ".business-name"]:
        el = soup.select_one(sel)
        if el:
            d["Business Name"] = clean(el.get_text()); break

    for sel in [".address", ".biz-address", "[itemprop='address']", ".location"]:
        el = soup.select_one(sel)
        if el:
            d["Address"] = clean(el.get_text()); break
    if not d["Address"]:
        m = re.search(r"(?:Address|Location)\s*[:\-–]\s*(.+?)(?:\n|<)", soup.get_text(), re.I)
        if m:
            d["Address"] = clean(m.group(1))

    tel = soup.select_one("a[href^='tel:']")
    if tel:
        d["Phone"] = clean(tel["href"].replace("tel:", ""))
    if not d["Phone"]:
        for sel in [".phone", ".biz-phone", "[itemprop='telephone']", ".mobile"]:
            el = soup.select_one(sel)
            if el:
                nums = re.findall(r"[6-9]\d{9}", el.get_text())
                if nums:
                    d["Phone"] = nums[0]; break
    if not d["Phone"]:
        nums = re.findall(r"[6-9]\d{9}", soup.get_text())
        if nums:
            d["Phone"] = nums[0]

    return d


def has_next_page(soup):
    for a in soup.select("a"):
        txt = a.get_text(strip=True).lower()
        if txt in ("next", "»", ">", "next page", "next »"):
            return True
        if "next" in (a.get("rel") or []):
            return True
    return False


# ── MAIN SCRAPER ──────────────────────────────────────────────────────────────

def scrape_category(slug):
    records = []
    print(f"\n{'='*58}")
    print(f"  📂 Category: {slug}")
    print(f"{'='*58}")

    for page_num in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}/{slug}" if page_num == 1 else f"{BASE_URL}/{slug}?page={page_num}"
        print(f"\n  [Page {page_num}] Fetching: {url}")

        soup = get_page(url)
        if not soup:
            print("  ⚠ Could not fetch listing page. Stopping this category.")
            break

        # Try parsing data directly from listing page first (faster)
        listing_records = parse_listing_page(soup, slug)
        if listing_records:
            print(f"  → Extracted {len(listing_records)} records from listing page directly")
            records.extend(listing_records)
        else:
            # Fallback: visit each business detail page
            links = get_biz_links(soup)
            print(f"  → Found {len(links)} business links (visiting each individually)")
            for i, biz_url in enumerate(links, 1):
                biz_soup = get_page(biz_url)
                if biz_soup:
                    rec = parse_biz_detail(biz_soup, biz_url, slug)
                    records.append(rec)
                    print(f"     ✓ [{i}] {rec['Business Name'] or '(no name)'} | {rec['Phone'] or 'no phone'}")
                else:
                    print(f"     ✗ [{i}] Skipped")
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        if not has_next_page(soup):
            print(f"  → No next page after page {page_num}.")
            break

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n  ✅ Total from '{slug}': {len(records)}")
    return records


def main():
    warm_up_session()

    all_records = []
    start = datetime.now()

    for slug in CATEGORY_SLUGS:
        cat_records = scrape_category(slug)
        all_records.extend(cat_records)
        # Pause between categories to avoid server hammering
        time.sleep(random.uniform(5, 10))

    print(f"\n{'='*58}")
    print(f"  🎉 TOTAL RECORDS: {len(all_records)}")
    print(f"  ⏱  Time: {datetime.now() - start}")
    print(f"{'='*58}")

    if not all_records:
        print("\n⚠ No data collected. The site may be down or blocking. Try again later.")
        return

    df = pd.DataFrame(all_records)
    # Keep only useful columns, drop URL if not needed
    cols = ["Business Name", "Address", "Phone", "Category"]
    if "URL" in df.columns:
        cols.append("URL")
    df = df[cols]
    df.drop_duplicates(subset=["Business Name", "Phone"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n📄 CSV  → {OUTPUT_CSV}  ({len(df)} rows)")

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Businesses")
        ws = w.sheets["Businesses"]
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in col) + 4, 60
            )
    print(f"📊 Excel → {OUTPUT_EXCEL}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
