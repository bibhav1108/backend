# 🚀 Sahyog Setu V2.0: Campaign System (Action Engine)
**Technical Handover for Frontend Developers**

The Campaign System (`NGO_Campaign`) is a proactive, team-based mission engine designed for structured NGO activities (e.g., Slum Schooling, Health Camps, Mass Food Distribution). 

Unlike the Marketplace (which is FCFS), Campaigns follow a **Strict Governance Flow** with an "Approval Gate."

---

## 🏗️ Core Models
1. **`NGO_Campaign`**: The master record (Name, Description, Type, Location, Timeline, Quota).
2. **`MissionTeam`**: The participation bridge. 
   - **PENDING**: Volunteer has "Opted-In" to help.
   - **APPROVED**: Admin has selected this volunteer for the final mission.
   - **REJECTED**: Admin has removed them from the pool.

---

## ⚙️ The 6-Step Action Lifecycle (UI Flow)

### 1. Identify (Create Mission)
**API**: `POST /api/v1/campaigns/`
- **Frontend Action**: A form to set the name, description (The "Why"), mission type (Education, Health, etc.), and location.
- **Key Field**: `volunteers_required` (The Quota).

### 2. Plan (Resource Allocation)
- **Frontend Action**: Link existing `Inventory` items to the campaign.
- **Logic**: When an item is linked, the backend updates **`reserved_quantity`** in the `Inventory` table.
- **Visual**: Show the user that these items are now "Locked" and cannot be used for other tasks.

### 3. Gather (Recruitment)
- **Frontend Action**: Toggle "Publish" to send the broadcast to the volunteer network via Telegram.
- **Volunteer View**: Volunteers see a "Join Mission" button in their bot. Clicking it adds them to the `MissionTeam` as `PENDING`.

### 4. Execute (The Approval Gate) 🛡️
**API**: `GET /api/v1/campaigns/{id}/participants` & `PATCH .../participants/{vol_id}`
- **Frontend Action**: A "Candidate Review" screen.
- **Critical UI**: The Admin sees a list of **PENDING** volunteers and clicks "Approve" for the top candidates until the `volunteers_required` quota is met.
- **Only APPROVED volunteers get the final location and mission instructions.**

### 5. Complete (Impact Sync)
**API**: `POST /api/v1/campaigns/{id}/complete`
- **Logic**: On completion, the system automatically:
  1. Deducts the `reserved_quantity` from the physical stock.
  2. Marks the Campaign as `COMPLETED`.
- **Frontend Action**: A "Finalize Mission" button with an optional text field for the final impact summary.

### 6. Report (Dashboard Analytics)
- **Frontend Action**: Display mission stats (Total volunteers, items used, total duration).

---

## 🔑 Critical Frontend Tips:
- **Status Badges**: Use distinct colors for `PLANNED` (Yellow), `ACTIVE` (Green), and `COMPLETED` (Blue).
- **Quota Meter**: Show a progress bar: `Approved (2) / Required (10)`.
- **Inventory Warning**: If the NGO tries to reserve more than what's available in `Inventory.quantity`, show a "Resource Shortage" warning.

---

**Sahyog Setu V2.0 is now ready for a high-impact dashboard UI!** 🏆🚀🌉✨
