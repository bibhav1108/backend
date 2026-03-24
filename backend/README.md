# Sahyog Setu Backend - Phase 1

This is the initial FastAPI backend setup for Sahyog Setu (Version 1.0 Baseline), featuring a fully capable **V3-ready Database Schema** (Enums, Future-proof columns).

---

## 🚀 Quick Start

### 📦 1. Database Layer (Postgres + PostGIS)
Spin up the required database container using Docker Compose:
```bash
docker compose up -d
```
*Note: This starts fully equipped safe PostGIS endpoints scaling the spatial queries automatically for later.*

### 🔑 2. Environment Configuration
Create your `.env` file from the template:
```bash
copy .env.example .env
```
Edit `.env` as required (Defaults will match the docker compose setup).

### 🐍 3. Virtual Environment & Dependencies
```bash
python -m venv venv

# Windows Prompt:
venv\Scripts\activate

# Linux/Mac Prompt:
# source venv/bin/activate

pip install -r requirements.txt
```

### ⚡ 4. Seed Default Organization Layer
Initialize the required placeholder items (NGO IDs) required for registration:
```bash
python app/db_seed.py
```

### 🏃 5. Start the Application
Run development server endpoints:
```bash
uvicorn app.main:app --reload
```
Validate running loops route `/health` returns status complete.

