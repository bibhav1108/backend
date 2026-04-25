# 🛠️ SahyogSync Backend Setup Guide

Follow these steps to set up and run the FastAPI backend and database from scratch.

---

### 📋 Prerequisites
Ensure you have the following installed:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Python 3.10+](https://www.python.org/downloads/)

---

### 🚀 Step-by-Step Setup

#### 1. Start the Database (Docker)
Navigate to the `backend` folder and start the database container:
```bash
cd backend
docker compose up -d
```
> [!NOTE]
> This spins up a PostgreSQL + PostGIS database automatically with standard credentials configured.

---

#### 2. Configure Environment Variables
Create a `.env` file from the example template to match the DB setup:
```bash
# On Windows PowerShell/CMD:
copy .env.example .env

# On Linux/Mac:
# cp .env.example .env
```
*(Optionally edit `.env` if you need to change ports or passwords)*

---

#### 3. Create a Virtual Environment (venv)
Set up an isolated workspace for Python packages:
```bash
python -m venv venv
```

---

#### 4. Activate the Environment
To use the workspace, activate it:
*   **Windows (PowerShell)**: `venv\Scripts\Activate.ps1`
*   **Windows (CMD)**: `venv\Scripts\activate.bat`
*   **Mac/Linux**: `source venv/bin/activate`

---

#### 5. Install Dependencies
Run the install command to get all required modules:
```bash
pip install -r requirements.txt
```

---

#### 6. Seed Default NGO Data
Initialize required lookup variables (NGO IDs, support layers):
```bash
python app/db_seed.py
```

---

#### 7. Start the Backend Launcher
Navigate back to the **project root folder** and run:
```bash
cd ..
python run.py
```

---

### 🔗 Useful Links
Once running, access these in your browser:
*   **Swagger Docs**: [http://localhost:8005/docs](http://localhost:8005/docs)
*   **Health Check**: [http://localhost:8005/health](http://localhost:8005/health)
