# IDBF Bangalore Business Scraper

Scrapes **business name, address, and phone number** from [bangalore.idbf.in](https://bangalore.idbf.in) using GitHub Actions — no laptop needed.

## Repo Structure

```
├── .github/
│   └── workflows/
│       └── scrape.yml       ← GitHub Actions workflow
├── scraper.py               ← Main scraper
├── requirements.txt
└── README.md
```

## How to Run (from your phone)

1. **Create a new GitHub repo** and upload all these files
2. Go to your repo → **Actions** tab
3. Click **IDBF Bangalore Scraper** → **Run workflow** → **Run workflow**
4. Wait ~10–20 mins for it to finish
5. Click the completed run → scroll down to **Artifacts**
6. Download **idbf-results** (contains CSV + Excel file)

## Customize Categories

Edit `scraper.py` → `CATEGORY_SLUGS` list.
Slugs come from the site URL, e.g. `bangalore.idbf.in/restaurants` → slug is `restaurants`.

## Settings

| Variable | Default | Description |
|---|---|---|
| `MAX_PAGES` | 5 | Pages per category |
| `DELAY_MIN` | 2.0 | Min seconds between requests |
| `DELAY_MAX` | 4.0 | Max seconds between requests |

## Output

| Column | Description |
|---|---|
| Business Name | Name of the business |
| Address | Street/area address |
| Phone | Contact number |
| Category | Category slug |
| URL | Source page URL |
