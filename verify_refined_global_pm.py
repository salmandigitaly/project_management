import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.core.database import init_db
from app.models.workitems import Project, Issue, Sprint, Backlog, Board
from app.models.users import User
from beanie import Link, PydanticObjectId
from datetime import datetime, timedelta

async def verify():
    print("🚀 Starting Refined Global PM Verification...")
    await init_db()
    
    # 1. Setup Test Data
    test_user = await User.find_one(User.email == "test_global@example.com")
    if not test_user:
        test_user = User(email="test_global@example.com", full_name="Global Tester", hashed_password="pw", role="admin")
        await test_user.insert()
    
    # 2. Test Global Sprint Creation (No project)
    gs = Sprint(
        name="Pure Global Sprint",
        project=None,
        goal="Verify separate board",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=7),
        created_by=test_user,
        status="planned"
    )
    await gs.insert()
    print(f"✅ Created pure global sprint: {gs.id}")

    # 3. Verify Isolation (Router logic mock)
    planned_global_sprints = await Sprint.find(
        Sprint.project == None,
        Sprint.status != "completed",
        Sprint.is_deleted != True
    ).to_list()
    print(f"✅ Found {len(planned_global_sprints)} planned global sprints.")
    assert any(s.id == gs.id for s in planned_global_sprints)

    # 4. Test Global Board Creation
    # This simulates calling GET /global/board/{sprint_id}
    board = await Board.find_one(Board.sprint_id == str(gs.id))
    if not board:
        board = Board(
            name=f"Global Board - {gs.name}",
            project_id=None,
            sprint_id=str(gs.id),
            columns=[
                {"name": "To Do", "status": "todo", "position": 1, "color": "#FF6B6B"},
                {"name": "In Progress", "status": "in_progress", "position": 2, "color": "#4ECDC4"},
                {"name": "Done", "status": "done", "position": 3, "color": "#96CEB4"},
            ]
        )
        await board.insert()
    print(f"✅ Created global board for sprint: {board.id}")
    assert board.project_id is None
    assert board.sprint_id == str(gs.id)

    # 5. Test Global Completed Sprints
    gs.status = "completed"
    gs.completed_at = datetime.utcnow()
    await gs.save()
    
    completed_global_sprints = await Sprint.find(
        Sprint.project == None,
        Sprint.status == "completed",
        Sprint.is_deleted != True
    ).to_list()
    print(f"✅ Found {len(completed_global_sprints)} completed global sprints.")
    assert any(s.id == gs.id for s in completed_global_sprints)

    print("✨ Refined Global PM Verification Successful!")

if __name__ == "__main__":
    asyncio.run(verify())
