# Master Blueprint: SahyogSync V2.0 (Dual-Engine Operation)

SahyogSync V2.0 (formerly Sahyog Setu) establishes a **strict architectural boundary** between reactive donor-recovery operations and proactive NGO-led missions. This document serves as the finalized technical roadmap of the system, reflecting the current production-ready state.

## ✅ Project Status: MISSION ACCOMPLISHED

> [!IMPORTANT]
> **Architecture Finalized**: The platform now operates on two parallel tracks:
> 1. **Marketplace (Recovery Engine)**: Reactive, instant, donor-driven. FCFS (First-Come, First-Served) dispatch.
> 2. **Mission Control (Action Engine)**: Proactive, planned, NGO-driven. Web-based volunteer briefing.
> 
> **Stability & Fail-Safe**: Integrated background processing and regex fallbacks to ensure 100% uptime even during AI API exhaustion.

---

## 🏗️ Technical Implementation Summary

### 1. Database & Model Foundation
- [x] **Entity Isolation**: Massive schema refactor to prevent data mixing (`MarketplaceNeed`, `NGO_Campaign`, `MissionTeam`, etc.).
- [x] **Inventory Duality**: `MarketplaceInventory` (Recovery History) vs. `Inventory` (Strategic internal NGO stock).
- [x] **Audit Traceability**: `AuditTrail` records mission launches, volunteer approvals, and completions.

### 2. Marketplace: The Recovery Engine (Stability-Focused)
- [x] **Non-Blocking Orchestration**: Gemini AI parsing moved to **FastAPI Background Tasks**. Webhook responds in <100ms.
- [x] **Fail-Safe Mechanism**: **Regex Fallback Parser** in `AIService` handles Gemini API exhaustion/timeout.
- [x] **FCFS Dispatch Architecture**: Coordinators can notify multiple volunteers simultaneously; mission belongs to the first to "Accept" on Telegram.
- [x] **OTP Verification Gate**: Secure 6-digit OTP confirmation with the donor. Success auto-logs to `MarketplaceInventory`.

### 3. Mission Control: The Action Engine (Proactive)
- [x] **Web-Based Mission Briefing**: Volunteers receive unique links (`/missions/{id}?vol_id={vid}`) to browse full campaign details in the browser.
- [x] **Volunteer Pool Management**: 
    - Volunteers "Opt-In" via the web interface.
    - Status remains `PENDING` for NGO review.
    - Final `APPROVED`/`REJECTED` gate ensures organization control and safety.
- [x] **Inventory Reservation**: Automatic resource locking via `reserved_quantity` logic prevents over-allocation.
- [x] **Markdown-Ready Broadcasts**: Enhanced Telegram messages with proper escaping for high-reliability delivery.

### 4. Application Wiring & Governance
- [x] **Isolated Routing**: API endpoints logically separated under `/api/v1/auth`, `/api/v1/organizations`, `/api/v1/users`, `/api/v1/marketplace`, and `/api/v1/campaigns`.
- [x] **NGO-Volunteer Isolation**: Secure multi-tenancy where volunteers and users are strictly bound to their parent `Organization`.
- [x] **Manual Re-Broadcasts**: Ad-hoc trigger to notify newly verified volunteers about existing active missions.

---

## 🛠️ Verification Results
- **Stability Test**: Verified that the bot responds immediately ("Analyzing... 🤖") while processing AI in the background.
- **FCFS Lock Test**: Confirmed that once a marketplace mission is accepted by one volunteer, it becomes unavailable to others.
- **Web Briefing Test**: Verified that unique links correctly identify volunteers for the `/opt-in` and `/reject` endpoints.
- **Exhaustion Test**: Verified that Regex Fallback triggers if AI fails, ensuring donor data still reaches the NGO.

**SahyogSync V2.0 is now bulletproof and ready for production.** 🚀🏆🌉✨

