# Deploying Slab Terminal

Recommended free setup — three services, about 20 minutes, no credit card:

| Piece | Host | Why |
|---|---|---|
| Postgres | **Neon** (neon.tech) | Free Postgres that doesn't expire |
| FastAPI | **Render** (render.com) | Builds `backend/Dockerfile` from `render.yaml` |
| Next.js | **Vercel** (vercel.com) | First-party Next.js hosting |

The free Render tier sleeps after 15 minutes idle, so the first page load after a break takes
~30–60 s. Render's $7/month Starter plan removes that. (Alternative: put all three on Railway
for about $5/month in one dashboard.)

## 0. Push the code to GitHub
Render and Vercel deploy from your GitHub repo (`shanelin0107/sports_card_plat`).

## 1. Database — Neon
1. Create a project → copy the **connection string** (`postgresql://…neon.tech/neondb?sslmode=require`).
2. Nothing else: the backend creates the tables and loads demo data on first start.
   (Set `SEED_DEMO_DATA=false` on Render if you want to start with an empty collection.)

## 2. API — Render
1. Render → **New → Blueprint** → select the repo. It reads `render.yaml`.
2. Fill `DATABASE_URL` with the Neon string. `API_KEY` is generated for you.
3. After deploy, open `https://<your-api>.onrender.com/health` → `{"status":"ok"}`.
4. Copy the generated `API_KEY` (Environment tab) for step 3.

## 3. Web — Vercel
1. Vercel → **Add New → Project** → import the repo → **Root Directory: `frontend`**.
2. Environment variables:
   - `API_BASE_URL` = `https://<your-api>.onrender.com`
   - `API_KEY` = the value from Render
   - `SITE_PASSWORD` = the password you'll log in with
   - `SESSION_SECRET` = any long random string (`openssl rand -hex 32`)
3. Deploy → open the URL → sign in.

## Security model
- Browser → Vercel requires the login cookie (`SITE_PASSWORD`).
- Vercel → Render sends `X-API-Key`; the API rejects requests without it.
- The API key never reaches the browser; all browser calls go through `/api/backend/*`.

## Running ingestion on a schedule (optional)
Use Render's Cron Job, GitHub Actions, or any cron service to call:
```
curl -X POST -H "X-API-Key: $API_KEY" https://<your-api>.onrender.com/api/v1/internal/ingestion/run?mode=daily
```
The daily-change KPI needs no cron: the dashboard records a valuation snapshot each day it is opened.

## AI price check (optional)
Set `ANTHROPIC_API_KEY` on Render (and in `.env` locally). The card page then shows an
"AI price check" panel: Claude searches the web (eBay sold listings, 130point, price guides,
checklists), identifies the exact card, and lists sold and live prices with source links.
Prices whose source page wasn't actually retrieved are discarded, and nothing becomes a comp
until you click "Save as comp" on an exact match. Cost is roughly $0.05–0.30 per lookup
(web searches are $10 per 1,000 plus tokens). Change the model with `AI_MODEL`.

## eBay market data (optional)
Set `EBAY_CLIENT_ID` (Production App ID) and `EBAY_CLIENT_SECRET` (Production Cert ID) from
developer.ebay.com → Application Keys. Every keyset can read live listings (Browse API); sold
history needs eBay's Marketplace Insights approval, which the app detects automatically
(`GET /api/v1/market/ebay/status`).

## Recent eBay sales per card (optional, CompsAPI)
eBay's own sold-history API is partner-only and its sold search page is behind a captcha,
so sold prices come from [CompsAPI](https://compsapi.com) (eBay sold listings as JSON).

1. Get a free key at https://app.compsapi.com (100 searches/month, 1 year of history;
   paid plans from $9 for 5,000).
2. Set `COMPSAPI_KEY` in `.env` locally (and on Render), then restart.

What it does:
- Collection page: **↻** on a row fetches that card's recent sales (1 search);
  **Update sales** checks every card, skipping any checked in the last 24 hours (free).
  Adding a card fetches its sales right away. Opening a card page also syncs, at most once a day.
- Each sale's title is checked against the card (player, year, set, #, parallel, grade).
  Only exact matches are saved; other parallels, other grades, lots and reprints are skipped.
  Prices include shipping; Best Offer sales use the real accepted price.
- Wrong sale saved? Open the card and use **Wrong sale?** to remove it; it won't come back.
