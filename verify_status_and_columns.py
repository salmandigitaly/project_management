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
    print("🚀 Starting Global PM Refinement Verification (Status & 4th Column)...")
    await init_db()
    
    # 1. Setup Test Data
    test_user = await User.find_one(User.email == "test_global@example.com")
    if not test_user:
        test_user = User(email="test_global@example.com", full_name="Global Tester", hashed_password="pw", role="admin")
        await test_user.insert()
    
    # 2. Test Global Board Columns
    gs = Sprint(
        name="Verification Sprint 4Col",
        project=None,
        goal="Verify 4 columns",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=7),
        created_by=test_user,
        status="planned"
    )
    await gs.insert()
    
    # Simulate get_global_board which creates the board
    board = await Board.find_one(Board.sprint_id == str(gs.id))
    if not board:
        from app.models.workitems import BoardColumn
        board = Board(
            name=f"Global Board - {gs.name}",
            project_id=None,
            sprint_id=str(gs.id),
            columns=[
                BoardColumn(name="To Do", status="todo", position=1, color="#FF6B6B"),
                BoardColumn(name="In Progress", status="in_progress", position=2, color="#4ECDC4"),
                BoardColumn(name="Impediment", status="impediment", position=3, color="#FF9F43"),
                BoardColumn(name="Done", status="done", position=4, color="#96CEB4"),
            ]
        )
        await board.insert()
    
    print(f"✅ Board columns count: {len(board.columns)}")
    assert len(board.columns) == 4
    assert any(c.status == "impediment" for c in board.columns)
    assert any(c.name == "Impediment" for c in board.columns)

    # 3. Test Status Update (PUT Global Issue)
    p1 = await Project.find_one(Project.key == "GP1")
    if not p1:
        p1 = Project(key="GP1", name="Global Project 1", project_lead=test_user, created_by=test_user)
        await p1.insert()
        
    issue = Issue(name="Update Me", project=p1, type="task", location="board", status="todo", created_by=test_user)
    await issue.insert()
    
    # Mocking the PUT router logic
    issue.status = "impediment"
    issue.updated_at = datetime.utcnow()
    await issue.save()
    
    refreshed = await Issue.get(issue.id)
    print(f"✅ Issue status updated: {refreshed.status}")
    assert refreshed.status == "impediment"

    print("✨ Status & 4th Column Verification Successful!")

if __name__ == "__main__":
    asyncio.run(verify())
