# SahyogSync V2.1.0: AI Supervision Engine

This document outlines the core AI functionalities implemented to stabilize the marketplace flow and ensure high-tier data recovery.

## 1. Multi-Item Normalization Layer
**Problem**: Gemini often returns complex, nested JSON lists (especially for multi-item reports like "Rice and Dal"). The previous bot logic only expected a flat dictionary.
**Solution**: Implemented a normalization middleware in `webhooks.py`.
- **Logic**: Automatically detects keys like `donations` or `items`.
- **Consolidation**: Merges multiple rows into a single summary string for the NGO approval card.
- **Fail-Safe**: Ensures the output is always a flat dictionary before proceeding to UI rendering.

## 2. Inbound Deduplication Guard
**Problem**: Telegram retries (caused by minor server delays) were triggering 3-4 AI calls for a single donor report, exhausting the 5 RPM Gemini quota.
**Solution**: Created an `InboundMessage` ledger.
- **Logic**: Every incoming `chat_id` + `message_id` is logged in the database.
- **Protection**: If the same ID arrives again, the backend yields a `200 OK` instantly and skips AI processing.
- **Benefit**: Saves ~70% of API quota during high-traffic or unstable network scenarios.

## 3. Structured Persistent Storage
**Problem**: Recovered data was buried in raw text strings, making NGO dashboarding and auditing impossible.
**Solution**: Expanded the `MarketplaceAlert` schema.
- **Columns**: Added `item`, `quantity`, `location`, and `notes`.
- **Workflow**: The background task `process_ai_surplus_report` now saves structured JSON fields directly into these columns.
- **Result**: NGO Coordinators see clean columns on the dashboard instead of raw paragraphs.

## 4. Automated Conversion Logic
**Problem**: Manual address entry during "Alert -> Need" conversion was slow.
**Solution**: Mapped AI output to the Need Creation workflow.
- **Address Mapping**: `Alert.location` (AI) -> `MarketplaceNeed.pickup_address` (Core).
- **Description Mapping**: `Alert.item` (AI) -> `MarketplaceNeed.description` (Core).

## 6. Modular AI Agent Architecture (LangChain Powered)
**Problem**: As the system grows, putting all AI logic into a single file makes it unmaintainable and hard to test.
**Solution**: Created a dedicated `backend/app/agents/` package.
- **LangChain Integration**: Standardized on LangChain LCEL for building specialized mission agents.
- **Campaign Architect Agent**: 
    - **Persona**: NGO Mission Expert Assistant.
    - **Logic**: Automatically architectures a professional mission plan from a simple coordinator prompt.
    - **Output Mapping**: Maps natural language to `CampaignCreate` fields (Timeline, Resources, Skills, etc.).
- **Hybrid Workflow**: Introduced the `/draft` API endpoint which allows coordinators to get AI-suggested form values, review them on the dashboard, and then manually confirm/edit before launch.

## 7. Model & Framework Standards
- **Standard Model**: `gemini-2.5-flash` (Optimized for JSON extraction).
- **Core Framework**: LangChain (for prompt engineering and structured output parsing).
- **Versioning**: Version 2.1.0 "AI Supervision".

---
*Document Version: 1.2.0*
*Last Updated: 2026-04-09*
