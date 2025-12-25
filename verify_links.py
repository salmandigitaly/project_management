import asyncio
import httpx

BASE_URL = "http://localhost:8000/api/v1"

# Concept script for manual/assisted verification
async def verify():
    print("Verification plan for Generic Linking:")
    print("1. Create a Project and an Epic.")
    print("2. Create an Issue.")
    print("3. Link the Issue to the Epic with reason 'child'.")
    print("   POST /api/v1/links/ {source_id: issue_id, source_type: 'issue', target_id: epic_id, target_type: 'epic', reason: 'child'}")
    print("4. Verify link appears in GET /api/v1/links/?item_id={issue_id}")
    print("5. Verify link appears in GET /api/v1/links/?item_id={epic_id}")
    print("6. Link the Epic to another Epic with reason 'relates_to'.")
    print("7. Permanently delete a link and verify it's gone.")

if __name__ == "__main__":
    asyncio.run(verify())
