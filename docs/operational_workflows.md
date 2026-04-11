# Sahyog Setu - Complete Operational Lifecycle & Subparts

This document provides a **comprehensive breakdown** of every version of Sahyog Setu, detailing the operational flow (Mermaid diagrams) and the granular subparts/components active in each phase.

---

## 🌐 Version 1.0 - 1.7: The Reactive Bridge
*Goal: Connecting donors to NGOs for instant food recovery.*

### 🗺️ Operational Flow (Marketplace / Speed Layer)
```mermaid
sequenceDiagram
    actor Donor
    actor Bot
    actor Backend
    actor NGO_Admin
    actor Volunteer

    Donor->>Bot: 📱 Msg: "Surplus Food at 12 MG Road..."
    Bot->>Backend: 📡 Immediate 200 OK Response
    Bot->>Donor: 🤖 "Analyzing your report... (Hold on!)"
    
    rect rgb(240, 240, 240)
    Note over Bot, Backend: Background Task Started
    alt AI is Active
        Bot->>Backend: 🧠 AI Parsing (Gemini 2.0)
    else AI Exhausted
        Bot->>Backend: 🛡️ Regex Fallback (Plan B)
    end
    end

    Bot->>Donor: 🔢 "Confirm Summary? [✅ Yes / 🔄 Edit]"
    Donor->>Bot: ✅ Yes
    Backend->>Backend: 📡 MarketplaceAlert.is_confirmed = True
    
    NGO_Admin->>Backend: 📄 List Confirmed Alerts
    NGO_Admin->>Backend: 🖱️ Claim Alert -> MarketplaceNeed
    
    NGO_Admin->>Backend: 🎫 Dispatch Volunteer
    Backend->>Volunteer: 📱 Mission Alert
    Volunteer->>Bot: ✅ Accept
    
    Volunteer->>Donor: 🚗 Arrives & shows OTP
    Donor->>Bot: 🔢 Enters OTP
    Bot->>Backend: 📡 Verify & Complete
    Backend->>Backend: 📉 Auto-Populate MarketplaceInventory
    Backend->>Donor: 🎉 "Impact Recorded"
```

---

## 🏢 Version 2.0: Mission Control (The Action Layer)
*Goal: Structured, team-based NGO campaigns with strict resource security.*

### 🗺️ Operational Flow (NGO Campaigns / Strategic Layer)
```mermaid
sequenceDiagram
    actor NGO_Admin
    actor Inventory
    actor Volunteer_Pool
    actor Backend
    actor Mission_Team

    NGO_Admin->>Backend: 📋 Create NGO_Campaign (Education/Health)
    NGO_Admin->>Backend: ➕ Set Quota & Timeline
    
    Backend->>Inventory: 🔒 Reserve Internal Stock (reserved_quantity)
    
    NGO_Admin->>Backend: 📣 Broadcast Recruitment
    Volunteer_Pool->>Backend: 🙋 Join Pool (Opt-In)
    
    NGO_Admin->>Backend: 🕵️ Review Candidates
    NGO_Admin->>Backend: ✅ Approve Final Team
    
    Backend->>Mission_Team: 🚀 Mission Activation
    
    NGO_Admin->>Backend: 🏁 Mark Complete
    Backend->>Inventory: 📉 Deduct Physical & Reserved stock
    Backend->>Backend: 📊 Generate Action Impact Report
```

### 🧩 Subparts & Components: V2.0 (Dual-Engine Stability)
| Subpart | Component | Details |
| :--- | :--- | :--- |
| **Stability Layer** | BackgroundTasks | FastAPI processing prevents Telegram timeout retries. |
| **Fail-Safe Gate** | Regex Fallback | Ensures 100% mission uptime even if Gemini AI hits limits. |
| **Recovery Engine** | `MarketplaceInventory` | Auto-logs resources recovered via the public marketplace. |
| **Action Engine** | 6-Step Lifecycle | Identify ➡️ Plan ➡️ Gather ➡️ Execute ➡️ Complete ➡️ Report. |
| **Governance** | Admin Gateway | Pool-based recruitment for complex strategic missions. |

---

## 🏢 Version 2.1: AI Supervision (The Intelligence Layer)
*Goal: Supervised AI parsing, auto-deduplication, and structured report management.*

