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
