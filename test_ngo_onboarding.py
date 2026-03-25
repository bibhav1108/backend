import httpx
import asyncio

BASE_URL = "http://localhost:8005/api/v1"

async def test_ngo_onboarding():
    print("--- Testing NGO Onboarding Flow ---")
    async with httpx.AsyncClient() as client:
        # 1. Register NGO
        print("\nStep 1: Registering New NGO 'Helping Hands'...")
        reg_data = {
            "org_name": "Helping Hands NGO",
            "org_phone": "+911122334455",
            "org_email": "contact@helpinghands.org",
            "admin_name": "Sarah Connor",
            "admin_email": "sarah@helpinghands.org",
            "admin_password": "superSecretPassword123"
        }
        resp = await client.post(f"{BASE_URL}/organizations/register", json=reg_data)
        if resp.status_code != 201:
            print(f"❌ Registration Failed: {resp.text}")
        assert resp.status_code == 201
        org_id = resp.json()["org_id"]
        print(f"✅ NGO Registered. ID: {org_id}")

        # 2. Login with New Credentials
        print("\nStep 2: Logging in with new Coordinator credentials...")
        login_data = {
            "username": "sarah@helpinghands.org",
            "password": "superSecretPassword123"
        }
        resp = await client.post(f"{BASE_URL}/auth/login", data=login_data)
        if resp.status_code != 200:
            print(f"❌ Login Failed: {resp.text}")
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        assert resp.json()["org_id"] == org_id
        print(f"✅ Login Successful. Token received for Org {org_id}.")

    print("\n--- NGO ONBOARDING TEST PASSED ---")

if __name__ == "__main__":
    asyncio.run(test_ngo_onboarding())