### 🗺️ Operational Flow (Marketplace / Deduplication Guard)
```mermaid
sequenceDiagram
    actor Donor
    actor Bot
    actor Backend
    actor Gemini
    actor NGO_Dashboard

    Donor->>Bot: 📱 Msg: "Surplus Food at Gomti Nagar..."
    
    rect rgb(230, 240, 255)
    Note over Bot, Backend: Deduplication Guard
    Backend->>Backend: 🛡️ Check InboundMessage Table
    alt Is Duplicate (Retry)
        Backend-->>Bot: 🚫 Ignore (Return 200 OK)
    else Is New Message
        Backend->>Backend: 📝 Log Message ID
    end
    end

    Backend->>Gemini: 🧠 Structured Parsing (Item/Qty/Location)
    Gemini-->>Backend: 📋 JSON Payload (donations: [...])
    
    Backend->>Backend: 📊 Save Structured Columns to MarketplaceAlert
    
    Bot->>Donor: 🔢 "Confirm Summary? [✅ Rice/Dal @ Noida]"
    
    NGO_Dashboard->>Backend: 📄 View Structured Alerts (Columns)
    NGO_Dashboard->>Backend: 🖱️ Convert to Need (Auto-fills address/item)
```

### 🗺️ Operational Flow (AI Campaign Architect)
```mermaid
sequenceDiagram
    actor NGO_Admin
    actor AIAgent
    actor Backend
    actor Inventory
    actor Volunteer_Pool

    NGO_Admin->>AIAgent: ✍️ "I want to feed 500 people in Hazratganj"
    AIAgent->>Backend: 🧠 Parse Intent & Architect Plan
    Backend-->>NGO_Admin: 📝 Campaign DRAFT (Name/Timeline/Resources)
    
    NGO_Admin->>NGO_Admin: 🖱️ Review & Edit Draft
    NGO_Admin->>Backend: 🚀 ACTIVATE Mission
    
    Backend->>Inventory: 🔒 Reserve Stock
    Backend->>Volunteer_Pool: 📣 Targeted Broadcast (Web Link)
```

### 🧩 Subparts & Components: V2.1 (AI Supervision)
| Subpart | Component | Details |
| :--- | :--- | :--- |
| **Deduplication** | `InboundMessage` | Prevents Telegram retries from exhausting Gemini quotas. |
| **Data Recovery** | Structured Storage | Saves item/qty/location in distinct DB columns for auditing. |
| **Impact Tracker** | `MarketplaceInventory` | Auto-logs recovery history + NGO impact stats. |
| **Draft Engine** | LangChain Architect | **NGO Assistant Persona**: Generates professional mission drafts (Timeline/Resources) from simple coordinator prompts. |
| **V2 Guard** | 45-min OTP Expiry | Ensures mission integrity during high-speed pickups. |
| **Modular Core** | `backend/app/agents/` | Scalable package for domain-specific AI intelligence. |

---

## 🔔 Version 2.2: Verified Trust & Event Hub (The Coordination Layer)
*Goal: Centralized activity feed + Automated volunteer trust & identity management.*

### 🗺️ Operational Flow (Volunteer Trust & Onboarding)
```mermaid
sequenceDiagram
    actor Vol as Volunteer
    actor Bot as Telegram Bot
    actor BE as Backend
    actor Email as Email Service
    actor Admin as NGO Admin

    Vol->>Bot: 📱 Share Contact
    Bot->>BE: 📡 Match Phone & Auto-Generate User
    BE-->>Bot: 🔐 Return Credentials (Username/Password)
    Bot->>Vol: 🎉 "Welcome! Log in with these details..."
    
    rect rgb(235, 245, 235)
    Note over Vol, BE: Identity Verification Flow
    Vol->>BE: 📧 Update Profile (Email)
    BE->>Email: 🔢 Send OTP/Verification Link
    Vol->>BE: ✅ Verify Email
    BE->>BE: 📈 Status: ID_VERIFIED (+10 Trust Score)
    end

    Admin->>BE: 🕵️ Review Documents / ID
    Admin->>BE: 🥇 Mark as "TRUSTED" Tier
```

