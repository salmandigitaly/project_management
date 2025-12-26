import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.core.database import init_db
from app.models.workitems import Project, Issue, Sprint
from app.models.users import User
from beanie.operators import In
from datetime import datetime, timedelta

async def verify():
    print("🚀 Starting Completed Sprints Issue Verification...")
    await init_db()
    
    # 1. Setup Test Data
    test_user = await User.find_one(User.email == "test_global@example.com")
    
    p1 = await Project.find_one(Project.key == "GP1")
    
    # Create issues
    i1 = Issue(name="Completed Issue A", project=p1, type="task", status="done", created_by=test_user)
    await i1.insert()
    
    i2 = Issue(name="Rolled Over Issue B", project=p1, type="task", status="todo", created_by=test_user)
    await i2.insert()

    # Create and Assign to Global Sprint
    gs = Sprint(
        name="Sprint with History",
        project=None,
        goal="Verify issue history",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=7),
        created_by=test_user,
        status="running",
        active=True,
        issue_ids=[i1.id, i2.id]
    )
    await gs.insert()
    
    # Link issues back to sprint (simulating assignments)
    i1.sprint = gs
    await i1.save()
    i2.sprint = gs
    await i2.save()

    # 2. Complete Sprint
    # (Mocking completion logic)
    i1.sprint = None
    i1.location = "archived"
    await i1.save()
    
    i2.sprint = None
    i2.location = "backlog"
    await i2.save()
    
    gs.status = "completed"
    gs.active = False
    gs.completed_at = datetime.utcnow()
    await gs.save()
    
    print(f"✅ Sprint {gs.name} completed with {len(gs.issue_ids)} issues in snapshot.")

    # 3. Test the Endpoint Logic
    # (Mocking router GET /global/sprints/completed)
    sprints = await Sprint.find(
        Sprint.project == None,
        Sprint.status == "completed"
    ).to_list()
    
    found_gs = next((s for s in sprints if s.id == gs.id), None)
    assert found_gs is not None
    
    issue_details = []
    if found_gs.issue_ids:
        issues = await Issue.find(In(Issue.id, found_gs.issue_ids)).to_list()
        for i in issues:
            issue_details.append(i.name)
    
    print(f"✅ Found issues in completed sprint for response: {issue_details}")
    assert "Completed Issue A" in issue_details
    assert "Rolled Over Issue B" in issue_details

    print("✨ Completed Sprints Issue Verification Successful!")

if __name__ == "__main__":
    asyncio.run(verify())
