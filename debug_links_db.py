import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def debug_links():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client.get_default_database()
    collection = db["linked_work_items"]
    
    print("Checking 'linked_work_items' collection...")
    links = await collection.find({}).to_list(length=100)
    print(f"Total links found: {len(links)}")
    for l in links:
        print(l)

if __name__ == "__main__":
    asyncio.run(debug_links())
