# 📘 SahyogSync — Complete Feature Guide

> **Version**: 2.2.0 · **Platform**: AI-Powered NGO Coordination System  
> **Tagline**: *Bridging surplus resources to people who need them — powered by AI.*

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Architecture at a Glance](#2-architecture-at-a-glance)
3. [🏪 Marketplace — The Recovery Engine](#3--marketplace--the-recovery-engine)
4. [🎯 Mission Control — The Campaign Engine](#4--mission-control--the-campaign-engine)
5. [🤖 AI Integration — Where Intelligence Lives](#5--ai-integration--where-intelligence-lives)
6. [📱 Telegram Bot — The Field Interface](#6--telegram-bot--the-field-interface)
7. [📦 Inventory Management](#7--inventory-management)
8. [🔐 Authentication & Security](#8--authentication--security)
9. [👥 User & Volunteer Management](#9--user--volunteer-management)
10. [🏢 Organization Management](#10--organization-management)
11. [🛡️ Admin Panel — System Governance](#11-️-admin-panel--system-governance)
12. [🔔 Notification Center](#12--notification-center)
13. [📜 Audit Trail](#13--audit-trail)
14. [💬 Feedback System](#14--feedback-system)
15. [⚙️ System Services & Utilities](#15-️-system-services--utilities)
16. [🗄️ Data Model Reference](#16-️-data-model-reference)
17. [📡 API Route Map](#17--api-route-map)

---

## 1. Platform Overview

**SahyogSync** (formerly *Sahyog Setu*) is a full-stack AI-powered coordination platform designed for **NGOs and civic volunteers**. It automates the entire lifecycle of surplus resource recovery — from a donor's Telegram message to verified volunteer pickup — while also enabling large-scale planned missions (campaigns).

### Core Principles

| Principle | Description |
|---|---|
| **Zero Waste** | Every surplus report from a donor is captured, parsed, and routed to the nearest NGO |
| **Speed First** | Marketplace operates on First-Come-First-Served (FCFS) dispatch for instant response |
| **AI Everywhere** | Gemini AI parses unstructured donor text and drafts campaign plans from natural language |
| **Trust & Verification** | OTP-verified pickups, tiered volunteer trust levels, and full audit trails |
| **Multi-Tenancy** | Strict NGO-level data isolation — each organization sees only its own data |

---

## 2. Architecture at a Glance

SahyogSync operates on **two parallel tracks**:

```
┌─────────────────────────────────────────────────────────────┐
│                      SAHYOGSYNC v2.2                        │
├──────────────────────────┬──────────────────────────────────┤
│   🏪 MARKETPLACE         │   🎯 MISSION CONTROL             │
│   (Recovery Engine)      │   (Campaign Engine)              │
│                          │                                  │
│   • Reactive             │   • Proactive                    │
│   • Donor-driven         │   • NGO-driven                   │
│   • Instant FCFS         │   • Planned & scheduled          │
│   • Telegram-first       │   • Web-first                    │
│   • AI text parsing      │   • AI campaign drafting         │
│   • OTP verification     │   • Volunteer pool management    │
├──────────────────────────┴──────────────────────────────────┤
│              🤖 AI LAYER (Gemini 2.5 Flash)                  │
│       Surplus Parser · Campaign Architect · Fallback Regex  │
├─────────────────────────────────────────────────────────────┤
│              📱 TELEGRAM BOT (Field Interface)               │
│    Donor Reports · Volunteer Onboarding · OTP · Navigation  │
├─────────────────────────────────────────────────────────────┤
│           🗄️ PostgreSQL + SQLAlchemy (Async)                 │
│        PostGIS · JSON Fields · Full Migration Support       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 🏪 Marketplace — The Recovery Engine

The Marketplace is the **reactive, instant-response** system. It handles surplus food/resource donations reported via Telegram or the dashboard.

### 3.1 Marketplace Alerts (Donor Reports)

| Feature | Description |
|---|---|
| **Source** | Donors report surplus via the **Telegram Bot** (`/donate` or inline button) |
| **AI Parsing** | Unstructured text is parsed by **Gemini AI** to extract item, quantity, location, category, urgency |
| **Confirmation Flow** | AI presents a summary card → Donor confirms ✅ or edits 🔄 |
| **Location Pinning** | Donors can share GPS via Telegram's native location or a **web-based map picker** |
| **Dashboard Visibility** | Confirmed alerts appear on the NGO coordinator's dashboard for review |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/marketplace/needs/alerts` | List all confirmed, unprocessed alerts |
| `PATCH` | `/api/marketplace/needs/alerts/{id}/location` | Update alert GPS coordinates (public, for map picker) |
| `POST` | `/api/marketplace/needs/alerts/{id}/convert` | Convert a raw alert into a formal Marketplace Need |

### 3.2 Marketplace Needs

Once an alert is converted, it becomes a **Marketplace Need** — a formal, actionable pickup request.

| Feature | Description |
|---|---|
| **Creation** | Auto-generated from alerts OR manually created by coordinators |
| **Need Types** | `FOOD`, `WATER`, `KIT`, `BLANKET`, `MEDICAL`, `VEHICLE`, `OTHER` |
| **Urgency Levels** | `LOW`, `MEDIUM`, `HIGH` |
| **Status Lifecycle** | `OPEN` → `DISPATCHED` → `OTP_SENT` → `COMPLETED` / `CLOSED` |
| **Multi-NGO Visibility** | Unclaimed needs are visible to ALL active NGOs (marketplace model) |
| **FCFS Claiming** | First NGO to claim a global need gets it — the rest are notified it's taken |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/marketplace/needs/` | Create a new marketplace need |
| `GET` | `/api/marketplace/needs/` | List needs (own + unclaimed global) |
| `POST` | `/api/marketplace/needs/{id}/claim` | Claim a global need for your NGO |

### 3.3 Marketplace Dispatches (Volunteer Assignment)

| Feature | Description |
|---|---|
| **Multi-Dispatch** | Coordinator selects 1+ volunteers → all receive a Telegram alert simultaneously |
| **FCFS Lock** | First volunteer to tap **"✅ Accept Mission"** claims it; others see "Already Taken" |
| **OTP Gate** | Upon acceptance, a **6-digit OTP** (HMAC-SHA256 hashed, 45-min expiry) is generated |
| **Volunteer Status Sync** | Volunteer auto-set to `ON_MISSION` on accept, reverted to `AVAILABLE` on complete/cancel |
| **Donor Notification** | Donor is notified when a volunteer is en route + gets a "Confirm OTP" button |
| **Google Maps Navigation** | If coordinates exist, volunteer gets a direct Google Maps link |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/marketplace/dispatches/` | Dispatch volunteers to a need |
| `POST` | `/api/marketplace/dispatches/verify-otp` | Verify pickup OTP (dashboard route) |
| `GET` | `/api/marketplace/dispatches/` | List all dispatch history for the NGO |

### 3.4 Marketplace Inventory (Recovery History)

Every successfully completed pickup is **auto-logged** into the Marketplace Inventory — a historical record of all recovered resources.

| Feature | Description |
|---|---|
| **Auto-Population** | On OTP verification, the recovered item is logged with quantity/unit/timestamp |
| **Impact Stats** | Total recoveries and item-type breakdown available via `/stats` |
| **Fuzzy Transfer** | Smart suggestions to merge recovered items into main NGO inventory using **fuzzy string matching** |
| **Transfer to Main** | One-click transfer from recovery log to strategic NGO inventory (merge or create new) |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/marketplace/inventory/` | List all recovered items |
| `GET` | `/api/marketplace/inventory/stats` | Impact summary (totals + breakdown) |
| `GET` | `/api/marketplace/inventory/{id}/suggestions` | Fuzzy-match suggestions for transfer |
| `POST` | `/api/marketplace/inventory/{id}/transfer` | Transfer to main inventory |
| `DELETE` | `/api/marketplace/inventory/{id}` | Remove a recovery record |

---

## 4. 🎯 Mission Control — The Campaign Engine

The Campaign Engine handles **proactive, planned NGO-led missions** — things like food drives, health camps, and awareness programs.

### 4.1 Campaign Lifecycle

```
PLANNED → ACTIVE → COMPLETED
   │          │          │
   │          │          └── Inventory deducted, impact summary generated
   │          └── Broadcast sent, volunteers opt-in via web
   └── AI drafts plan OR coordinator creates manually
```

| Feature | Description |
|---|---|
| **AI Drafting** | Coordinator types a natural language prompt → AI generates a structured campaign JSON |
| **Campaign Types** | `HEALTH`, `EDUCATION`, `BASIC_NEEDS`, `AWARENESS`, `EMERGENCY`, `ENVIRONMENT`, `SKILLS`, `OTHER` |
| **Inventory Reservation** | Creating a campaign auto-reserves stock from NGO inventory (prevents over-allocation) |
| **Volunteer Quota** | Optional cap on maximum approved volunteers per mission |
| **Required Skills** | Campaigns can specify skills needed (e.g., `["medical", "driving"]`) |
| **Scheduling** | Start/End time fields for planned execution windows |

### 4.2 Volunteer Pool (Opt-In Flow)

| Feature | Description |
|---|---|
| **Web-Based Briefing** | Volunteers receive a unique URL: `/missions/{id}?vol_id={vid}` |
| **Opt-In/Reject** | Volunteers review briefing and choose to join or decline via the web interface |
| **Pending State** | All opt-ins start as `PENDING` — NGO must explicitly approve |
| **NGO Approval Gate** | Coordinators review the pool, approve/reject volunteers against quota |
| **Instant Notification** | Approved volunteers get a Telegram congratulation; rejected ones are logged |

### 4.3 Broadcast System

| Feature | Description |
|---|---|
| **Auto-Broadcast** | On campaign creation, all active Telegram-linked volunteers get a rich invitation message |
| **Manual Re-Broadcast** | Coordinators can re-trigger broadcast for newly onboarded volunteers |
| **Markdown-Safe** | Dynamic fields are escaped for Telegram Markdown V1 compatibility |
| **Background Processing** | Broadcasts run as FastAPI Background Tasks to prevent timeout |

### 4.4 Campaign Completion

| Feature | Description |
|---|---|
| **Inventory Deduction** | Reserved items are deducted from actual stock on completion |
| **Impact Summary** | Returns mission name, inventory spent, volunteers involved, completion time |
| **Audit Logging** | `MISSION_COMPLETED` event recorded with full metadata |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/campaigns/draft` | AI-generate a campaign draft from natural language |
| `POST` | `/api/campaigns/` | Create a new campaign (with inventory reservation) |
| `GET` | `/api/campaigns/` | List all campaigns for the NGO |
| `GET` | `/api/campaigns/{id}` | Get campaign details |
| `GET` | `/api/campaigns/{id}/pool` | View volunteer pool (pending/approved/rejected) |
| `POST` | `/api/campaigns/{id}/opt-in?vol_id=X` | Volunteer opts into a mission |
| `POST` | `/api/campaigns/{id}/reject?vol_id=X` | Volunteer declines a mission |
| `POST` | `/api/campaigns/{id}/approve-volunteer/{vol_id}` | NGO approves a volunteer |
| `POST` | `/api/campaigns/{id}/complete` | Complete campaign, deduct inventory |
| `POST` | `/api/campaigns/{id}/broadcast` | Manually re-trigger volunteer broadcast |

---

## 5. 🤖 AI Integration — Where Intelligence Lives

SahyogSync uses **Google Gemini 2.5 Flash** via LangChain for two core AI operations:

### 5.1 Surplus Text Parser (`AIService`)

**Location**: `backend/app/services/ai_service.py`

| Aspect | Detail |
|---|---|
| **Purpose** | Parse messy, unstructured donor text into structured JSON |
| **Model** | `gemini-2.5-flash` (temperature=0, timeout=20s) |
| **Input** | Raw text like `"I have 10kg dal at Sector 62, Noida. It is quite fresh."` |
| **Output** | `{"item": "Dal", "quantity": "10kg", "location": "Sector 62, Noida", "category": "FOOD", "urgency": "MEDIUM", "notes": "Quite fresh"}` |
| **Fields Extracted** | `item`, `quantity`, `location`, `category`, `urgency`, `notes` |
| **Prompt Engineering** | System prompt with clear field definitions + 2 few-shot examples |
| **Invocation** | `ai_service.parse_surplus_text(text)` — async, non-blocking |
| **Where Used** | `webhooks.py` → `process_ai_surplus_report()` background task |

### 5.2 Regex Fallback (Plan B)

**Location**: `backend/app/services/ai_service.py` → `_regex_fallback()`

| Aspect | Detail |
|---|---|
| **Purpose** | Ensures 100% uptime even when Gemini API is exhausted, slow, or down |
| **Trigger** | Activates automatically on any AI exception or if API key is missing |
| **Method** | Basic regex pattern matching for quantity patterns (`kg`, `packets`, `ltr`, etc.) |
| **Output Flag** | `"fallback_used": True` — so the bot card warns the user with "⚠️ Plan B: Basic Sync Used" |

### 5.3 Campaign Architect (`CampaignAgent`)

**Location**: `backend/app/agents/campaign_agent.py`

| Aspect | Detail |
|---|---|
| **Purpose** | Generate a structured campaign JSON from a coordinator's natural language prompt |
| **Input** | `"Organize a food distribution drive in Noida for 200 people next Saturday with 5 volunteers who can drive"` |
| **Output** | Complete JSON with `name`, `description`, `type`, `target_quantity`, `items`, `volunteers_required`, `required_skills`, `location_address`, `start_time`, `end_time` |
| **Markdown Handling** | Strips ` ```json ``` ` fences from Gemini's response before parsing |
| **Fallback** | Returns a basic dict with `note: "Plan B: Manual Drafting Required"` on failure |
| **Where Used** | `POST /api/campaigns/draft` endpoint |

### 5.4 AI Integration Map

```
┌────────────────────────────────────────────────────────┐
│                AI INTEGRATION POINTS                    │
├────────────────────────────────────────────────────────┤
│                                                        │
│  📱 Telegram Bot                                       │
│  └── Donor sends text → AIService.parse_surplus_text() │
│      └── Success → Structured summary card             │
│      └── Failure → Regex Fallback (Plan B)             │
│                                                        │
│  🖥️ Web Dashboard                                      │
│  └── Coordinator types prompt → CampaignAgent.draft()  │
│      └── Success → Pre-filled campaign form            │
│      └── Failure → Basic draft for manual editing      │
│                                                        │
│  🧠 AI Predictions (Stored in DB)                      │
│  └── MarketplaceAlert.predicted_type (category)        │
│  └── MarketplaceAlert.predicted_urgency (LOW/MED/HIGH) │
│      └── Pre-fills the "Convert to Need" action        │
│                                                        │
│  🔍 Fuzzy Matching (Non-AI)                            │
│  └── Marketplace → Main Inventory transfer suggestions │
│      └── Difflib SequenceMatcher (threshold: 0.4)      │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## 6. 📱 Telegram Bot — The Field Interface

The Telegram Bot is the **primary interface** for donors and volunteers in the field. It handles everything from onboarding to OTP-verified pickups, all through conversational inline buttons.

### 6.1 Bot Commands

| Command | Who Uses It | What It Does |
|---|---|---|
| `/start`, `/menu` | Everyone | Shows welcome poster + inline buttons (Join Volunteer / Donate Food) |
| `/donate` | Donors | Initiates surplus reporting flow (creates pending alert) |
| `/help` | Everyone | Shows full command reference + support contacts |
| `/tutorial` | Everyone | Step-by-step onboarding guide |
| `/about` | Everyone | About SahyogSync |
| `/leaderboard` | Volunteers | Top 5 heroes ranked by completed missions |
| `/my_missions` | Volunteers | View active marketplace pickup missions |
| `/my_campaigns` | Volunteers | View joined campaign missions with status + web links |
| `/cancel` | Volunteers | Cancel the most recent active pickup (re-opens the need) |

### 6.2 Donation Flow (Donor Journey)

```
1. Donor sends /donate or taps "🎁 Donate Food"
         │
2. Bot creates a [Pending Report] placeholder in DB
         │
3. Donor types free-form text: "I have 10kg dal at Sector 62"
         │
4. Bot responds: "🤖 Thinking... Analyzing your report!"
         │
5. Background Task: Gemini AI parses the text
         │
6. Bot sends AI Summary Card:
   ┌──────────────────────────────────┐
   │ 📦 Item: Dal                     │
   │ 🔢 Quantity: 10kg                │
   │ 📍 Location: Sector 62, Noida    │
   │ 🏷️ Category: FOOD                │
   │ 📝 Notes: None                   │
   │                                  │
   │  [✅ Yes, Confirm] [🔄 No, Edit] │
   └──────────────────────────────────┘
         │
7a. ✅ Confirm → Alert marked confirmed → Location pinning step
    ┌──────────────────────────────────────┐
    │ 🗺️ Pick Precise Spot on Map (Web)    │
    │ 📍 Quick Share (Current Location)    │
    └──────────────────────────────────────┘
         │
7b. 🔄 Edit → Alert reset to [Pending Report] → Donor re-types
         │
8. Notification broadcast to all active NGOs
```

### 6.3 Volunteer Onboarding Flow

```
1. User taps "🙋 Join Volunteer"
         │
2. If already registered → "You're already in! Use /menu"
   If not → "Share your phone to verify"
         │
3. User shares contact via Telegram's native button
         │
4. Phone normalized → Matched against volunteer records
         │
5a. ✅ Match found (pre-registered by NGO):
    - Telegram linked + activated
    - If new: User account auto-created (username + password generated)
    - Credentials sent to volunteer
         │
5b. ❌ No match:
    - "Access Denied — contact your NGO coordinator"
```

### 6.4 Mission Accept/Decline Flow (Volunteer)

```
1. Volunteer receives Dispatch Alert:
   ┌──────────────────────────────────────┐
   │ 🚨 New Donation Pickup ALERT        │
   │ 📦 Type: FOOD                        │
   │ 🔢 Qty: 10kg                         │
   │ 📍 Pickup: Sector 62, Noida          │
   │ 🗺️ Map: [Open Google Maps]           │
   │                                      │
   │  [✅ Accept Mission] [❌ Decline]     │
   └──────────────────────────────────────┘
         │
2a. ✅ Accept:
    - FCFS check → if already taken → "Mission Already Taken!"
    - If available → OTP generated → "Your code is: 483291"
    - Volunteer status → ON_MISSION
    - Donor notified: "Volunteer is on the way!"
         │
2b. ❌ Decline:
    - Dispatch marked FAILED
    - Volunteer status → AVAILABLE
```

### 6.5 OTP Verification Flow (Donor-Side Completion)

```
1. Volunteer arrives at donor location, shows 6-digit code
         │
2. Donor taps "✅ Confirm OTP" button → Bot asks to type the code
         │
3. Donor types the 6-digit code in chat
         │
4. System verifies:
   - Expiry check (45 minutes)
   - HMAC-SHA256 hash comparison
         │
5a. ✅ Valid:
    - Dispatch → COMPLETED
    - Need → COMPLETED
    - Item → auto-logged to MarketplaceInventory
    - VolunteerStats.completions += 1
    - Trust tier auto-upgrade (first mission → FIELD_VERIFIED)
    - Volunteer status → AVAILABLE
    - Impact message to donor + completion message to volunteer
         │
5b. ❌ Invalid → "Invalid Code. Please check."
5c. ⏰ Expired → "OTP Expired"
```

### 6.6 Stability & Fail-Safes

| Mechanism | Description |
|---|---|
| **Non-Blocking AI** | Gemini parsing runs in FastAPI `BackgroundTasks` — webhook responds in <100ms |
| **Message Deduplication** | `InboundMessage` table prevents double-processing during Telegram retries |
| **Alert Expiry** | Pending reports older than 15 minutes are auto-ignored |
| **Markdown Fallback** | If Markdown-formatted message fails (400 error), auto-retries as plain text |
| **Photo Fallback** | If welcome photo fails to send, falls back to text-only welcome |
| **Periodic Cleanup** | Background worker (every 12h) clears stale dedup logs and pending alerts |
| **Regex Fallback** | If Gemini is down, regex parser ensures donor data still reaches the NGO |

---

## 7. 📦 Inventory Management

SahyogSync maintains **two separate inventory systems** to enforce the architectural boundary between reactive recovery and proactive planning.

### 7.1 Strategic Inventory (NGO Internal Stock)

The main inventory that NGOs manage for their planned operations.

| Feature | Description |
|---|---|
| **CRUD** | Full Create/Read/Update/Delete with org-level isolation |
| **Categories** | Free-text category field (e.g., `FOOD`, `MEDICAL`, `OTHERS`) |
| **Reserved Quantity** | Auto-incremented when a campaign reserves stock; prevents deletion of reserved items |
| **Delete Protection** | Items with `reserved_quantity > 0` cannot be deleted (HTTP 409) |
| **Audit Logging** | Every add/update logs an `INVENTORY_ADDED` or `INVENTORY_UPDATED` event |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/inventory/` | List all inventory items |
| `POST` | `/api/inventory/` | Add a new item (duplicate check enforced) |
| `PATCH` | `/api/inventory/{id}` | Update quantity/details (can't go below reserved) |
| `DELETE` | `/api/inventory/{id}` | Delete an item (blocked if reserved) |

### 7.2 Marketplace Inventory (Recovery History)

Automatically populated when marketplace missions complete. See [§3.4](#34-marketplace-inventory-recovery-history).

### 7.3 Inventory Duality

```
┌───────────────────────┐     ┌──────────────────────────┐
│ 📦 Strategic Inventory │     │ 🏪 Marketplace Inventory │
│   (Planned Stock)      │     │   (Recovery History)     │
│                        │     │                          │
│ • Manual CRUD          │ ←── │ • Auto-populated on OTP  │
│ • Campaign Reservation │     │ • Fuzzy transfer tool    │
│ • Category & Units     │     │ • Impact statistics      │
│                        │     │                          │
│ Campaigns draw FROM    │     │ Recoveries feed INTO     │
│ this inventory         │     │ this inventory           │
└───────────────────────┘     └──────────────────────────┘
         ▲                              │
         └──── Transfer (merge/new) ────┘
```

---

## 8. 🔐 Authentication & Security

### 8.1 Login System

| Feature | Description |
|---|---|
| **Method** | OAuth2 Password Flow (username/email + password) |
| **Token** | JWT (JSON Web Token) with `sub`, `org_id`, `role` claims |
| **Expiry** | Configurable (default: 60 minutes) |
| **Org Status Check** | Pending organizations are blocked from login (HTTP 403) |
| **Password Hashing** | Bcrypt via Passlib |

### 8.2 Password Recovery

| Channel | Flow |
|---|---|
| **Email** | User submits email → 6-digit OTP sent via Resend API → User enters OTP + new password |
| **Telegram** | User submits phone → OTP sent to Telegram bot chat → User enters OTP + new password |
| **Expiry** | OTP valid for 10 minutes |
| **Anti-Enumeration** | Returns generic success message even if account doesn't exist |

### 8.3 OTP Security (HMAC-SHA256)

| Aspect | Detail |
|---|---|
| **Generation** | 6-digit random numeric code |
| **Storage** | HMAC-SHA256 hash (never stores raw OTP) |
| **Verification** | Timing-safe comparison via `hmac.compare_digest()` |
| **Expiry** | 45 minutes for marketplace pickups, 10–15 minutes for auth flows |

### 8.4 Role-Based Access Control (RBAC)

| Role | Access Level |
|---|---|
| `SYSTEM_ADMIN` | Full platform access — approve/reject NGOs, view all data, manage feedback |
| `NGO_COORDINATOR` | Organization-scoped — manage volunteers, inventory, campaigns, dispatches |
| `VOLUNTEER` | Personal scope — view own missions, update profile, join requests |

---

## 9. 👥 User & Volunteer Management

### 9.1 Volunteer Registration (Web Flow)

```
1. User visits registration page
         │
2. Enters email + username → POST /volunteers/send-otp
   - Checks email/username uniqueness
   - Sends 6-digit OTP via email (Resend API)
         │
3. User enters OTP → POST /volunteers/verify-otp
   - Returns a signed JWT (verified_token)
         │
4. User fills full form + provides token → POST /volunteers/register
   - Creates User (VOLUNTEER role) + Volunteer + VolunteerStats records
   - Optional: Select an NGO to join (org_id)
```

### 9.2 Volunteer Profiles

| Feature | Description |
|---|---|
| **Trust Tiers** | `UNVERIFIED` → `ID_VERIFIED` → `FIELD_VERIFIED` (auto-upgrades on first mission completion) |
| **Trust Score** | Numeric score (manually adjustable) |
| **Skills** | JSON array of capabilities (e.g., `["medical", "driving"]`) |
| **Zone** | Geographic zone assignment |
| **Aadhaar Verification** | Last 4 digits stored for ID verification |
| **Status** | `AVAILABLE` / `BUSY` / `ON_MISSION` / `INACTIVE` |
| **Statistics** | Completions count, no-shows, hours served |

### 9.3 Join Request System

Volunteers without an NGO can request to join one:

| Step | Description |
|---|---|
| 1 | Volunteer browses public NGO list → sends join request |
| 2 | Request appears in NGO coordinator's "Incoming Requests" panel |
| 3 | Coordinator approves → volunteer's `org_id` updated; or rejects |
| 4 | Only one pending request allowed at a time (anti-spam) |
| 5 | Volunteers can also **leave** an NGO to become independent again |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/volunteers/join-requests/` | Submit a join request |
| `DELETE` | `/api/volunteers/join-requests/{id}` | Cancel pending request |
| `POST` | `/api/volunteers/join-requests/leave` | Leave current NGO |
| `GET` | `/api/volunteers/join-requests/my` | View own requests |
| `GET` | `/api/volunteers/join-requests/incoming` | NGO views pending requests |
| `PATCH` | `/api/volunteers/join-requests/{id}` | NGO approves/rejects |

### 9.4 User Profiles

| Feature | Description |
|---|---|
| **Profile Image** | Upload (JPEG/PNG/WEBP), stored in `/static/profiles/`, unique filename per user |
| **Org Stats** | Real-time counts of campaigns, inventory items, volunteers |
| **Email Update** | OTP-verified email change flow |

---

## 10. 🏢 Organization Management

### 10.1 NGO Registration

```
1. NGO fills registration form:
   - Organization: name, phone, email
   - Coordinator: name, email, password
         │
2. POST /api/organizations/register
   - Validates uniqueness of org email/phone and coordinator email
   - Password complexity check (letters + numbers, min 8 chars)
   - Phone format validation (10+ digits)
   - Creates Organization (status: "pending") + User (NGO_COORDINATOR)
         │
3. System Admin approves the organization
   - Status → "active"
   - Coordinator can now login
```

### 10.2 Organization Profile

| Feature | Description |
|---|---|
| **About** | Free-text description field |
| **Website URL** | Optional link to NGO website |
| **Public Listing** | Active NGOs appear in the public directory for volunteer registration |
| **Broadcast Limits** | `last_broadcast_at` and `daily_broadcast_count` fields for rate limiting |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/organizations/register` | Public NGO registration |
| `GET` | `/api/organizations/me` | Get own org profile |
| `PATCH` | `/api/organizations/me` | Update about/website |
| `GET` | `/api/organizations/public` | List active orgs (for volunteer registration) |

---

## 11. 🛡️ Admin Panel — System Governance

The System Admin panel provides platform-wide oversight and control.

### 11.1 Features

| Feature | Description |
|---|---|
| **System Stats** | Total NGOs, pending NGOs, active NGOs, total volunteers |
| **NGO Listing** | View all organizations with status filter (pending/active) |
| **Volunteer Listing** | View all platform volunteers with identity, status, and trust tier |
| **Approve NGO** | Activate a pending organization (enables coordinator login) |
| **Reject NGO** | Delete a pending organization and all associated data (cascade) |

### 11.2 Access Control

All admin endpoints require `SYSTEM_ADMIN` role — enforced by the `require_admin` dependency.

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/admin/stats` | System-wide statistics |
| `GET` | `/api/admin/organizations` | List all orgs (with optional status filter) |
| `GET` | `/api/admin/volunteers` | List all volunteers |
| `POST` | `/api/admin/organizations/{id}/approve` | Approve an NGO |
| `POST` | `/api/admin/organizations/{id}/reject` | Reject/Delete an NGO |

---

## 12. 🔔 Notification Center

A centralized, real-time notification engine that feeds the coordinator dashboard.

### 12.1 Notification Types

| Type | Trigger | Priority | Description |
|---|---|---|---|
| `DONOR_ALERT` | Donor confirms a surplus report | INFO | Multi-cast to ALL active NGOs |
| `MISSION_ACCEPTED` | Volunteer accepts a marketplace dispatch | SUCCESS | Sent to the volunteer's NGO |
| `MISSION_COMPLETED` | OTP verified (pickup done) | SUCCESS | Sent to the volunteer's NGO |
| `MISSION_CANCELLED` | Volunteer cancels or declines | WARNING | Sent to the volunteer's NGO |
| `CAMPAIGN_INTEREST` | Volunteer opts into a campaign | INFO | Sent to the campaign's NGO |
| `SYSTEM` | Admin broadcasts | Varies | General system notifications |

### 12.2 Smart Cleanup

When an NGO converts/claims a marketplace alert, notifications for that alert are **automatically removed** for all other NGOs. This prevents stale "ghost" alerts cluttering dashboards.

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/notifications/` | List notifications (unread first, paginated) |
| `PATCH` | `/api/notifications/{id}/read` | Mark a notification as read |
| `PATCH` | `/api/notifications/read-all` | Mark all as read |

---

## 13. 📜 Audit Trail

Complete accountability and traceability for all significant actions.

### 13.1 Tracked Events

| Event Type | Trigger |
|---|---|
| `MISSION_LAUNCHED` | New campaign created |
| `MISSION_COMPLETED` | Campaign marked complete |
| `PARTICIPANT_APPROVED` | Volunteer approved for a campaign |
| `INVENTORY_ADDED` | New item added to inventory |
| `INVENTORY_UPDATED` | Stock quantity modified |
| `INVENTORY_TRANSFERRED` | Item moved from marketplace to main inventory |

### 13.2 Audit Record Structure

| Field | Description |
|---|---|
| `org_id` | Which NGO this event belongs to |
| `actor_id` | The user who performed the action |
| `event_type` | Categorical event identifier |
| `target_id` | ID of the affected entity (campaign, inventory item, etc.) |
| `notes` | Human-readable description of what happened |
| `created_at` | UTC timestamp |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/audit/` | Paginated audit logs with optional `event_type` filter |

---

## 14. 💬 Feedback System

### 14.1 Features

| Feature | Description |
|---|---|
| **Submission** | Any authenticated user can submit reviews or report issues |
| **Feedback Types** | `REVIEW` (platform review with optional rating) or `ISSUE` (bug/feature request) |
| **Categories** | `BUG`, `UI`, `FEATURE`, `GENERAL`, etc. |
| **Status Tracking** | `PENDING` → `RESOLVED` (managed by admin) |
| **Admin Dashboard** | System admins can list, filter, and update feedback status |

**API Endpoints:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/feedback/submit` | Submit feedback or issue |
| `GET` | `/api/feedback/list` | Admin: list all feedback (with type filter) |
| `PATCH` | `/api/feedback/{id}/status` | Admin: update status (e.g., mark as RESOLVED) |

---

## 15. ⚙️ System Services & Utilities

### 15.1 Telegram Service

**Location**: `backend/app/services/telegram_service.py`

| Method | Purpose |
|---|---|
| `send_message()` | Send text message with optional inline keyboard |
| `send_photo()` | Send image (URL or local file) with caption |
| `broadcast_photo()` | Blast photo+caption to multiple chat IDs |
| `delete_message()` | Remove a message from chat |
| `get_file_url()` | Resolve Telegram file_id to download URL |
| `answer_callback_query()` | Acknowledge inline button press (stops spinner) |
| `set_bot_commands()` | Register command menu (role-based: public vs volunteer) |
| `send_password_reset_otp()` | Send security code for account recovery |
| `escape_markdown()` | Escape special chars for Telegram Markdown V1 safety |

### 15.2 Email Service

**Location**: `backend/app/services/email_service.py`

| Method | Purpose |
|---|---|
| `send_email()` | Generic email sender via **Resend API** (HTTP-based, no SMTP) |
| `send_verification_email()` | Email verification link for new accounts |
| `send_password_reset_otp()` | 6-digit OTP for password recovery |
| `send_email_update_otp()` | OTP for email address change |
| `send_registration_otp()` | Styled OTP email for volunteer registration |

### 15.3 OTP Service

**Location**: `backend/app/services/otp.py`

| Function | Purpose |
|---|---|
| `generate_otp_code()` | Random 6-digit numeric string |
| `hash_otp()` | HMAC-SHA256 hash with server secret key |
| `generate_otp_pair()` | Returns `(raw_code, hash, expiry_timestamp)` |
| `verify_otp()` | Timing-safe hash comparison |

### 15.4 Fuzzy Matching Utility

**Location**: `backend/app/utils/fuzzy.py`

Used for smart inventory transfer suggestions. Employs Python's `difflib.SequenceMatcher` with a configurable similarity threshold (default: 0.4).

### 15.5 Database Migrations

**Location**: `backend/app/database.py`

The `run_migrations()` function uses SQLAlchemy's `Inspector` to detect missing columns and tables, automatically adding them on startup. This eliminates the need for Alembic in the current development phase.

### 15.6 Background Maintenance Worker

Runs every 12 hours:
1. **Dedup Cleanup**: Removes `InboundMessage` records older than 24 hours
2. **Stale Alert Cleanup**: Removes `MarketplaceAlert` records that are still `[Pending Report]` after 24 hours

---

## 16. 🗄️ Data Model Reference

### Entity Relationship Summary

| Model | Description | Key Relations |
|---|---|---|
| `Organization` | NGO entity | → Users, Volunteers, Needs, Campaigns, Inventory |
| `User` | Platform login identity | → Organization |
| `Volunteer` | Field worker profile | → Organization, User, Stats, JoinRequests |
| `VolunteerStats` | Performance metrics (1:1 with Volunteer) | → Volunteer |
| `VolunteerJoinRequest` | NGO join requests | → Volunteer, Organization |
| `MarketplaceAlert` | Raw donor report from Telegram | → MarketplaceNeeds |
| `MarketplaceNeed` | Formal actionable pickup request | → Organization, Alert, Dispatches |
| `MarketplaceDispatch` | Volunteer assignment to a need | → Need, Volunteer |
| `MarketplaceInventory` | Recovered item log | → Organization |
| `Inventory` | Strategic NGO stock | → Organization |
| `NGO_Campaign` | Planned mission/campaign | → Organization, MissionTeam |
| `MissionTeam` | Volunteer participation in a campaign | → Campaign, Volunteer |
| `Notification` | Dashboard alerts | → Organization |
| `AuditTrail` | Activity log | → Organization |
| `PlatformFeedback` | User reviews/issues | → User |
| `TelegramMessage` | Sent message log (for cleanup) | — |
| `InboundMessage` | Deduplication store | — |
| `RegistrationVerification` | Temporary OTP store for registration | — |

---

## 17. 📡 API Route Map

### Authentication
| Prefix | File |
|---|---|
| `/api/auth` | `auth.py` |

### Core Resources
| Prefix | File |
|---|---|
| `/api/organizations` | `organizations.py` |
| `/api/users` | `users.py` |
| `/api/volunteers` | `volunteers/router.py` |

### Marketplace Engine
| Prefix | File |
|---|---|
| `/api/marketplace/needs` | `marketplace.py` |
| `/api/marketplace/dispatches` | `marketplace_dispatches.py` |
| `/api/marketplace/inventory` | `marketplace_inventory.py` |

### Campaign Engine
| Prefix | File |
|---|---|
| `/api/campaigns` | `campaigns.py` |

### Inventory
| Prefix | File |
|---|---|
| `/api/inventory` | `inventory.py` |

### Webhooks
| Prefix | File |
|---|---|
| `/api/v1/webhooks` | `webhooks.py` |
| `/api/webhooks` | `webhooks.py` (legacy compat) |

### Governance
| Prefix | File |
|---|---|
| `/api/admin` | `admin.py` |
| `/api/notifications` | `notifications/router.py` |
| `/api/audit` | `audit.py` |
| `/api/feedback` | `feedback.py` |

### Metadata
| Prefix | File |
|---|---|
| `/api` (meta) | `meta.py` |

---

> **SahyogSync v2.2.0** — Built with ❤️ for a hunger-free world. 🌍🤝
