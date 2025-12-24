import asyncio
import httpx

BASE_URL = "http://localhost:8000/api/v1"

# Note: You'll need a valid token to run this.
# This is a conceptual script to guide the user or for me to run if I had a token.
# Since I don't have a token, I'll provide instructions for manual verification via Swagger.

async def verify():
    print("Verification plan for Recycle Bin:")
    print("1. Create a Project via POST /projects/")
    print("2. Create an Issue via POST /issues/")
    print("3. Verify project and issue are visible in lists.")
    print("4. Delete the Issue via DELETE /issues/{id}")
    print("5. Verify Issue is NOT in /issues/ but IS in /recycle-bin/")
    print("6. Restore the Issue via POST /recycle-bin/restore/issue/{id}")
    print("7. Verify Issue is back in /issues/")
    print("8. Delete the Project via DELETE /projects/{id}")
    print("9. Verify Project and its Issue are in /recycle-bin/")
    print("10. Permanently delete Project as admin via DELETE /recycle-bin/permanent/project/{id}")

if __name__ == "__main__":
    asyncio.run(verify())
