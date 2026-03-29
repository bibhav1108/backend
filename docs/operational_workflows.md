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

## 🔵 Version 2.1 - 3.0: Intelligence & Scale
*Strategic Allocation, DPDPA Security, and City Scale Crisis Autopilot.*
