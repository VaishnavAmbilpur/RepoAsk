# Zero Cold-Start Free Deployment Guide

This guide explains how to deploy **RepoAsk** (Frontend + Backend) **100% Free** without cold starts.

---

## 🚫 Why Avoid Render, Koyeb, or Railway Free Tiers?
* **Render Free:** Spins down after 15 mins of inactivity. Cold start takes **50 to 90 seconds**, causing timeouts.
* **Koyeb / Vercel Serverless Functions:** 10–25s timeout limit kills long SSE streams and in-process ONNX embeddings.

---

## 🏆 The Zero Cold-Start Free Architecture

```
┌─────────────────────────────────┐      ┌──────────────────────────────────┐
│      Cloudflare Pages / Vercel   │      │         Fly.io / Koyeb 24/7      │
│      (Frontend Static SPA)      │ ───► │      (FastAPI Docker Backend)     │
│       • Edge CDN (Global)       │ HTTPS│       • Always-on Docker          │
│       • 0ms Cold Start          │      │       • FastEmbed Pre-cached      │
└─────────────────────────────────┘      └──────────────────────────────────┘
                                                          │
                                         ┌────────────────┴─────────────────┐
                                         │       Turso Cloud SQLite         │
                                         │   • Free 9GB storage             │
                                         │   • LibSQL Edge replication      │
                                         └──────────────────────────────────┘
```

---

## Part 1: Deploy Backend (Fly.io or Render with Keep-Alive)

### Option A: Fly.io (Recommended — Never Sleeps)
Fly.io provides free shared-cpu VMs that don't spin down when configured properly.

1. Install Fly CLI:
   ```powershell
   powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
   ```
2. Login and launch from the `backend` directory:
   ```bash
   cd backend
   fly launch
   ```
   * Choose an app name (e.g., `repoask-api`)
   * When asked to tweak settings, say `Yes` or edit `fly.toml` to set:
     ```toml
     [http_service]
       internal_port = 8000
       force_https = true
       auto_stop_machines = false   # ◄── PREVENTS COLD STARTS!
       auto_start_machines = true
       min_machines_running = 1      # ◄── KEEPS 1 MACHINE ALWAYS ON!
     ```
3. Set your secrets:
   ```bash
   fly secrets set OPENROUTER_API_KEY="your-key-here" FRONTEND_ORIGIN="https://your-frontend.pages.dev,https://your-app.vercel.app"
   ```
4. Deploy:
   ```bash
   fly deploy
   ```
   Your backend is live at `https://repoask-api.fly.dev`!

---

### Option B: Render Web Service (With 0 Cold-Start Keep-Alive Cron)
If you prefer Render:
1. Push this repository to GitHub.
2. In Render Dashboard, click **New Web Service** and select your repo.
3. Configure:
   * **Root Directory:** `backend`
   * **Runtime:** `Docker` (Render automatically uses [backend/Dockerfile](file:///c:/Users/Vaishnav%20Ambilpur/Desktop/Trek%20-%20RepoGuide/backend/Dockerfile))
   * **Instance Type:** Free
   * **Environment Variables:**
     * `OPENROUTER_API_KEY`: your OpenRouter API key
     * `FRONTEND_ORIGIN`: `*` or your frontend URL
4. **Kill the Cold Start (Free Cron):**
   * Go to [cron-job.org](https://cron-job.org) (100% free forever).
   * Create a cron job pointing to: `https://your-render-app.onrender.com/healthz`
   * Schedule: **Every 10 minutes**.
   * Render will **never go to sleep**, giving you 0 cold start!

---

## Part 2: Deploy Frontend (Cloudflare Pages or Vercel)

Both Cloudflare Pages and Vercel are static CDNs with **0ms cold start**.

### Option A: Cloudflare Pages (Recommended)
1. Push your code to GitHub.
2. Go to Cloudflare Dashboard > **Workers & Pages** > **Create application** > **Pages**.
3. Connect your GitHub repository.
4. Build Settings:
   * **Framework preset:** `Vite`
   * **Root directory:** `frontend`
   * **Build command:** `pnpm run build`
   * **Build output directory:** `dist`
5. Environment Variables:
   * `VITE_API_URL`: `https://your-backend-url.fly.dev` (or `onrender.com`)
6. Click **Save and Deploy**.

### Option B: Vercel
1. Install Vercel CLI or import the repo via [vercel.com](https://vercel.com).
2. Set Root Directory to `frontend`.
3. Add Environment Variable:
   * `VITE_API_URL`: `https://your-backend-url.fly.dev`
4. The included `vercel.json` automatically handles client-side routing.

---

## Part 3: Free Cloud Database (Turso — Optional)

By default, the backend includes SQLite (`local.db`). For persistence across Docker container rebuilds:
1. Create a free account at [turso.tech](https://turso.tech) (Free tier includes 9GB).
2. Create database: `turso db create repoask`
3. Get URL and token:
   ```bash
   turso db show repoask --url
   turso db tokens create repoask
   ```
4. Set backend environment variables:
   * `TURSO_DATABASE_URL`: `libsql://your-db-name.turso.io`
   * `TURSO_AUTH_TOKEN`: `your-turso-token`

