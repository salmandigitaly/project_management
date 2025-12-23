import asyncio
from app.core.database import init_db
from app.models.workitems import Board, BoardColumn
from app.routers.boards import BoardsRouter
from app.models.users import User
from beanie import PydanticObjectId

async def main():
    await init_db()
    
    # Clean up any existing boards
    await Board.find_all().delete()

    print(" Creating Test Board...")
    # Create a test board
    board = Board(
        name="Reorder Test",
        project_id=str(PydanticObjectId()),
        columns=[
            BoardColumn(name="A", status="a", position=0),
            BoardColumn(name="B", status="b", position=1),
            BoardColumn(name="C", status="c", position=2)
        ]
    )
    await board.insert()
    print(f"Board created with columns: {[c.name for c in board.columns]}")
    
    # Mock Permission Service
    from app.services.permission import PermissionService
    async def mock_check(*args, **kwargs): return True
    PermissionService.can_edit_project = mock_check

    # Mock Router instance
    controller = BoardsRouter()
    
    # Mock User
    user = User(id=PydanticObjectId(), email="test@test.com", hashed_password="pw", role="admin")

    print("\n--- TEST 1: Swap A(0) and B(1) ---")
    
    payload = {"new_order": [1, 0, 2]}
    try:
        res = await controller.reorder_columns(str(board.id), payload, current_user=user)
        print("Success:", res)
        
        # Verify DB
        updated_board = await Board.get(board.id)
        names = [c.name for c in updated_board.columns]
        print("New Column Order:", names)
        
        if names == ["B", "A", "C"]:
            print("✅ TEST 1 PASSED")
        else:
             print("❌ TEST 1 FAILED")

    except Exception as e:
        print(f"❌ TEST 1 ERROR: {e}")


    print("\n--- TEST 2: Duplicate check (Should Fail) ---")
    payload_bad = {"new_order": [0, 0, 2]}
    try:
        await controller.reorder_columns(str(board.id), payload_bad, current_user=user)
        print("❌ TEST 2 FAILED (Should have raised error)")
    except Exception as e:
        print(f"✅ TEST 2 PASSED (Caught expected error: {e})")

if __name__ == "__main__":
    asyncio.run(main())
