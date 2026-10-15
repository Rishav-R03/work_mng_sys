# Work Tracker

Log hours, overtime and wins; pull GitHub commits/PRs as evidence; generate a manager report or a recruiter-ready summary.

Stack: FastAPI · Jinja2 · Bootstrap 5 · HTMX · Chart.js · SQLAlchemy (SQLite locally, Postgres in prod).

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # set DEV_LOGIN=1 to try it without GitHub
.venv\Scripts\python seed_demo.py   # optional: fake data for the demo user
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Open http://localhost:8000 and use "Demo login" (needs `DEV_LOGIN=1`).

## GitHub sign-in

1. https://github.com/settings/developers → **New OAuth App**.
2. Homepage URL: your `BASE_URL`. Callback URL: `BASE_URL/auth/callback`
   (local: `http://localhost:8000/auth/callback`).
3. Put the client id/secret in `.env` (or Render env vars), and set `ALLOWED_GITHUB_LOGIN` to your username.

`GITHUB_SCOPE=read:user repo` lets the sync include commits from private repos. Use `read:user` for public activity only.
The token is stored encrypted (Fernet key derived from `SECRET_KEY`). Changing `SECRET_KEY` means signing in again.

## Deploy (Render free + Neon free)

Render's free filesystem is ephemeral and its free Postgres expires, so the database lives on Neon.

1. Create a Neon project, copy the connection string (`postgresql://...?sslmode=require`).
2. Push this folder to GitHub, then in Render: **New → Blueprint** (uses `render.yaml`).
3. Set env vars: `DATABASE_URL`, `BASE_URL` (the `https://...onrender.com` URL), `GITHUB_CLIENT_ID`,
   `GITHUB_CLIENT_SECRET`, `ALLOWED_GITHUB_LOGIN`. Do **not** set `DEV_LOGIN`.
4. Update the GitHub OAuth callback URL to the Render URL.

The free web service sleeps after ~15 min idle; the first request afterwards takes 30–60 s.
Tables are created on startup (no migrations). Use **Settings → Download CSV** as your backup.

## How things are calculated

- Each entry stores `duration_minutes`. Start/end are optional (break is subtracted in start–end mode).
- Overtime for a day = that day's total minus contracted hours (min 0). Month figures are the sums.
- GitHub activity is bucketed by calendar day in your configured timezone.
- GitHub sync uses the search API (default branch commits, merged PRs), first sync covers 12 months.
