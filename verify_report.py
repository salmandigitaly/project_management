import asyncio
import json
from app.core.database import init_db
from app.models.workitems import Project
from app.services.report_service import ReportService

async def main():
    await init_db()
    
    # 1. Get first project
    project = await Project.find_one()
    if not project:
        print("No projects found in DB.")
        return

    print(f"Testing report for project: {project.name} ({project.id})")
    
    # 2. Generate Report
    report = await ReportService.generate_project_report(str(project.id))
    
    # 3. Print verification
    print(json.dumps(report, indent=2, default=str))

    # Basic Checks
    if "project_summary" in report:
        print("\n✅ Project Summary Present")
        print(f"   Completion: {report['project_summary']['completion_percentage']}%")
    else:
         print("\n❌ Project Summary Missing")

    if "work_items_status" in report:
        print("✅ Work Items Status Present")
    
    if "types_of_work" in report:
        print("✅ Types of Work Present")
        types = report["types_of_work"]
        print(f"   Types found: {[t['type'] for t in types]}")

    if "member_contributions" in report:
        print(f"✅ Member Contributions Present ({len(report['member_contributions'])} members)")

if __name__ == "__main__":
    asyncio.run(main())
