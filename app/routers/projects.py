# app/routers/projects.py
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from datetime import datetime
from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import Project
# typing helpers and fallback Any marker used by this module
from typing import List, Optional, Dict, Any as _Any, Any
from app.services.permission import PermissionService
# try to import related models for populating lists; fallback to _Any if missing
try:
    from app.models.workitems import Epic, Sprint, Issue , Feature
    from app.models.workitems import Comment, TimeEntry, LinkedWorkItem
except Exception:
    Epic = Sprint = Issue = _Any

# safe imports for Pydantic models / helpers that may live in other modules.
# If your project defines these in different modules, replace the try/except targets.
try:
    from app.schemas.project_management import ProjectOut, ProjectCreate, ProjectUpdate
except Exception:
    # fallback: try the other schema module used in this repo
    try:
        from app.schemas.project_management import ProjectOut, ProjectCreate, ProjectUpdate
    except Exception:
        ProjectOut = ProjectCreate = ProjectUpdate = _Any

try:
    from beanie import PydanticObjectId
except Exception:
    PydanticObjectId = _Any

try:
    from app.models.workitems import Backlog, Board, BoardColumn
except Exception:
    Backlog = Board = BoardColumn = _Any

try:
    from app.schemas.users import UserSummary, MemberSummary
except Exception:
    UserSummary = MemberSummary = _Any

from bson import ObjectId
from bson.dbref import DBRef
import logging

logger = logging.getLogger(__name__)

# helper: normalize a Link / object / id to string id
def _link_id(link):
    """Return string id from Link / Document / str / ObjectId-like objects."""
    if not link:
        return None
    # if it's already a string or ObjectId-like, return str()
    try:
        # beanie Link/document: may have .id or .ref.id
        if getattr(link, "id", None):
            return str(getattr(link, "id"))
        ref = getattr(link, "ref", None)
        if ref and getattr(ref, "id", None):
            return str(getattr(ref, "id"))
        # some Link wrappers may expose .link_id or ._id
        if getattr(link, "link_id", None):
            return str(getattr(link, "link_id"))
        if getattr(link, "_id", None):
            return str(getattr(link, "_id"))
    except Exception:
        pass
    # fallback to string conversion
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
        self.router.add_api_route("/{project_id}/members", self.assign_member, methods=["POST"], response_model=ProjectOut)
        self.router.add_api_route("/{project_id}/members/{user_id}", self.remove_member, methods=["DELETE"], response_model=ProjectOut)
