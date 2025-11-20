from app.models.workitems import Project, Issue
from app.models.users import User
from app.models.workitems import Issue  # Add this import
class PermissionService:
    @staticmethod
    async def can_view_project(project_id: str, user_id: str) -> bool:
        project = await Project.get(project_id)
        if not project:
            return False

        user = await User.get(user_id)
        if not user:
            return False

        if user.role == "admin":
            return True

        try:
            if project.project_lead and str(project.project_lead.id) == user_id:
                return True
        except Exception:
            pass

        # ✅ use project.members (dict of user_id -> role)
        return user_id in (project.members or {})

    @staticmethod
    async def can_manage_sprint(project_id: str, user_id: str) -> bool:
        project = await Project.get(project_id)
        if not project:
            return False

        user = await User.get(user_id)
        if not user:
            return False

        if user.role == "admin":
            return True

        try:
            if project.project_lead and str(project.project_lead.id) == user_id:
                return True
        except Exception:
            pass

        # ✅ use project.members
        role = (project.members or {}).get(user_id)
        return role in {"scrum_master", "project_admin"}
    @staticmethod
    async def can_edit_project(project_id: str, user_id: str) -> bool:
        project = await Project.get(project_id)
        if not project:
            return False

        user = await User.get(user_id)
        if not user:
            return False

        if user.role == "admin":
            return True

        try:
            if project.project_lead and str(project.project_lead.id) == user_id:
                return True
        except Exception:
            pass

        # ✅ use project.members (dict of user_id -> role)
        role = (project.members or {}).get(user_id)
        return role in {"scrum_master", "project_admin", "admin"}
    

    @staticmethod
    async def can_edit_workitem(issue_id: str, user_id: str) -> bool:
        """
        Check if user can edit a specific workitem (issue)
        """
        issue = await Issue.get(issue_id)
        if not issue:
            return False

        user = await User.get(user_id)
        if not user:
            return False

        # Admin can edit any issue
        if user.role == "admin":
            return True

        # Project lead can edit any issue in their project
        project = await issue.project.fetch()
        if project.project_lead and str(project.project_lead.id) == user_id:
            return True

        # Assignee can edit their own assigned issues
        if issue.assignee and str(issue.assignee.id) == user_id:
            return True

        # User can edit issues they created
        if issue.created_by and str(issue.created_by.id) == user_id:
            return True

        # Check project member roles
        role = (project.members or {}).get(user_id)
        if role in {"scrum_master", "project_admin", "developer"}:
            return True

        return False