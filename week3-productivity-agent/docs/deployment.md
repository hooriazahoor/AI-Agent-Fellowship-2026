# Deployment Guide (Render - recommended, free tier, Docker-native)

## Prerequisites
- A GitHub account with this project pushed to a repository
- Your `GEMINI_API_KEY` (same one used locally)

## Step 1 - Push the project to GitHub

```powershell
cd D:\productivity-agent123\productivity-agent
git init
git add .
git commit -m "Initial commit - productivity agent"
```

Create a new empty repo on github.com (no README/gitignore), then:

```powershell
git remote add origin https://github.com/<your-username>/productivity-agent.git
git branch -M main
git push -u origin main
```

`.gitignore` already excludes `venv/`, `.env`, and `data/*.db`, so secrets won't be pushed.

## Step 2 - Create the Render Web Service

1. Go to https://render.com and sign up / log in (GitHub login is easiest).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub account and select the `productivity-agent` repo.
4. Configure:
   - **Name:** `productivity-agent` (or anything)
   - **Region:** closest to you
   - **Branch:** `main`
   - **Runtime:** **Docker** (Render auto-detects the `Dockerfile`)
   - **Instance Type:** Free
5. Under **Environment Variables**, add each of these (values from your local `.env`):

   | Key | Value |
   |---|---|
   | `GEMINI_API_KEY` | your actual key |
   | `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
   | `GEMINI_MODEL` | `gemini-2.0-flash` |
   | `DATABASE_URL` | `sqlite:///data/productivity_agent.db` |
   | `FLASK_SECRET_KEY` | any random long string |
   | `FLASK_DEBUG` | `False` |
   | `MAX_AGENT_STEPS` | `8` |
   | `MAX_TOOL_RETRIES` | `2` |
   | `TOOL_TIMEOUT_SECONDS` | `30` |
   | `PORT` | `5000` |

6. Click **Create Web Service**. Render will build the Docker image and deploy it (~3-5 minutes).
7. Once live, you'll get a URL like `https://productivity-agent.onrender.com`.

## Step 3 - Load sample data on the live app

Open the deployed URL and click **"Load sample data"** in the sidebar so the app
has something to show during evaluation.

## Important: SQLite persistence on Render's free tier

Render's **free tier does not provide a persistent disk** - the container's
filesystem (including the SQLite file) resets on every redeploy or restart.
This is fine for a demo, but for the onsite evaluation, be aware:

- If the service restarts between your setup and the evaluation, click
  "Load sample data" again.
- For real persistence, either:
  - Upgrade to a Render paid plan and add a **Persistent Disk** mounted at
    `/app/data`, **or**
  - Point `DATABASE_URL` at a free managed Postgres instance instead (Render
    offers a free Postgres tier, or use Supabase - both work since the app
    uses SQLAlchemy, which supports Postgres with no code changes beyond
    the connection string, e.g. `postgresql://user:pass@host/dbname`).

This limitation is documented in the project's `README.md` as required by
the spec ("If persistent cloud storage is not available, clearly document
the limitation").

## Alternative: Railway

1. https://railway.app -> **New Project** -> **Deploy from GitHub repo**.
2. Railway also auto-detects the `Dockerfile`.
3. Add the same environment variables under the service's **Variables** tab.
4. Railway's free tier also uses ephemeral storage by default - same caveat
   as above applies. Add a Railway **Volume** mounted at `/app/data` for a
   persistent SQLite file if you stay on Railway.

## Alternative: Hugging Face Spaces (Docker Space)

1. https://huggingface.co/new-space -> choose **Docker** as the Space SDK.
2. Push this repo's contents to the Space's git remote (same as GitHub).
3. Add secrets under **Settings -> Repository secrets** (same env vars as above).
4. HF Spaces persistent storage requires a paid "persistent storage" add-on;
   otherwise the same ephemeral-SQLite caveat applies.

## Verifying the deployment

Once live, check:
```
https://<your-app-url>/health
```
should return `{"status": "ok", "llm_provider": "gemini"}`.