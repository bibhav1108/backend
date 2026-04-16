# SahyogSync V2.1.0: AI Supervision Engine

This document outlines the core AI intelligence implemented to stabilize the platform's dual engines: **Marketplace** and **Campaigns**.

---

## 🔵 Marketplace Engine (Reactive Layer)
*Goal: Ensuring high-fidelity recovery of donor surplus through intelligent parsing and deduplication.*

### 1. Multi-Item Normalization Layer
- **Problem**: Gemini often returns complex JSON lists for multi-item reports (e.g., "Rice and Dal"), which could break legacy UI cards.
- **Solution**: A normalization middleware in `webhooks.py` that merges nested items into a single, clean summary card.
- **Benefit**: Ensures 100% UI stability for complex donation reports.

### 2. Inbound Deduplication Guard
- **Problem**: Telegram retries were triggering 3-4 AI calls for a single report, wasting Gemini quota.
- **Solution**: A database-backed `InboundMessage` ledger that skips AI processing for duplicate Message IDs.
- **Benefit**: Saves ~70% of API quota and shields the system from "retry-storms".

### 3. Structured Persistent Storage
- **Problem**: Donation data was trapped in raw text, making it unauditable.
- **Solution**: AI now extracts data directly into dedicated DB columns (`item`, `quantity`, `location`, `notes`).
- **Benefit**: Instant visibility of marketplace inventory and structured NGO dashboards.

---

## 🟢 Campaign Engine (Proactive Layer)
*Goal: Accelerating mission planning through modular agents and natural language architecture.*

### 1. AI Campaign Architect (LangChain)
- **Problem**: Manually filling out 10+ fields for a new campaign is slow and prone to errors.
- **Solution**: A dedicated `CampaignAgent` that uses LangChain to architect a specialized mission plan from a single natural language goal.
- **Persona**: Acts as an "NGO Mission Expert Assistant".

### 2. Hybrid Draft Workflow (`/draft` API)
- **Logic**: Instead of auto-saving, the AI generates a **Structured Draft**.
- **Dashboard Integration**: The dashboard pre-fills the "Create Campaign" form using this draft, allowing the coordinator to fine-tune and then Launch.

### 3. Modular Agent Package
- **Location**: `backend/app/agents/`
- **Scalability**: Decouples mission-specific intelligence from core services, allowing for easy expansion as we add more specialized agents (e.g., InventoryAgent).

---

## ⚙️ Shared Model Configuration
- **Standard Model**: `gemini-2.5-flash` (Optimized for JSON extraction).
- **Core Framework**: LangChain (for Persona-based prompt engineering).
- **Versioning**: Version 2.1.0 "AI Supervision".

---
*Document Version: 1.3.0*
*Last Updated: 2026-04-09*
