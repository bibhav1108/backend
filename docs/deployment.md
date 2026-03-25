# 🚀 Sahyog Setu Deployment Guide (Neon + Render)

Follow these steps to deploy your Sahyog Setu backend to the cloud.

## 1. 🐘 Setup Neon Database
1. Go to [Neon.tech](https://neon.tech) and create a new project.
2. In the Neon Console, go to **SQL Editor** and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
3. Copy your **Connection String** (it will look like `postgres://user:pass@host/db`).

## 2. 🌐 Deploy to Render
1. Create a new **Web Service** on [Render](https://render.com).
2. Connect your GitHub repository.
3. Use the following settings:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
4. Add **Environment Variables**:
   - `DATABASE_URL`: (Paste your Neon connection string)
   - `SECRET_KEY`: (A random string)
   - `ALGORITHM`: `HS256`
   - `PYTHONPATH`: `.`

## 3. 🧪 Verify Deployment
1. Once Render says "Live", visit your URL: `https://your-service.onrender.com/health`.
2. It should return `{"status": "healthy"}`.

---
> [!TIP]
> **Database Migrations**: The current setup automatically creates tables on startup. For future updates, consider using Alembic for migrations.
