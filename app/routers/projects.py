# app/routers/projects.py

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import List, Dict, Optional, Any
from beanie import PydanticObjectId

from app.routers.auth import get_current_user
from app.models.users import User  # your Beanie User document
from app.models.workitems import Board, Backlog, Epic, Issue, Project, BoardColumn, Sprint
from app.schemas.project_management import ProjectCreate, ProjectUpdate, ProjectOut, UserSummary, MemberSummary
from bson import ObjectId


def _link_id(link) -> Optional[str]:
    """
    Return string id from a Beanie Link/Document/ObjectId/None safely.
    Works whether the link is fetched or not.
    """
    if not link:
        return None
    if hasattr(link, "id"):
        try:
            return str(link.id)
        except Exception:
            pass
    if hasattr(link, "ref") and getattr(link.ref, "id", None) is not None:
        return str(link.ref.id)
    if isinstance(link, ObjectId):
        return str(link)
    try:
        return str(link)
    except Exception:
        return None


class BaseController:
    prefix: str = ""
    tags: list = []

    def __init__(self):
        self.router = APIRouter(prefix=self.prefix, tags=self.tags)
        self.setup_routes()

    def setup_routes(self):
        raise NotImplementedError

    async def ensure_admin(self, user: User):
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")


class ProjectsController(BaseController):
    prefix = "/projects"
    tags = ["projects"]

    def setup_routes(self):
        self.router.add_api_route("/", self.get_all, methods=["GET"], response_model=List[ProjectOut])
        self.router.add_api_route("/", self.create_project, methods=["POST"], response_model=ProjectOut)
        self.router.add_api_route("/{project_id}", self.get_project, methods=["GET"], response_model=ProjectOut)
        self.router.add_api_route("/{project_id}", self.update_project, methods=["PUT"], response_model=ProjectOut)
        self.router.add_api_route("/{project_id}", self.delete_project, methods=["DELETE"])

    async def _user_from_id(self, user_id):
        if not user_id:
            return None
        u = await User.get(str(user_id))
        if not u:
            raise HTTPException(status_code=400, detail=f"User not found: {user_id}")
        return u

    def _to_members_dict(self, member_roles_dict: Optional[Dict[str, str]]) -> Dict[str, str]:
        """
        Internally the model uses: Project.members: Dict[user_id, role]
        We only accept/emit member_roles in API. No separate 'members' list.
        """
        result: Dict[str, str] = {}
        if member_roles_dict:
            result.update({str(k): v for k, v in member_roles_dict.items()})
        return result

    async def to_response(self, project: Project) -> ProjectOut:
        """
        Convert Beanie Document (Links -> ids) and include detailed member & user info.
        """
        data: Dict[str, Any] = project.dict()
        data["id"] = str(project.id)

        async def user_info(user_link):
            if not user_link:
                return None
            uid = _link_id(user_link)
            user = await User.get(uid)
            if user:
                # try common name fields, fall back to username/display_name/first+last, then email prefix
                name = (
                    getattr(user, "name", None)
                    or getattr(user, "full_name", None)
                    or getattr(user, "display_name", None)
                    or getattr(user, "username", None)
                    or (" ".join(filter(None, [getattr(user, "first_name", ""), getattr(user, "last_name", "")]))).strip()
                )
                if not name:
                    email = getattr(user, "email", "") or ""
                    name = email.split("@", 1)[0] if "@" in email else ""
                return {
                    "id": str(user.id),
                    "name": name or "",
                    "email": getattr(user, "email", None),
                }
            return {"id": uid, "name": None, "email": None}

        data["project_lead"] = await user_info(project.project_lead)
        data["created_by"] = await user_info(project.created_by)
        data["updated_by"] = await user_info(project.updated_by)

        members_dict: Dict[str, str] = getattr(project, "members", {}) or {}
        detailed_members = []
        for user_id, role in members_dict.items():
            ui = await user_info(user_id)
            # ui can be None or dict with id,name,email
            detailed_members.append({
                "id": ui["id"] if ui else str(user_id),
                "name": (ui["name"] if ui else "") or "",
                "email": ui.get("email") if ui else None,
                "role": role,
            })

        data["members"] = detailed_members
        data.pop("member_roles", None)

        return ProjectOut(**data)

    async def create_defaults(self, project: Project):
        pid = str(project.id)

        existing_backlog = await Backlog.find_one({"project_id": pid})
        if not existing_backlog:
            await Backlog(project_id=pid).insert()

        existing_board = await Board.find_one({"project_id": pid})
        if not existing_board:
            board = Board(
                name="Project Board",
                project_id=pid,
                columns=[
                    BoardColumn(name="Backlog", status="backlog", position=0, color="#8B8B8B"),
                    BoardColumn(name="To Do", status="todo", position=1, color="#FF6B6B"),
                    BoardColumn(name="In Progress", status="in_progress", position=2, color="#4ECDC4"),
                    BoardColumn(name="In Review", status="in_review", position=3, color="#45B7D1"),
                    BoardColumn(name="Done", status="done", position=4, color="#96CEB4"),
                ],
                visible_to_roles=[],
            )
            await board.insert()

    async def get_all(
        self,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: User = Depends(get_current_user),
    ):
        await self.ensure_admin(current_user)
        projects = await Project.find(skip=skip, limit=limit).to_list()
        return [await self.to_response(p) for p in projects]

    async def get_project(self, project_id: str, current_user: User = Depends(get_current_user)):
        await self.ensure_admin(current_user)
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return await self.to_response(project)

    async def create_project(self, payload: ProjectCreate, current_user: User = Depends(get_current_user)):
        await self.ensure_admin(current_user)

        existing = await Project.find_one(Project.key == payload.key)
        if existing:
            raise HTTPException(status_code=400, detail="Project key already exists")

        if payload.project_lead:
            lead_doc = await self._user_from_id(payload.project_lead)
        else:
            lead_doc = current_user

        members_dict = self._to_members_dict(member_roles_dict=getattr(payload, "member_roles", None))

        data = {
            "key": payload.key,
            "name": payload.name,
            "description": payload.description,
            "avatar_url": payload.avatar_url,
            "platform": payload.platform,
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "project_lead": lead_doc,
            "members": members_dict,
            "created_by": current_user,
            "updated_by": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        project = Project(**data)
        await project.insert()
        await self.create_defaults(project)
        return await self.to_response(project)

    async def update_project(
        self,
        project_id: str,
        payload: ProjectUpdate,
        current_user: User = Depends(get_current_user),
    ):
        await self.ensure_admin(current_user)

        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        update = payload.dict(exclude_unset=True)

        if "project_lead" in update:
            pl_id = update.pop("project_lead")
            project.project_lead = await self._user_from_id(pl_id) if pl_id else None

        if "member_roles" in update:
            new_members = self._to_members_dict(update.pop("member_roles"))
            merged = dict(getattr(project, "members", {}) or {})
            merged.update(new_members)
            update["members"] = merged

        update["updated_at"] = datetime.utcnow()
        update["updated_by"] = current_user

        await project.set(update)
        return await self.to_response(project)

    async def delete_project(self, project_id: str, current_user: User = Depends(get_current_user)):
        await self.ensure_admin(current_user)
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        await project.delete()
        return {"message": "Project and related data deleted successfully"}


# helper to load a single user summary
async def _get_user_summary(user_id: Optional[PydanticObjectId | str]) -> Optional[UserSummary]:
    if not user_id:
        return None
    # normalize id
    try:
        uid = PydanticObjectId(user_id)
    except Exception:
        # already PydanticObjectId or invalid
        uid = user_id
    user = await User.get(uid)
    if not user:
        return UserSummary(id=str(uid), name="", email=None)
    # try common name fields used in your User model, fallback to email local part
    name = (
        getattr(user, "name", None)
        or getattr(user, "full_name", None)
        or getattr(user, "display_name", None)
        or getattr(user, "username", None)
        or (" ".join(filter(None, [getattr(user, "first_name", ""), getattr(user, "last_name", "")]))).strip()
    )
    if not name:
        email = getattr(user, "email", "") or ""
        name = email.split("@", 1)[0] if "@" in email else ""
    return UserSummary(id=str(user.id), name=name or "", email=getattr(user, "email", None))


# helper to build members list from stored member_roles dict (or other structure)
async def _build_members_from_roles(member_roles: Optional[Dict[str, str]]) -> List[MemberSummary]:
    if not member_roles:
        return []
    members: List[MemberSummary] = []
    # parallelize if needed; simple sequential for clarity
    for uid, role in member_roles.items():
        u = await _get_user_summary(uid)
        members.append(
            MemberSummary(
                id=u.id if u else str(uid),
                name=u.name if u else "",
                email=u.email if u else None,
                role=role,
                member_roles={str(uid): role},
            )
        )
    return members

# Example: when building the ProjectOut response (inside your GET endpoints or service)
# project is your DB model instance
# project_out = ProjectOut(
#     id=str(project.id),
#     key=project.key,
#     name=project.name,
#     description=project.description,
#     avatar_url=project.avatar_url,
#     platform=project.platform,
#     start_date=project.start_date,
#     end_date=project.end_date,
#     project_lead=await _get_user_summary(project.project_lead),
#     created_by=await _get_user_summary(project.created_by),
#     updated_by=await _get_user_summary(project.updated_by),
#     members=await _build_members_from_roles(getattr(project, "member_roles", {}) or {}),
#     epics_count=getattr(project, "epics_count", 0),
#     sprints_count=getattr(project, "sprints_count", 0),
#     issues_count=getattr(project, "issues_count", 0),
#     created_at=project.created_at,
#     updated_at=project.updated_at,
# )
# return project_out

# router export
projects_router = ProjectsController().router