# DETOUR — Deployment Guide

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│  Frontend (React)   │  HTTP  │  Backend (FastAPI)   │
│  Vercel (free)      │◄──────►│  Railway / Render    │
└─────────────────────┘        └──────────────────────┘
                                        │
                    ┌───────────────────┼──────────────────┐
                    ▼                   ▼                  ▼
              Supabase DB        Infrared SDK        Gemini API
              (SDK cache)        (microclimate)      (AI personas)
```

---

## Frontend — Vercel

The frontend is a Vite + React app. Vercel handles it natively.

### Steps

1. Go to [vercel.com](https://vercel.com) → New Project → Import your GitHub repo
2. Set **Root Directory** to `thermal-router/frontend`
3. Framework: **Vite** (auto-detected)
4. Add environment variable:
   ```
   VITE_API_URL=https://your-backend.railway.app
   ```
5. Deploy — done.

### Update API URL in frontend

In `thermal-router/frontend/src/hooks/useRoute.ts` and any `fetch('http://localhost:8001/...')` calls, replace with:
```ts
const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'
```

---

## Backend — Railway (recommended)

Railway is the easiest one-click Python host. Free trial, $5/month after.

### Steps

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select the repo, set **Root Directory** to `thermal-router/backend`
3. Railway auto-detects the `requirements.txt` and runs:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. Add environment variables (Settings → Variables):

```env
INFRARED_API_KEY=your_key
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_key
GEMINI_API_KEY=your_key
CORS_ORIGINS=https://your-app.vercel.app
SKIP_SDK=false
SDK_TIMEOUT=180
```

5. Set the start command if not auto-detected:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

### OSM Graph Cache

The pre-warmed `.graphml` files are large and not in the repo (gitignored). You must either:

**Option A — prewarm on Railway** (run once after deploy):
```bash
railway run python prewarm_osm.py
```
This downloads graphs from Overpass API (~5 min). They are saved to `_osm_cache/` on the Railway volume.

**Option B — attach a Railway volume**:
- In Railway: Add → Volume → mount at `/app/_osm_cache`
- Upload your local `.graphml` files via the Railway CLI:
  ```bash
  railway up --detach
  railway run cp -r _osm_cache/ /app/_osm_cache/
  ```

---

## Backend — Render with Docker (recommended)

The backend is fully Dockerized with a multi-stage build.

### Quick Deploy

1. Go to [render.com](https://render.com) → **New +** → **Web Service** → connect GitHub repo
2. Render auto-detects `render.yaml` and creates the service
3. Set **secret** environment variables in the Render dashboard:
   ```
   INFRARED_API_KEY=your_key
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_KEY=your_key
   GEMINI_API_KEY=your_key
   R2_ACCOUNT_ID=your_id
   R2_ACCESS_KEY=your_key
   R2_SECRET_KEY=your_key
   ```
4. Deploy — Render builds the Docker image and starts the service

### How it works

- `render.yaml` defines the service as Docker, pointing to `backend/Dockerfile`
- On startup the app syncs graphml files from Cloudflare R2 (~500 MB, ~60s)
- Then preloads them into memory for instant graph clipping
- Single worker (graphml preload is ~2 GB RAM) — use Starter plan ($7/mo) minimum
- Health check at `/health` with 180s start-period to allow sync + preload

### Local Docker test

```bash
cd backend
docker build -t detour-api .
docker run --env-file .env -p 8000:10000 detour-api
```

---

## Backend — Fly.io (best for always-on + persistent disk)

```bash
# Install flyctl, then from thermal-router/backend/
fly launch
fly secrets set INFRARED_API_KEY=xxx SUPABASE_URL=xxx ...
fly volumes create osm_cache --size 2   # persistent disk for graphml
fly deploy
fly ssh console -C "python prewarm_osm.py"
```

Add to `fly.toml`:
```toml
[mounts]
  source = "osm_cache"
  destination = "/app/_osm_cache"
```

---

## Environment Variables Reference

| Variable | Where | Description |
|---|---|---|
| `INFRARED_API_KEY` | Backend | Infrared SDK API key |
| `SUPABASE_URL` | Backend | Supabase project URL |
| `SUPABASE_KEY` | Backend | Supabase service key |
| `GEMINI_API_KEY` | Backend | Google Gemini (AI personas) |
| `CORS_ORIGINS` | Backend | Comma-separated allowed origins (your Vercel URL) |
| `SKIP_SDK` | Backend | `true` = OSM-only instant routing, `false` = full SDK |
| `SDK_TIMEOUT` | Backend | Seconds before SDK fallback (default 180) |
| `VITE_API_URL` | Frontend | Backend URL for Vercel build |

---

## Recommendation

| Layer | Service | Cost | Notes |
|---|---|---|---|
| **Frontend** | Vercel | Free | Perfect for Vite/React |
| **Backend** | Railway | $5/mo | Easiest setup, persistent disk available |
| **Database** | Supabase | Free tier | Already set up (SDK cache) |
| **Infrared SDK** | api.infrared.city | Pay-per-use | External API |

**Total: ~$5/month** for a production-ready demo.
