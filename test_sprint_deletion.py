"""
Test script to verify sprint deletion moves issues to backlog
"""
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"
LOGIN_URL = "http://localhost:8000/api/v1/login"
REGISTER_URL = "http://localhost:8000/api/v1/auth/register"

def register():
    response = requests.post(REGISTER_URL, json={
        "email": "test@example.com",
        "password": "test123",
        "full_name": "Test User",
        "role": "admin",
        "is_active": True
    })
    if response.status_code == 200:
        print("✅ User registered successfully")
        return True
    elif response.status_code == 400 and "already registered" in response.text:
        print("✅ User already registered")
        return True
    else:
        print(f"Registration response: {response.text}")
        return False

def login():
    response = requests.post(LOGIN_URL, json={
        "email": "test@example.com",
        "password": "test123"
    })
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        # Try to register if login fails
        print("Login failed, attempting to register...")
        if register():
            # Try login again
            response = requests.post(LOGIN_URL, json={
                "email": "test@example.com",
                "password": "test123"
            })
            if response.status_code == 200:
                return response.json()["access_token"]
        print(f"Login failed: {response.text}")
        return None

def test_sprint_deletion_moves_issues():
    token = login()
    if not token:
        print("❌ Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n=== Testing Sprint Deletion with Issue Preservation ===\n")
    
    # 1. Get or create a project
    print("1. Getting project...")
    projects = requests.get(f"{BASE_URL}/projects", headers=headers).json()
    if not projects:
        print("❌ No projects found")
        return
    project_id = projects[0]["id"]
    print(f"✅ Using project: {project_id}")
    
    # 2. Create a sprint
    print("\n2. Creating sprint...")
    sprint_data = {
        "name": "Test Sprint for Deletion",
        "project_id": project_id,
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-01-14T00:00:00"
    }
    sprint_response = requests.post(f"{BASE_URL}/sprints", json=sprint_data, headers=headers)
    if sprint_response.status_code != 200:
        print(f"❌ Failed to create sprint: {sprint_response.text}")
        return
    sprint_id = sprint_response.json()["id"]
    print(f"✅ Created sprint: {sprint_id}")
    
    # 3. Create issues in the sprint
    print("\n3. Creating issues in sprint...")
    issue_ids = []
    for i in range(3):
        issue_data = {
            "project_id": project_id,
            "sprint_id": sprint_id,
            "type": "task",
            "name": f"Test Issue {i+1}",
            "description": f"Test issue {i+1} for sprint deletion",
            "priority": "medium",
            "location": "sprint"
        }
        issue_response = requests.post(f"{BASE_URL}/issues", json=issue_data, headers=headers)
        if issue_response.status_code == 200:
            issue_id = issue_response.json()["id"]
            issue_ids.append(issue_id)
            print(f"✅ Created issue {i+1}: {issue_id}")
        else:
            print(f"❌ Failed to create issue {i+1}: {issue_response.text}")
    
    if not issue_ids:
        print("❌ No issues created")
        return
    
    print(f"\n✅ Created {len(issue_ids)} issues in sprint")
    
    # 4. Delete the sprint
    print(f"\n4. Deleting sprint {sprint_id}...")
    delete_response = requests.delete(f"{BASE_URL}/sprints/{sprint_id}", headers=headers)
    if delete_response.status_code != 200:
        print(f"❌ Failed to delete sprint: {delete_response.text}")
        return
    
    result = delete_response.json()
    print(f"✅ Sprint deleted")
    print(f"   Message: {result.get('message')}")
    print(f"   Issues moved to backlog: {result.get('issues_moved_to_backlog', 0)}")
    
    # 5. Verify issues are in backlog
    print("\n5. Verifying issues moved to backlog...")
    moved_count = 0
    for issue_id in issue_ids:
        issue_response = requests.get(f"{BASE_URL}/issues/{issue_id}", headers=headers)
        if issue_response.status_code == 200:
            issue = issue_response.json()
            if issue.get("location") == "backlog" and issue.get("sprint_id") is None:
                moved_count += 1
                print(f"✅ Issue {issue_id}: location={issue.get('location')}, sprint_id={issue.get('sprint_id')}")
            else:
                print(f"❌ Issue {issue_id}: location={issue.get('location')}, sprint_id={issue.get('sprint_id')}")
        else:
            print(f"❌ Issue {issue_id} not found (might have been deleted)")
    
    print(f"\n{'='*50}")
    if moved_count == len(issue_ids):
        print(f"✅ SUCCESS: All {moved_count} issues moved to backlog")
    else:
        print(f"❌ FAILED: Only {moved_count}/{len(issue_ids)} issues moved to backlog")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    test_sprint_deletion_moves_issues()
