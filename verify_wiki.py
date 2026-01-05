import asyncio
import httpx
import os
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

BASE_URL = "http://127.0.0.1:8000/api/v1"

async def verify_wiki():
    print("--- Starting Wiki Feature Verification ---")
    
    # 1. Get test user and project from DB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client.get_default_database()
    user_doc = await db.users.find_one({"role": "admin"})
    if not user_doc:
        user_doc = await db.users.find_one()
    
    project_doc = await db.projects.find_one()
    
    if not user_doc or not project_doc:
        print("❌ Could find test user or project")
        return

    email = user_doc["email"]
    password = "admin" # Assumption for local testing
    project_id = str(project_doc["_id"])
    
    async with httpx.AsyncClient() as http_client:
        # Login
        url = f"{BASE_URL}/login"
        print(f"Attempting login at: {url}")
        login_res = await http_client.post(url, json={"email": email, "password": password})
        print(f"Login response status: {login_res.status_code}")
        
        if login_res.status_code != 200:
            url = f"{BASE_URL}/auth/login"
            print(f"Attempting login at alternative: {url}")
            login_res = await http_client.post(url, json={"email": email, "password": password})
            print(f"Alternative login status: {login_res.status_code}")
            
        if login_res.status_code != 200:
            print(f"❌ Login failed: {login_res.text}")
            return
        
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Create Parent Wiki Page
        print("Creating parent wiki page...")
        parent_res = await http_client.post(
            f"{BASE_URL}/projects/{project_id}/wiki",
            headers=headers,
            json={
                "title": "Main Documentation",
                "content": "# Project Overview\nThis is the root documentation page."
            }
        )
        if parent_res.status_code != 200:
            print(f"❌ Parent page creation failed: {parent_res.text}")
            return
        
        parent_page = parent_res.json()
        parent_id = parent_page["id"]
        print(f"✅ Parent page created: {parent_id}")

        # 3. Create Child Wiki Page
        print("Creating child wiki page...")
        child_res = await http_client.post(
            f"{BASE_URL}/projects/{project_id}/wiki",
            headers=headers,
            json={
                "title": "Setup Guide",
                "content": "## Steps\n1. Install Python\n2. Run app",
                "parent_id": parent_id
            }
        )
        if child_res.status_code != 200:
            print(f"❌ Child page creation failed: {child_res.text}")
            return
        print(f"✅ Child page created: {child_res.json()['id']}")

        # 4. Upload Wiki Asset (Image)
        print("Uploading wiki asset...")
        test_img_path = "test_wiki_img.png"
        with open(test_img_path, "wb") as f:
            f.write(b"fake image data")
            
        with open(test_img_path, "rb") as f:
            files = {"file": (test_img_path, f, "image/png")}
            asset_res = await http_client.post(
                f"{BASE_URL}/projects/{project_id}/wiki/assets/upload",
                headers=headers,
                files=files
            )
            
        if asset_res.status_code != 200:
            print(f"❌ Asset upload failed: {asset_res.text}")
        else:
            asset_data = asset_res.json()
            print(f"✅ Asset uploaded: {asset_data['id']}")
            asset_url = f"{BASE_URL}/projects/{project_id}/wiki/assets/{asset_data['id']}"
            print(f"🔗 Asset URL: {asset_url}")

        # 5. List Wiki (Verification of Tree structure)
        print("Fetching wiki tree...")
        list_res = await http_client.get(f"{BASE_URL}/projects/{project_id}/wiki", headers=headers)
        if list_res.status_code != 200:
            print(f"❌ List failed: {list_res.text}")
        else:
            tree = list_res.json()
            print(f"✅ Tree structure retrieved. Root pages: {len(tree)}")
            if len(tree) > 0 and len(tree[0]["children"]) > 0:
                print("✅ Hierarchy verified (child found inside parent)")
            else:
                print("❌ Hierarchy verification failed")

        # Cleanup test files
        if os.path.exists(test_img_path):
            os.remove(test_img_path)

if __name__ == "__main__":
    asyncio.run(verify_wiki())
