import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.core.database import init_db
from app.models.workitems import Project, Issue, Sprint, Backlog
from app.models.users import User
from beanie import Link, PydanticObjectId
from datetime import datetime, timedelta

async def verify():
    print("🚀 Starting Global PM Verification...")
    await init_db()
    
    # 1. Setup Test Data
    # Get or create a test user
    test_user = await User.find_one(User.email == "test_global@example.com")
    if not test_user:
        test_user = User(email="test_global@example.com", full_name="Global Tester", hashed_password="pw", role="admin")
        await test_user.insert()
    
    # Create two projects
    p1 = await Project.find_one(Project.key == "GP1")
    if not p1:
        p1 = Project(key="GP1", name="Global Project 1", project_lead=test_user, created_by=test_user)
        await p1.insert()
        await Backlog(project_id=str(p1.id)).insert()

    p2 = await Project.find_one(Project.key == "GP2")
    if not p2:
        p2 = Project(key="GP2", name="Global Project 2", project_lead=test_user, created_by=test_user)
        await p2.insert()
        await Backlog(project_id=str(p2.id)).insert()

    # Create issues in both projects
    i1 = Issue(name="Issue 1 (P1)", project=p1, type="task", location="backlog", created_by=test_user)
    await i1.insert()
    
    i2 = Issue(name="Issue 2 (P2)", project=p2, type="task", location="backlog", created_by=test_user)
    await i2.insert()

    print(f"✅ Created test projects and issues: {i1.id} (P1), {i2.id} (P2)")

    # 2. Test Global Backlog Logic (Mocking the router logic)
    backlog_issues = await Issue.find(Issue.location == "backlog", Issue.is_deleted != True).to_list()
    print(f"✅ Found {len(backlog_issues)} issues in global backlog.")
    assert len(backlog_issues) >= 2

    # 3. Create a Global Sprint
    gs = Sprint(
        name="Common Sprint 1",
        project=None, # Global
        goal="Verify cross-project assignment",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=7),
        created_by=test_user,
        status="planned"
    )
    await gs.insert()
    print(f"✅ Created global sprint: {gs.id}")

    # 4. Assign issues from different projects
    i1.sprint = gs
    i1.location = "sprint"
    await i1.save()
    
    i2.sprint = gs
    i2.location = "sprint"
    await i2.save()
    
    gs.issue_ids = [i1.id, i2.id]
    await gs.save()
    print(f"✅ Assigned issues from P1 and P2 to global sprint.")

    # 5. Start Sprint
    gs.status = "running"
    gs.active = True
    await gs.save()
    
    for i in [i1, i2]:
        i.location = "board"
        await i.save()
    print(f"✅ Started sprint and moved issues to board.")

    # 6. Complete Sprint (logic check)
    # Mark i1 as done, i2 stays todo
    i1.status = "done"
    await i1.save()
    
    print("🏁 Completing sprint...")
    # Refresh objects
    issues = await Issue.find(Issue.sprint.id == gs.id).to_list()
    for i in issues:
        if i.status == "done":
            i.sprint = None
            i.location = "archived"
        else:
            i.sprint = None
            i.location = "backlog"
            # Add back to project backlog
            pid = str(i.project.id if hasattr(i.project, 'id') else i.project.ref.id)
            bl = await Backlog.find_one({"project_id": pid})
            if bl and i.id not in bl.items:
                bl.items.append(i.id)
                await bl.save()
        await i.save()
    
    gs.active = False
    gs.status = "completed"
    await gs.save()
    
    # Final check
    i1_refreshed = await Issue.get(i1.id)
    i2_refreshed = await Issue.get(i2.id)
    
    print(f"📊 Final Status - i1: {i1_refreshed.location}, i2: {i2_refreshed.location}")
    assert i1_refreshed.location == "archived"
    assert i2_refreshed.location == "backlog"
    
    print("✨ Global PM Verification Successful!")

if __name__ == "__main__":
    asyncio.run(verify())
