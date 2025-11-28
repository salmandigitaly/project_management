# import asyncio
# import sys
# from bson import ObjectId
# from motor.motor_asyncio import AsyncIOMotorClient
# from app.core.config import settings

# async def add_member(project_id: str, user_id: str):
#     client = AsyncIOMotorClient(settings.MONGODB_URL)
#     db = client.get_database(settings.DB_NAME)
#     await db["projects"].update_one(
#         {"_id": ObjectId(project_id)},
#         {"$addToSet": {"members": ObjectId(user_id)}}
#     )
#     print(f"Added user {user_id} to project {project_id}")

# if __name__ == "__main__":
#     if len(sys.argv) != 3:
#         print("Usage: python add_member.py <PROJECT_ID> <USER_ID>")
#         sys.exit(1)
#     PROJECT_ID, USER_ID = sys.argv[1], sys.argv[2]
#     asyncio.run(add_member(PROJECT_ID, USER_ID))