# ...existing code...

    async def _user_from_id(self, user_id):
        if not user_id:
            return None
        try:
            u = await User.get(str(user_id))
            if not u:
                raise HTTPException(status_code=400, detail=f"User not found: {user_id}")
            return u
        except Exception as e:
            # Catch validation errors (invalid ObjectId format) and other errors
            error_msg = str(e)
            if "ValidationError" in str(type(e)) or "PydanticObjectId" in error_msg or "Id must be of type" in error_msg:
                raise HTTPException(status_code=400, detail=f"Invalid user ID format: {user_id}")
            raise HTTPException(status_code=400, detail=f"User not found: {user_id}")

    def _to_members_dict(self, member_roles_dict: Optional[Dict[str, str]]) -> Dict[str, str]:
        """
        Internally the model uses: Project.members: Dict[user_id, role]
        We only accept/emit member_roles in API. No separate 'members' list.
        """
        result: Dict[str, str] = {}
        if member_roles_dict:
            result.update({str(k): v for k, v in member_roles_dict.items()})
        return result

    async def to_response(self, project: Project) -> _Any:
        """
        Convert Beanie Document (Links -> ids) and include detailed member & user info.
        """
        data: Dict[str, Any] = project.dict()
        data["id"] = str(project.id)

        # helper: get user document (best-effort) and return summary dict
        async def _get_user_summary_dict(user_link):
            if not user_link:
                return None
            uid = _link_id(user_link)
            if not uid:
                return None
            user = None
            # Try Beanie.get with PydanticObjectId, then fallback to find_one by _id
            try:
                if PydanticObjectId is not _Any:
                    user = await User.get(PydanticObjectId(str(uid)))
                else:
                    user = await User.get(str(uid))
            except Exception:
                try:
                    user = await User.find_one({"_id": ObjectId(str(uid))})
                except Exception:
                    try:
                        user = await User.find_one({"_id": uid})
                    except Exception:
                        user = None

            if not user:
                return {"id": uid, "name": "", "email": None}

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

            return {"id": str(getattr(user, "id", uid)), "name": name or "", "email": getattr(user, "email", None)}

        data["project_lead"] = await _get_user_summary_dict(project.project_lead)
        data["created_by"] = await _get_user_summary_dict(project.created_by)
        data["updated_by"] = await _get_user_summary_dict(project.updated_by)

        members_dict: Dict[str, str] = getattr(project, "members", {}) or {}
        detailed_members = []
        for user_id, role in members_dict.items():
            ui = await _get_user_summary_dict(user_id)
            detailed_members.append({
                "id": ui["id"] if ui else str(user_id),
                "name": (ui["name"] if ui else "") or "",
                "email": ui.get("email") if ui else None,
                "role": role,
            })

        data["members"] = detailed_members
        data.pop("member_roles", None)

        # populate related lists (epics/sprints/issues) with lightweight summaries
        # safe: only run if model import succeeded
        epics_list = []
        epics_count = 0
        if Epic is not _Any:
            async for e in Epic.find():
                if _link_id(getattr(e, "project", None)) == str(project.id):
                    epics_list.append({"id": str(getattr(e, "id", None)), "title": getattr(e, "title", getattr(e, "name", None))})
                    epics_count += 1
        data["epics"] = epics_list
        data["epics_count"] = epics_count

        features_list = []
        features_count = 0
        if Feature is not _Any:
            try:
                async for f in Feature.find(Feature.project_id == str(project.id)):
                    features_list.append({"id": str(f.id), "name": getattr(f, "name", None)})
                    features_count += 1
            except Exception:
                pass
        data["features"] = features_list
        data["features_count"] = features_count

        sprints_list = []
        sprints_count = 0
        if Sprint is not _Any:
            async for s in Sprint.find():
                if _link_id(getattr(s, "project", None)) == str(project.id):
                    sprints_list.append({"id": str(getattr(s, "id", None)), "name": getattr(s, "name", None)})
                    sprints_count += 1
        data["sprints"] = sprints_list
        data["sprints_count"] = sprints_count

        issues_list = []
        issues_count = 0
        subtasks_count = 0
        if Issue is not _Any:
            try:
                # use raw motor collection to avoid Beanie model validation errors
                col = Issue.get_motor_collection()
                async for doc in col.find({"project": ObjectId(str(project.id))}):
                    issue_type = doc.get("type", "")
                    if issue_type == "subtask":
                        subtasks_count += 1
                    else:
                        issues_count += 1
                    issues_list.append({
                        "id": str(doc.get("_id")),
                        "title": doc.get("title") or doc.get("summary") or ""
                    })
            except Exception:
                # fallback: leave issues_list empty on any error
                issues_list = []
        data["issues"] = issues_list
        data["issues_count"] = issues_count
        data["subtasks_count"] = subtasks_count

        # populate comments (project-level only)
        comments_list = []
        if Comment is not _Any:
            try:
                # Fetch comments
                comments = await Comment.find(
                    Comment.project.id == project.id,
                    Comment.epic == None,
                    Comment.issue == None,
                    Comment.sprint == None
                ).to_list()
                
                for c in comments:
                    author_name = None
                    if c.author:
                        try:
                            # Try to get from loaded doc or fetch
                            if getattr(c.author, "full_name", None):
                                author_name = c.author.full_name
                            elif getattr(c.author, "email", None):
                                author_name = c.author.email
                            else:
                                # fetch
                                uid = _link_id(c.author)
                                if uid:
                                    u = await User.get(uid)
                                    if u:
                                        author_name = u.full_name or u.email
                        except Exception:
                            pass
                    comments_list.append({
                        "id": str(c.id),
                        "project_id": _link_id(c.project),
                        "epic_id": _link_id(getattr(c, "epic", None)),
                        "sprint_id": _link_id(getattr(c, "sprint", None)),
                        "issue_id": _link_id(c.issue),
                        "author_id": _link_id(c.author),
                        "author_name": author_name,
                        "comment": c.comment,
                        "created_at": getattr(c, "created_at", None),
                    })
            except Exception:
                pass
        data["comments"] = comments_list

        # If ProjectOut is the fallback Any (_Any) we cannot instantiate it.
        # Return plain dict in that case; otherwise construct the Pydantic model.
        if ProjectOut is _Any:
            return data
        try:
            return ProjectOut(**data)
        except Exception:
            # If construction fails for any reason, return plain dict as a safe fallback
            return data

    async def create_defaults(self, project: Project):
        pid = str(project.id)

        # create backlog: prefer Backlog model, fallback to raw motor collection
        try:
            if Backlog is not _Any:
                existing_backlog = await Backlog.find_one({"project_id": pid})
                if not existing_backlog:
                    await Backlog(project_id=pid, items=[]).insert()
            else:
                # fallback: insert into the "backlogs" collection using motor (best-effort)
                try:
                    col = Project.get_motor_collection().database.get_collection("backlogs")
                    existing = await col.find_one({"project_id": pid})
                    if not existing:
                        await col.insert_one({"project_id": pid, "items": []})
                except Exception:
                    # ignore motor errors; not critical
                    pass
        except Exception:
            # defensive: never raise from defaults creation
            pass

        # create board & columns if Board model exists
        try:
            if Board is not _Any and BoardColumn is not _Any:
                existing_board = await Board.find_one({"project_id": pid})
                if not existing_board:
                    board = Board(
                        name="Project Board",
                        project_id=pid,
                        columns=[
                            # BoardColumn(name="Backlog", status="backlog", position=0, color="#8B8B8B"),
                            BoardColumn(name="To Do", status="todo", position=1, color="#FF6B6B"),
                            BoardColumn(name="In Progress", status="in_progress", position=2, color="#4ECDC4"),
                            BoardColumn(name="Impediment", status="impediment", position=3, color="#FF6B6B"),
                            BoardColumn(name="Done", status="done", position=4, color="#96CEB4"),
                        ],
                        visible_to_roles=[],
                    )
                    await board.insert()
            else:
                # models missing: skip board creation
                pass
        except Exception:
            pass

    async def get_all(
        self,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: User = Depends(get_current_user),
    ):
        """
        Admin: return all projects (paged).
        Non-admin: return only projects the user can view (owner/member/public).
        """
        out = []
        async for p in Project.find().skip(skip).limit(limit):
            # admin sees everything
            if getattr(current_user, "role", None) == "admin":
                allowed = True
            else:
                allowed = await PermissionService.can_view_project(str(p.id), str(getattr(current_user, "id", None)))
            if not allowed:
                continue
            out.append(await self.to_response(p))
        return out

    async def get_project(self, project_id: str, current_user: User = Depends(get_current_user)):
        proj = await Project.get(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")

        # allow admin OR owner/member OR public projects
        if not await PermissionService.can_view_project(project_id, str(getattr(current_user, "id", None))):
            raise HTTPException(status_code=403, detail="No access to project")
        
        # return full detailed response using the shared to_response converter
        return await self.to_response(proj)

    async def create_project(self, payload: ProjectCreate = Body(...), current_user: User = Depends(get_current_user)):
        """
        Create project — payload is a JSON body matching ProjectCreate schema.
        """
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
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # permission check (keep yours)
        # robust permission check: try several possible method names on PermissionService,
        # fall back to admin role if none found.
        perm_fn = None
        for name in ("can_manage_project", "can_manage_projects", "can_delete_project", "can_manage", "can_view_project"):
            candidate = getattr(PermissionService, name, None)
            if callable(candidate):
                perm_fn = candidate
                break

        if callable(perm_fn):
            try:
                # common signature: (project_id, user_id)
                allowed = await perm_fn(project_id, str(current_user.id))
            except TypeError:
                # try swapped args if signature differs
                try:
                    allowed = await perm_fn(str(current_user.id), project_id)
                except Exception:
                    allowed = False
            except Exception:
                allowed = False
        else:
            allowed = getattr(current_user, "role", None) == "admin"

        if not allowed:
            raise HTTPException(status_code=403, detail="No access to delete project")

        # --- cascade delete related documents explicitly (motor delete_many) ---
        async def _cascade_delete_by_model(model):
            try:
                col = model.get_motor_collection()
            except Exception:
                return
            qs = []
            try:
                oid = ObjectId(str(project_id))
                qs += [{"project": oid}, {"project.$id": oid}, {"project.id": oid}, {"project": DBRef("projects", oid)}]
            except Exception:
                pass
            qs += [{"project": str(project_id)}, {"project_id": str(project_id)}, {"project.id": str(project_id)}, {"project.$id": str(project_id)}]
            # run delete_many for all query shapes
            for q in qs:
                try:
                    await col.delete_many(q)
                except Exception:
                    pass
            # ensure project_id cleanup
            try:
                await col.delete_many({"project_id": str(project_id)})
            except Exception:
                pass

        # models to clean up (imported at top of file)
        cleanup = [Epic, Feature, Issue, Sprint, Board, Backlog, Comment, TimeEntry, LinkedWorkItem]
        for m in cleanup:
            try:
                await _cascade_delete_by_model(m)
            except Exception as e:
                logger.exception("Cascade error for %s: %s", getattr(m, "__name__", str(m)), str(e))

        # finally remove the project document
        await project.delete()

        # ensure child documents removed (force cleanup to cover shapes missed by handlers)
        try:
            await _delete_project_children(project_id)
        except Exception as e:
            logger.exception("Project cleanup failed: %s", str(e))

        return {"message": "Project deleted"}

    # ...existing code...
    async def assign_member(
        self,
        project_id: str,
        payload: Dict[str, str] = Body(...),  # either {"user_id":"...", "role":"..."} OR {"uid1":"role1", "uid2":"role2", ...}
        current_user: User = Depends(get_current_user),
    ):
        """
        Add or update one or more members for the project.
        Accepts either:
          - single member form: {"user_id": "...", "role": "..."}
          - bulk form: {"6924...": "dev", "6925...": "test", ...}
        """
        # permission check (reuse same robust pattern as delete_project)
        perm_fn = None
        for name in ("can_manage_project", "can_manage_projects", "can_manage", "can_update_project"):
            candidate = getattr(PermissionService, name, None)
            if callable(candidate):
                perm_fn = candidate
                break
        if callable(perm_fn):
            try:
                allowed = await perm_fn(project_id, str(current_user.id))
            except TypeError:
                try:
                    allowed = await perm_fn(str(current_user.id), project_id)
                except Exception:
                    allowed = False
            except Exception:
                allowed = False
        else:
            allowed = getattr(current_user, "role", None) == "admin"
        if not allowed:
            raise HTTPException(status_code=403, detail="No access to modify project members")

        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        members = dict(getattr(project, "members", {}) or {})

        # Support legacy single-member body {"user_id": "...", "role": "..."}
        if "user_id" in payload and "role" in payload and len(payload) == 2:
            member_doc = await self._user_from_id(payload["user_id"])
            members[str(member_doc.id)] = payload["role"]
        else:
            # Bulk mapping: user_id -> role
            for uid, role in payload.items():
                if not uid or not role:
                    # skip invalid entries; alternatively raise if you prefer strict validation
                    continue
                member_doc = await self._user_from_id(uid)
                members[str(member_doc.id)] = role

        update = {"members": members, "updated_at": datetime.utcnow(), "updated_by": current_user}
        await project.set(update)
        project = await Project.get(project_id)
        return await self.to_response(project)
# ...existing code...
    async def remove_member(
        self,
        project_id: str,
        user_id: str,
        current_user: User = Depends(get_current_user),
    ):
        """
        Remove a member from the project by user_id.
        """
        # same permission check as assign_member
        perm_fn = None
        for name in ("can_manage_project", "can_manage_projects", "can_manage", "can_update_project"):
            candidate = getattr(PermissionService, name, None)
            if callable(candidate):
                perm_fn = candidate
                break
        if callable(perm_fn):
            try:
                allowed = await perm_fn(project_id, str(current_user.id))
            except TypeError:
                try:
                    allowed = await perm_fn(str(current_user.id), project_id)
                except Exception:
                    allowed = False
            except Exception:
                allowed = False
        else:
            allowed = getattr(current_user, "role", None) == "admin"
        if not allowed:
            raise HTTPException(status_code=403, detail="No access to modify project members")
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        members = dict(getattr(project, "members", {}) or {})
        members.pop(str(user_id), None)

        update = {"members": members, "updated_at": datetime.utcnow(), "updated_by": current_user}
        await project.set(update)
        project = await Project.get(project_id)
        return await self.to_response(project)
# ...existing code...

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


projects_router = ProjectsController().router