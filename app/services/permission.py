from typing import Optional, Iterable

from app.models.users import User
from app.models.workitems import Project, Issue

# local helper (avoid importing routers)
def _id_of(obj):
    if obj is None:
        return None
    try:
        oid = getattr(obj, "id", None)
        if oid is not None:
            return str(oid)
    except Exception:
        pass
    try:
        ref = getattr(obj, "ref", None)
        if ref is not None:
            _id = getattr(ref, "id", None) or getattr(ref, "_id", None)
            if _id:
                return str(_id)
    except Exception:
        pass
    try:
        return str(obj)
    except Exception:
        return None


class PermissionService:
    @staticmethod
    async def _is_admin(user_id: str) -> bool:
        user = await User.get(user_id)
        return bool(user and getattr(user, "role", None) == "admin")

    @staticmethod
    async def _is_project_owner_or_member(proj: Project, user_id: str) -> bool:
        owner = getattr(proj, "owner", None)
        try:
            if owner and (str(owner) == str(user_id) or getattr(owner, "id", None) and str(getattr(owner, "id")) == str(user_id)):
                return True
        except Exception:
            pass

        members: Iterable = getattr(proj, "members", None) or getattr(proj, "team", None) or getattr(proj, "members_ids", None) or []
        for m in members or []:
            try:
                if str(m) == str(user_id):
                    return True
                if getattr(m, "id", None) and str(getattr(m, "id")) == str(user_id):
                    return True
                ref = getattr(m, "ref", None)
                if ref and getattr(ref, "id", None) and str(getattr(ref, "id")) == str(user_id):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    async def _is_employee_or_admin(user_id: Optional[str]) -> bool:
        """Return True for users with role 'admin' or 'employee'."""
        if not user_id:
            return False
        try:
            u = await User.get(str(user_id))
            return getattr(u, "role", None) in ("admin", "employee")
        except Exception:
            return False

    @staticmethod
    async def can_view_project(project_id: str, user_id: str) -> bool:
        if await PermissionService._is_employee_or_admin(user_id):
            return True
        if await PermissionService._is_admin(user_id):
            return True
        proj = await Project.get(project_id)
        if not proj:
            return False
        if await PermissionService._is_project_owner_or_member(proj, user_id):
            return True
        if getattr(proj, "public", False):
            return True
        return False

    @staticmethod
    async def can_edit_project(project_id: str, user_id: str) -> bool:
        if await PermissionService._is_employee_or_admin(user_id):
            return True
        if await PermissionService._is_admin(user_id):
            return True
        proj = await Project.get(project_id)
        if not proj:
            return False
        return await PermissionService._is_project_owner_or_member(proj, user_id)

    @staticmethod
    async def can_edit_workitem(issue_id: str, user_id: str) -> bool:
        if await PermissionService._is_employee_or_admin(user_id):
            return True
        if await PermissionService._is_admin(user_id):
            return True
        issue = await Issue.get(issue_id)
        if not issue:
            return False
        creator = getattr(issue, "created_by", None)
        if creator and (str(creator) == str(user_id) or getattr(creator, "id", None) and str(getattr(creator, "id")) == str(user_id)):
            return True
        assignee = getattr(issue, "assignee", None)
        if assignee and (str(assignee) == str(user_id) or getattr(assignee, "id", None) and str(getattr(assignee, "id")) == str(user_id)):
            return True
        proj_id = _id_of(issue.project)
        if proj_id and await PermissionService.can_edit_project(proj_id, user_id):
            return True
        return False

    @staticmethod
    async def can_comment(issue_id: str, user_id: str) -> bool:
        if await PermissionService._is_admin(user_id):
            return True
        if await PermissionService._is_employee_or_admin(user_id):
            return True
        issue = await Issue.get(issue_id)
        if not issue:
            return False
        proj_id = _id_of(issue.project)
        if proj_id and await PermissionService.can_view_project(proj_id, user_id):
            return True
        return False

    @staticmethod
    async def can_manage_sprint(project_id: str, user_id: str) -> bool:
        if await PermissionService._is_employee_or_admin(user_id):
            return True
        if await PermissionService._is_admin(user_id):
            return True
        proj = await Project.get(project_id)
        if not proj:
            return False
        return await PermissionService._is_project_owner_or_member(proj, user_id)