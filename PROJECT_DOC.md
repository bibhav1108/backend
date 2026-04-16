# 🌉 SahyogSync - System Documentation
**"Powering the Right Help, at the Right Time"**

Welcome to the comprehensive technical documentation for **SahyogSync**. This document provides an in-depth analysis of the architecture, workflows, data models, and intelligence layers that power this social impact platform.

---

## 🏗️ System Architecture
SahyogSync is built on a **High-Performance Async Infrastructure** designed for real-time coordination between NGOs, Volunteers, and Donors.

### 🛠️ Technology Stack
| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Core** | FastAPI (Python 3.12+) | Async performance and type-safe API. |
| **Database** | PostgreSQL + PostGIS | Relational data + Geospatial capabilities. |
| **Intelligence** | Google Gemini (AI Service) | Natural Language Processing for donation reports. |
| **Messaging** | Telegram Bot API | Primary field interface for Volunteers & Donors. |
| **Authentication** | JWT + bcrypt + OTP | Secure access for Admins and Volunteers. |
| **Async Tasks** | FastAPI BackgroundTasks | Non-blocking AI analysis and email dispatch. |

---

## 📋 Core Workflows

### 1. The Resource Marketplace (Speed Layer)
This is the reactive bridge that connects food surplus to immediate recovery.

> [!TIP]
> **Key Innovation**: Uses a "Deduplication Guard" to prevent Telegram retries from double-processing messages, saving AI costs and DB integrity.

#### **Flow**:
1. **Report**: Donor sends a raw message to the Telegram bot (e.g., *"10kg food left at Gomti Nagar"*).
2. **Analyze**: System hands off the text to the **AI Intelligence Layer (Gemini)**.
3. **Structured Summary**: AI extracts `Item`, `Quantity`, `Location`, and `Urgency`.
4. **Confirm**: Donor verifies the summary card via inline buttons.
5. **Dispatch**: NGO claims the alert and dispatches a nearby volunteer.
6. **Verify (OTP)**: Volunteer shows a 6-digit code -> Donor enters it in the bot -> Mission Complete.

---

### 2. Strategic NGO Campaigns (Action Layer)
Designed for planned, high-impact events like healthcare camps or mass distributions.

#### **Flow**:
1. **Plan**: NGO Admin drafts a campaign (Timeline, Items required, Volunteer count).
2. **Recruit**: System broadcasts the mission to the volunteer pool.
3. **Apply**: Volunteers opt-in; Admin reviews their **Trust Tier** and past performance.
4. **Execute**: Approved team coordinates via dynamic web briefs.
5. **Impact**: Mission closure triggers auto-deduction from reserved inventory.

---

## 🗄️ Data Architecture (Enhanced)

### Core Entities
| Entity | Description |
| :--- | :--- |
| **Organizations** | Root entity representing NGOs; owns all inventory and users. |
| **Users** | Admin/Coordinator accounts with RBAC (NGO_ADMIN, NGO_COORDINATOR). |
| **Volunteers** | Field agents with `TrustScore` and `Skills`. Linked to Telegram. |
| **MarketplaceAlert** | The "Inbox" where raw donor reports are parsed by AI. |
| **MarketplaceNeed** | Verified, actionable pickup requests. |
| **MarketplaceDispatch** | The link between a Volunteer and a Need, involving OTP verification. |
| **Inventory** | Internal NGO stock vs. Marketplace recovered resources. |

---

## 🧠 Intelligence Layer (AI Orchestration)
The **AI Service** (`app/services/ai_service.py`) acts as the translator between human speech and database structure.

```python
# Conceptual AI Prompt Logic
"Parse this donation report: '{text}' into JSON format:
 { item: str, quantity: str, location: str, category: NeedType }"
```h

> [!IMPORTANT]
> **Fail-Safe Mechanism**: If the AI (Gemini) is busy or hits rate limits, the system automatically falls back to a **Plan B (Regex Sync)** to ensure no donation report is lost.

---

## 🔐 Security & Identity
1. **Trust Tiers**:
   - `UNVERIFIED`: Fresh signups.
   - `ID_VERIFIED`: Verified via Email/Phone.
   - `FIELD_VERIFIED`: Manual NGO approval after 5+ successful missions.
2. **OTP Lifecycle**:
   - Verification OTPs expire in **10 minutes**.
   - Mission Pickup codes expire in **45 minutes** to ensure proximity and safety.

---

## 📂 Project Structure
```text
backend/app/
├── agents/             # Domain-specific AI Personas (e.g., Campaign Drafter)
├── api/v1/endpoints/   # API Routing (Restful & Webhooks)
├── volunteers/         # Modular logic for Volunteer lifecycle
├── services/           # Business Logic (AI, Email, Telegram, OTP)
├── models.py           # Single Source of Truth for Data
├── database.py         # DB connection & Session management
└── main.py             # FastAPI entry point & Middleware
```

---

## 🚀 Project Evolution (Version History)
SahyogSync has evolved through distinct phases of intelligence and coordination.

| Version | Phase Name | Focus | Key Features |
| :--- | :--- | :--- | :--- |
| **v1.0 - v1.7** | **The Reactive Bridge** | Instant Food Recovery | Telegram bot, Basic Marketplace, Manual OTP verification. |
| **v2.0** | **Mission Control** | Action Layer | Team-based NGO Campaigns, Internal Stock Reservation, Role-based access. |
| **v2.1** | **AI Supervision** | Intelligence Layer | **Gemini AI Integration**, Deduplication Guard, Structured DB logging. |
| **v2.2** | **Verified Trust Hub** | Coordination Layer | (CURRENT) Central Notification Feed, Volunteer Trust Scores, Email/Identity Verification. |
| **v2.3+** | **Operational Edge** | Optimization | (ROADMAP) Spatial Queries (PostGIS), Smart Match Ranking, Fleet Management. |

---

## 🗺️ Future Roadmap
- [ ] **Spatial Heatmaps**: Visualization of surplus hotspots for better NGO planning.
- [ ] **Volunteer Fatigue Scoring**: AI-driven workload management to prevent burnout.
- [ ] **Autonomous Dispatch**: FCFS auto-assignment for high-urgency perishables.

---
> *Generated by Antigravity AI on 2026-04-13*
r high-urgency perishables.


---
> *Generated by Antigravity AI on 2026-04-13*
