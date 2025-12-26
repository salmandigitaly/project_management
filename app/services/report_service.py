import logging
from typing import Dict, Any, List
from datetime import datetime
from collections import Counter

from app.models.workitems import Project, Issue, Epic, Sprint, Feature
from app.models.users import User

from beanie.operators import In

logger = logging.getLogger(__name__)

class ReportService:
    @staticmethod
    async def generate_project_report(project_id: str) -> Dict[str, Any]:
        """
        Aggregates data for the Project Completion Report.
        """
        try:
            # 1. Fetch Project
            project = await Project.get(project_id)
            if not project:
                return {"error": "Project not found"}
            
            # Fetch all issues for this project
            # We fetch all at once to minimize DB calls for the breakdown steps
            issues = await Issue.find(Issue.project.id == project.id).to_list()
            
            # 2. Project Summary
            # Calculate total time spent (sum of issue.time_spent_hours)
            total_time_spent = sum(i.time_spent_hours for i in issues if i.time_spent_hours)
            
            # Check for completed issues (assuming 'done' status is completed)
            total_issues_count = len(issues)
            completed_issues_count = len([i for i in issues if i.status == 'done'])
            completion_percentage = 0.0
            if total_issues_count > 0:
                completion_percentage = round((completed_issues_count / total_issues_count) * 100, 1)

            lead_email = "Unassigned"
            if project.project_lead:
                try:
                    # check if already fetched (if it's a User instance) or fetch it
                    if isinstance(project.project_lead, User):
                         lead_email = project.project_lead.email
                    else:
                         # It is a Link
                         lead = await project.project_lead.fetch()
                         if lead:
                             lead_email = lead.email
                except Exception:
                    pass

            project_summary = {
                "id": str(project.id),
                "name": project.name,
                "lead": lead_email,
                "start_date": project.start_date,
                "end_date": project.end_date,
                "completion_percentage": completion_percentage,
                "total_hours_spent": round(total_time_spent, 2)
            }

            # 3. Work Items Status Overview (Doughnut Chart)
            # "status" field in Issue model. Common values: todo, in_progress, in_review, done, backlog
            # Note: The user might have different status keys so we normalize/count them.
            
            status_counts = Counter(i.status for i in issues)
            # Ensure we have keys for the requested dashboard view even if 0
            target_statuses = ["todo", "in_progress", "impediment", "done", "backlog"]
            
            status_breakdown = []
            for s in target_statuses:
                count = status_counts.get(s, 0)
                pct = 0.0
                if total_issues_count > 0:
                    pct = round((count / total_issues_count) * 100, 1)
                status_breakdown.append({
                    "status": s,
                    "count": count,
                    "percentage": pct
                })
            
            # Add any other statuses found that are not in target_statuses? 
            # For strict dashboard matching, we might focus on these, but good to encompass all.
            # For now, let's strictly return the breakdown list as requested.

            work_items_status = {
                "total": total_issues_count,
                "completed": completed_issues_count,
                "breakdown": status_breakdown
            }

            # 4. Types of Work (Epics, Features, Stories, Tasks, Bugs, Subtasks)
            # We need to fetch Epics and Features counts separately
            epics_count = await Epic.find(Epic.project.id == project.id).count()
            features_count = await Feature.find(Feature.project_id == project.id).count()
            
            # From 'issues' list, breakdown by 'type': story, task, bug, subtask
            type_counts = Counter(i.type for i in issues)
            
            # Total work items for "Types of work" chart = Epics + Features + All Issues associated? 
            # Or just filter the issues? The image shows "Epic", "Story", "Task", "Sub-task", "Bug".
            # So total = epics + features + issues.
            total_work_types = epics_count + features_count + total_issues_count
            
            types_of_work = []
            
            # Helper to add type entry
            def add_type_entry(label, count):
                pct = 0.0
                if total_work_types > 0:
                    pct = round((count / total_work_types) * 100, 1)
                types_of_work.append({
                    "type": label,
                    "count": count,
                    "percentage": pct
                })

            add_type_entry("Epic", epics_count)
            add_type_entry("Feature", features_count)
            # Issue types
            for t in ["story", "task", "subtask", "bug"]:
                count = type_counts.get(t, 0)
                # Dashboard label mapping
                label = t.capitalize()
                if t == "subtask": label = "Sub-task"
                add_type_entry(label, count)

            # 5. Priority Breakdown
            # Priority values: highest, high, medium, low, lowest
            priority_counts = Counter(i.priority for i in issues)
            # ensure all keys present
            priority_order = ["highest", "high", "medium", "low", "lowest"]
            issues_breakdown_by_priority = {}
            for p in priority_order:
                issues_breakdown_by_priority[p] = priority_counts.get(p, 0)

            # 6. Epic Progress
            # We need to list all epics and their individual progress
            # Progress = (completed issues in epic / total issues in epic) * 100
            epics = await Epic.find(Epic.project.id == project.id).to_list()
            epics_progress = []
            
            for epic in epics:
                # find issues for this epic
                # In-memory filter specific to this epic found in the bulk list
                # Issue model has 'epic' field which is a Link.
                # efficiently we can do this by ID comparison
                epic_issues = [
                    i for i in issues 
                    if i.epic and (
                        (hasattr(i.epic, 'id') and i.epic.id == epic.id) or 
                        (hasattr(i.epic, 'ref') and i.epic.ref.id == epic.id)
                    )
                ]
                
                e_total = len(epic_issues)
                e_completed = len([i for i in epic_issues if i.status == 'done'])
                e_progress = 0.0
                if e_total > 0:
                    e_progress = round((e_completed / e_total) * 100, 1)
                
                epics_progress.append({
                    "id": str(epic.id),
                    "name": epic.name,
                    "progress": e_progress,
                    "total_issues": e_total,
                    "completed_issues": e_completed
                })

            # 7. Sprint Performance
            sprints = await Sprint.find(Sprint.project.id == project.id).to_list()
            sprint_performance = []
            for sp in sprints:
                # issues are linked via 'issue_ids' (PydanticObjectId list) or potentially backlink 'issues'
                # The model definition showed: issue_ids: List[PydanticObjectId]
                
                # We can filter the main 'issues' list by checking if their ID is in sp.issue_ids
                sp_issue_ids = set(str(sid) for sid in sp.issue_ids)
                sp_issues = [i for i in issues if str(i.id) in sp_issue_ids]
                
                sp_total = len(sp_issues)
                sp_completed = len([i for i in sp_issues if i.status == 'done'])
                
                sprint_performance.append({
                    "name": sp.name,
                    "status": sp.status, # active, closed, planned
                    "total_issues": sp_total,
                    "completed_issues": sp_completed
                })
            
            # 8. Member Contributions (Team Workload)
            # Group by assignee
            member_stats = {}
            for i in issues:
                assignee_name = "Unassigned"
                if i.assignee:
                     # Since it is a Link, we might need to fetch if not populated.
                     # efficient way: if we strictly needed names we should have fetched with populate,
                     # or we assume we can get it from the Link if it was fetched.
                     # However, 'issues' query above didn't use aggregate/lookup so Link might be just ID.
                     # Let's rely on Beanie logic. If i.assignee is a DBRef/Link, we might need a separate resolution strategy 
                     # if performance is key.
                     # For now, let's assume we group by ID and then fetch User names or just label "Unassigned".
                     # If i.assignee is populated (unlikely without fetch_links=True), use it.
                     pass

            # Improve Member Stats:
            # We need to fetch users involved. 
            # To avoid N+1, unique user IDs from issues
            user_ids = set()
            for i in issues:
                # Safe Link ID access
                aid = None
                if i.assignee:
                     aid = getattr(i.assignee, "id", None)
                     if not aid and hasattr(i.assignee, "ref"):
                         aid = getattr(i.assignee.ref, "id", None)
                if aid:
                    user_ids.add(aid)
             
            # Fetch users
            users_map = {}
            if user_ids:
                users = await User.find(In(User.id, list(user_ids))).to_list()
                users_map = {u.id: u.full_name or u.email for u in users}

            raw_member_stats = {} # {user_id: {assigned, completed, hours}}
            
            # Add Unassigned
            raw_member_stats["unassigned"] = {"name": "Unassigned", "assigned": 0, "completed": 0, "hours": 0.0}

            for i in issues:
                uid = "unassigned"
                if i.assignee:
                     aid = getattr(i.assignee, "id", None)
                     if not aid and hasattr(i.assignee, "ref"):
                         aid = getattr(i.assignee.ref, "id", None)
                     if aid:
                         uid = aid
                
                if uid != "unassigned" and uid not in raw_member_stats:
                    name = users_map.get(uid, "Unknown")
                    raw_member_stats[uid] = {"name": name, "assigned": 0, "completed": 0, "hours": 0.0}
                
                raw_member_stats[uid]["assigned"] += 1
                if i.status == 'done':
                    raw_member_stats[uid]["completed"] += 1
                if i.time_spent_hours:
                    raw_member_stats[uid]["hours"] += i.time_spent_hours

            member_contributions = list(raw_member_stats.values())

            # 9. Recent Activities (Top 10 recently modified issues)
            # Sort issues by updated_at descending
            sorted_issues = sorted(
                issues, 
                key=lambda x: x.updated_at if x.updated_at else datetime.min, 
                reverse=True
            )
            recent_activities = []
            for i in sorted_issues[:10]:
                recent_activities.append({
                    "id": str(i.id),
                    "key": getattr(i, "key", ""),
                    "name": i.name,
                    "type": i.type,
                    "status": i.status,
                    "updated_at": i.updated_at
                })

            return {
                "project_summary": project_summary,
                "work_items_status": work_items_status,
                "types_of_work": types_of_work,
                "issues_breakdown_by_priority": issues_breakdown_by_priority,
                "epics_progress": epics_progress,
                "sprint_performance": sprint_performance,
                "member_contributions": member_contributions,
                "recent_activities": recent_activities
            }

        except Exception as e:
            logger.error(f"Error generating report for project {project_id}: {e}")
            return {"error": str(e)}
