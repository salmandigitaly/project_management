import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import MONGO_URI, DB_NAME
from datetime import datetime, timezone

async def main():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    users = db.users
    year = datetime.utcnow().year

    # find current max DIGI suffix
    cursor = users.find({'emp_id': {'$regex': '^DIGI'}}, {'emp_id': 1}).sort('emp_id', -1)
    max_n = 0
    async for doc in cursor:
        v = doc.get('emp_id') or ''
        digits = ''.join(ch for ch in v if ch.isdigit())
        if digits:
            try:
                n = int(digits)
                if n > max_n:
                    max_n = n
            except Exception:
                continue
    next_n = max_n + 1

    async for u in users.find({}):
        updates = {}
        if not u.get('emp_id'):
            updates['emp_id'] = f"DIGI{next_n:04d}"
            next_n += 1
        if not u.get('leave_balances'):
            updates['leave_balances'] = [{
                'year': year,
                'casual_leave': 12,
                'sick_leave': 10,
                'last_updated': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
            }]
        if updates:
            await users.update_one({'_id': u['_id']}, {'$set': updates})
            print("Updated", u.get('email'), updates)

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())