import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"
LOGIN_URL = "http://localhost:8000/api/v1/login"

REGISTER_URL = "http://localhost:8000/api/v1/auth/register"

def register(email, password):
    print(f"Attempting to register {email}...")
    resp = requests.post(REGISTER_URL, json={
        "email": email, 
        "password": password,
        "full_name": "Test Verifier",
        "role": "admin",
        "is_active": True
    })
    if resp.status_code == 200:
        print("Registration success")
        return True
    elif resp.status_code == 400 and "already registered" in resp.text:
        print("User already registered")
        return True
    else:
        print(f"Registration failed: {resp.text}")
        return False

def login(email, password):
    resp = requests.post(LOGIN_URL, json={"email": email, "password": password})
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        # Try to register and login again
        if register(email, password):
             resp = requests.post(LOGIN_URL, json={"email": email, "password": password})
             if resp.status_code != 200:
                 print(f"Login failed after registration: {resp.text}")
                 sys.exit(1)
        else:
            sys.exit(1)
    return resp.json()["access_token"]

def main():
    token = login("test_verifier@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    print("Creating/Getting Project...")
    resp = requests.get(f"{BASE_URL}/projects/", headers=headers)
    projects = resp.json()
    if projects:
        project_id = projects[0]["id"]
        print(f"Using existing project: {project_id}")
    else:
        resp = requests.post(f"{BASE_URL}/projects/", json={"name": "Comment Test Project", "key": "CTP", "description": "Test"}, headers=headers)
        if resp.status_code != 200:
            print(f"Create project failed: {resp.text}")
            sys.exit(1)
        project_id = resp.json()["id"]
        print(f"Created project: {project_id}")

    # 1. Test Project Comment (Auto-author, explicit project_id)
    print("Commenting on Project...")
    comment_data = {
        "project_id": project_id,
        "comment": "Project Comment Verification"
    }
    resp = requests.post(f"{BASE_URL}/comments/", json=comment_data, headers=headers)
    if resp.status_code != 200:
        print(f"Comment failed: {resp.text}")
        sys.exit(1)
    print("Project comment success")

    print("Verifying Project Comment...")
    resp = requests.get(f"{BASE_URL}/projects/{project_id}", headers=headers)
    project_data = resp.json()
    comments = project_data.get("comments", [])
    print(f"Project Comments Count: {len(comments)}")
    if len(comments) > 0 and "author_name" in comments[0]:
        print(f"✅ Project Comment Verified. Author: {comments[0]['author_name']}")
    else:
        print("❌ Project Comment Verification Failed")

    # 2. Test Epic Comment (Auto-author, inferred project_id)
    print("Creating Epic...")
    epic_data = {"name": "Test Epic", "project_id": project_id}
    resp = requests.post(f"{BASE_URL}/epics/", json=epic_data, headers=headers)
    epic_id = resp.json()["id"]
    print(f"Epic ID: {epic_id}")

    print("Commenting on Epic (Inferred Project)...")
    comment_data = {
        "epic_id": epic_id,
        "comment": "Epic Comment Verification"
    }
    resp = requests.post(f"{BASE_URL}/comments/", json=comment_data, headers=headers)
    if resp.status_code != 200:
        print(f"Comment failed: {resp.text}")
        sys.exit(1)
    print("Epic comment success")

    print("Verifying Epic Comment...")
    resp = requests.get(f"{BASE_URL}/epics/{epic_id}", headers=headers)
    epic_data = resp.json()
    comments = epic_data.get("comments", [])
    print(f"Epic Comments Count: {len(comments)}")
    if len(comments) > 0 and "author_name" in comments[0]:
        print(f"✅ Epic Comment Verified. Author: {comments[0]['author_name']}")
    else:
        print("❌ Epic Comment Verification Failed")

    # 3. Test Sprint Comment
    print("Creating Sprint...")
    sprint_data = {"name": "Test Sprint", "project_id": project_id, "start_date": "2023-01-01T00:00:00", "end_date": "2023-01-14T00:00:00"}
    resp = requests.post(f"{BASE_URL}/sprints/", json=sprint_data, headers=headers)
    sprint_id = resp.json()["id"]
    print(f"Sprint ID: {sprint_id}")

    print("Commenting on Sprint...")
    comment_data = {
        "sprint_id": sprint_id,
        "comment": "Sprint Comment Verification"
    }
    resp = requests.post(f"{BASE_URL}/comments/", json=comment_data, headers=headers)
    if resp.status_code != 200:
        print(f"Comment failed: {resp.text}")
        sys.exit(1)
    print("Sprint comment success")

    print("Verifying Sprint Comment...")
    resp = requests.get(f"{BASE_URL}/sprints/{sprint_id}", headers=headers)
    sprint_data = resp.json()
    comments = sprint_data.get("comments", [])
    print(f"Sprint Comments Count: {len(comments)}")
    if len(comments) > 0 and "author_name" in comments[0]:
        print(f"✅ Sprint Comment Verified. Author: {comments[0]['author_name']}")
    else:
        print("❌ Sprint Comment Verification Failed")

    # 4. Test Issue Comment
    print("Creating Issue...")
    issue_data = {"name": "Test Issue", "project_id": project_id, "type": "story", "priority": "medium", "status": "todo"}
    resp = requests.post(f"{BASE_URL}/issues/", json=issue_data, headers=headers)
    if resp.status_code != 200:
        print(f"Create issue failed: {resp.text}")
        sys.exit(1)
    issue_id = resp.json()["id"]
    print(f"Issue ID: {issue_id}")

    print("Commenting on Issue...")
    comment_data = {
        "issue_id": issue_id,
        "comment": "Issue Comment Verification"
    }
    resp = requests.post(f"{BASE_URL}/comments/", json=comment_data, headers=headers)
    if resp.status_code != 200:
        print(f"Comment failed: {resp.text}")
        sys.exit(1)
    print("Issue comment success")

    print("Verifying Issue Comment...")
    resp = requests.get(f"{BASE_URL}/issues/{issue_id}", headers=headers)
    issue_data = resp.json()
    comments = issue_data.get("comments", [])
    print(f"Issue Comments Count: {len(comments)}")
    if len(comments) > 0 and "author_name" in comments[0]:
        print(f"✅ Issue Comment Verified. Author: {comments[0]['author_name']}")
    else:
        print("❌ Issue Comment Verification Failed")

if __name__ == "__main__":
    main()
