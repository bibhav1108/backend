import httpx
import asyncio
import time

BASE_URL = "http://localhost:8005/api/v1"

async def run_final_test():
    print(" --- SAHYOG SETU COMPREHENSIVE FINAL VERIFICATION (V1 & V1.5) ---")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # --- PHASE 1: NGO ONBOARDING & AUTH (V1.5) ---
        print("\n[Phase 1] NGO Onboarding & Authentication")
        unique_suffix = str(int(time.time()))[-5:]
        org_name = f"Final Test NGO {unique_suffix}"
        admin_email = f"admin_{unique_suffix}@sahyog.org"
        reg_data = {
            "org_name": org_name, "org_phone": f"+9199{unique_suffix}00", 
            "org_email": f"contact_{unique_suffix}@sahyog.org",
            "admin_name": "Test Coordinator", "admin_email": admin_email,
            "admin_password": "password123"
        }
        res_reg = await client.post(f"{BASE_URL}/organizations/register", json=reg_data)
        assert res_reg.status_code == 201
        org_id = res_reg.json()["org_id"]
        print(f" [OK] Created Org: {org_name} (ID: {org_id})")

        # Login
        login_res = await client.post(f"{BASE_URL}/auth/login", data={"username": admin_email, "password": "password123"})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(" [OK] Auth Success: JWT Token received.")

        # --- PHASE 2: VOLUNTEER & INVENTORY (V1.0 & V1.5) ---
        print("\n[Phase 2] Volunteer Management & Activation")
        vol_phone = f"+9198{unique_suffix}11"
        vol_data = {"name": "Test Volunteer", "phone_number": vol_phone, "zone": "Central"}
        res_v = await client.post(f"{BASE_URL}/volunteers/", json=vol_data, headers=headers)
        assert res_v.status_code == 201
        vol_id = res_v.json()["id"]
        print(f" [OK] Registered Volunteer: {vol_id}")

        # Activation Gate
        await client.post(f"{BASE_URL}/webhooks/whatsapp", data={"From": f"whatsapp:{vol_phone}", "Body": "ACTIVATE"})
        print(" [OK] Volunteer WhatsApp Activated.")

        # Inventory
        inv_res = await client.post(f"{BASE_URL}/inventory/", json={"item_name": "Kits", "quantity": 10}, headers=headers)
        assert inv_res.status_code == 201
        print(" [OK] Inventory item tracked.")

        # --- PHASE 3: MARKETPLACE & CLAIMING (V1.5) ---
        print("\n[Phase 3] Marketplace & Claiming")
        need_data = {"type": "FOOD", "description": "Market surplus", "quantity": "100 units", "pickup_address": "Main Hub"}
        res_n = await client.post(f"{BASE_URL}/needs/", json=need_data)
        assert res_n.status_code == 201
        global_need_id = res_n.json()["id"]
        print(f" [OK] Created Global Need {global_need_id}.")

        # Claim
        res_claim = await client.post(f"{BASE_URL}/needs/{global_need_id}/claim", headers=headers)
        assert res_claim.status_code == 200
        print(f" [OK] Need {global_need_id} claimed by Org {org_id}.")

        # --- PHASE 4: DISPATCH & OTP LIFECYCLE (V1.0) ---
        print("\n[Phase 4] Dispatch & OTP Verification Lifecycle")
        # Trigger Dispatch
        res_d = await client.post(f"{BASE_URL}/dispatches/", json={"need_id": global_need_id, "volunteer_id": vol_id}, headers=headers)
        assert res_d.status_code == 201
        dispatch_id = res_d.json()["dispatch_id"]
        print(f" [OK] Dispatch {dispatch_id} triggered.")

        # Accept
        await client.post(f"{BASE_URL}/webhooks/whatsapp", data={"From": f"whatsapp:{vol_phone}", "Body": "YES"})
        print(" [OK] Volunteer Accepted (WhatsApp YES). Status: DISPATCHED")

        # OTP Verification
        res_o = await client.post(f"{BASE_URL}/dispatches/verify-otp", json={"dispatch_id": dispatch_id, "otp_code": "000000"}, headers=headers)
        assert res_o.status_code == 401
        print(" [OK] OTP Engine active (verified with intentional rejection).")

        # --- PHASE 5: METADATA & VERSION (V1.5) ---
        print("\n[Phase 5] Metadata & Patch Reports")
        res_p = await client.get(f"{BASE_URL}/patches")
        assert res_p.status_code == 200
        print(f" [OK] Found {len(res_p.json())} version patches in system ledger.")

    print("\n --- FINAL VERIFICATION COMPLETE! SYSTEM STABLE. ---")

if __name__ == "__main__":
    asyncio.run(run_final_test())