### 🗺️ Operational Flow (Unified Notification Engine)
```mermaid
sequenceDiagram
    actor System_Events
    actor Telegram_Webhook
    actor Notification_Service
    actor NGO_Dashboard
    actor Marketplace/Campaigns

    System_Events->>Notification_Service: 📡 Trigger: Donor Confirm / Mission Accept / Complete
    Telegram_Webhook->>Notification_Service: 📱 Trigger: Bot Interaction Events
    
    Notification_Service->>Notification_Service: 📝 Log to 'notifications' table (Priority/Data)
    Notification_Service-->>System_Events: 201 Created
    
    NGO_Dashboard->>Notification_Service: 🔄 Poll /api/v1/notifications
    Notification_Service-->>NGO_Dashboard: 📑 Return Activity Feed (Clickable metadata)
    
    NGO_Dashboard->>Marketplace/Campaigns: 🖱️ Click Notification -> Navigate to specific ID
```

### 🧩 Subparts & Components: V2.2 (Verified Coordination)
| Subpart | Component | Details |
| :--- | :--- | :--- |
| **Activity Feed** | `NotificationService` | Central engine for generating human-readable alerts from raw system events (Campaign join, OTP verify). |
| **Trust Tier System** | RBAC Guard | Categorizes volunteers into **NEW**, **ACTIVE**, and **ID_VERIFIED** based on security milestones. |
| **Identity Automator** | Credential Gen | Converts Telegram contacts into full `User` accounts using standardized naming rules. |
| **Security Layer** | Email/OTP Service | Handles time-bound (10-min) OTPs for password resets and identity verification. |
| **Deep-Linking** | Data Metadata | Stores target entity IDs (`campaign_id`, `alert_id`) in JSON for instant UI navigation. |
| **Modular Core** | `app/volunteers/` | Consolidated directory for all volunteer schemas, services, and routing. |

---

## 🔵 Version 2.3: Operational Optimization (Roadmap)
*Goal: Intelligent matching using PostGIS spatial queries and ML ranking.*

### 🗺️ Operational Flow (Smart Matching Lifecycle)
```mermaid
sequenceDiagram
    actor Donor
    actor Telegram/WhatsApp
    actor Gemini
    actor NGO_Admin
    actor Backend
    actor Volunteer_Team

    Donor->>Telegram/WhatsApp: 📱 Msg: "Surplus Food at 12 MG Road..." (Chat)
    Gemini->>Backend: 🧠 Real-time Parsing + Confidence Scoring
    Backend->>Backend: 📍 PostGIS: Find nearest NGOs (<5km)
    Backend->>NGO_Admin: 🚨 Priority Alert (Marketplace)
    
    NGO_Admin->>Backend: 🖱️ Claim & Auto-Suggest Volunteers
    Backend->>Backend: ⚡ Ranking: [Proximity + Trust Tier + Past Completions]
    
    Backend->>Volunteer_Team: 🚀 Targeted Dispatch
```

---

## 🔵 Version 2.5+: Security & Fatigue (Future Roadmap)
*Goal: Ensuring volunteer safety and data privacy.*

- **Fatigue Scoring**: Monitors volunteer workload to prevent burnout (Score = Hours + Mission count).
- **Security Gate**: Implements AES-256 encryption at rest for sensitive donor/volunteer PII (Phone numbers, precise locations).
- **Compliance Checks**: Automated verification of NGO status before allowing mission broadcasts.

---

## 🔵 Version 3.0: Intelligence & Scale (Crisis Autopilot)
*Goal: Autonomous resource allocation and city-scale crisis management.*

| Subpart | Component | Details |
| :--- | :--- | :--- |
| **Recovery Engine** | Crisis Autopilot | Automated FCFS dispatch for perishables during high-alert zones. |
| **AI Operations Advisor** | Pattern Analyzer | Monthly analytical nodes reviewing zone coverage gaps. |
| **DPDPA Compliance** | PII Purge | Automated 24h cleanup of ephemeral chat logs and precise coordinates. |
| **Governance** | Admin Gateway | High-level orchestration for city-wide resource distribution. |
| **Optimization** | Spatial Clustering | Real-time map of surplus hotspots for strategic planning. |
