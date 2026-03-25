import asyncio
import httpx
import random
from datetime import datetime

BASE_URL = "http://localhost:8005/api/v1"

async def run_final_v1_test():
    async with httpx.AsyncClient() as client:
        print("\n🚀 --- Sahyog Setu V1.0 FINAL LIFECYCLE TEST ---")
        
        # Unique identifier for this test run
        suffix = str(random.randint(1000, 9999))
        phone = f"+91700700{suffix}"
        
        # 1. Register Volunteer
        print(f"\n[1] Registering Volunteer (Phone: {phone})...")
        resp = await client.post(f"{BASE_URL}/volunteers/", json={
            "name": f"Final Test Vol {suffix}",
            "phone_number": phone,
            "org_id": 1
        })
        assert resp.status_code == 201
        vol_id = resp.json()["id"]
        print(f"✅ Success. Volunteer ID: {vol_id}")

        # 2. Volunteer Activation (WhatsApp ACTIVATE)
        print("\n[2] Simulating WhatsApp Activation (ACTIVATE)...")
        resp = await client.post(f"{BASE_URL}/webhooks/whatsapp", data={
            "From": f"whatsapp:{phone}",
            "Body": "ACTIVATE"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "activated"
        print("✅ Account Activated.")

        # 3. Volunteer List & Filtering
        print("\n[3] Testing Volunteer List & Filtering...")
        resp = await client.get(f"{BASE_URL}/volunteers/?org_id=1&whatsapp_active=true")
        assert resp.status_code == 200
        active_vols = resp.json()
        assert any(v["id"] == vol_id for v in active_vols)
        print(f"✅ Volunteer {vol_id} is correctly listed as ACTIVE.")

        # 4. Create Need
        print("\n[4] Creating Need (FOOD)...")
        resp = await client.post(f"{BASE_URL}/needs/", json={
            "org_id": 1,
            "type": "FOOD",
            "description": "50 surplus packets",
            "quantity": "50 packets",
            "pickup_address": "Hazratganj, Lucknow"
        })
        assert resp.status_code == 201
        need_id = resp.json()["id"]
        print(f"✅ Need Created. ID: {need_id}")

        # 5. Trigger Dispatch (Manual)
        print(f"\n[5] Triggering Dispatch (Need:{need_id} -> Vol:{vol_id})...")
        resp = await client.post(f"{BASE_URL}/dispatches/", json={
            "need_id": need_id,
            "volunteer_id": vol_id
        })
        assert resp.status_code == 201
        dispatch_id = resp.json()["dispatch_id"]
        print(f"✅ Dispatch Alert Fired. Dispatch ID: {dispatch_id}")

        # 6. Volunteer Confirmation (WhatsApp YES)
        print("\n[6] Simulating Volunteer confirmation (YES)...")
        resp = await client.post(f"{BASE_URL}/webhooks/whatsapp", data={
            "From": f"whatsapp:{phone}",
            "Body": "YES"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"
        print("✅ Dispatch Confirmed. OTP Generated.")

        # 7. Security Test: OTP Brute Force (3 Attempts)
        print("\n[7] Testing OTP Security (3-Attempt Lock)...")
        for i in range(1, 4):
            resp = await client.post(f"{BASE_URL}/dispatches/verify-otp", json={
                "dispatch_id": dispatch_id,
                "otp_code": "000000"
            })
            print(f"  Attempt {i}: Status {resp.status_code} | Msg: {resp.json().get('detail')}")
            assert resp.status_code == 401

        # 8. Check 4th attempt (Lock)
        print("\n[8] Verifying 4th attempt is FORBIDDEN...")
        resp = await client.post(f"{BASE_URL}/dispatches/verify-otp", json={
            "dispatch_id": dispatch_id,
            "otp_code": "000000"
        })
        assert resp.status_code == 403
        print("✅ OTP Lock successfully triggered.")

        print("\n🎉 --- ALL V1.0 MODULES VERIFIED SUCCESSFULLY ---")

if __name__ == "__main__":
    asyncio.run(run_final_v1_test())
