# app/routers/workitems.py
from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
import re

from bson import ObjectId
from bson.dbref import DBRef
from pydantic.error_wrappers import ValidationError

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.security import HTTPBearer
from typing import List
from beanie import PydanticObjectId

from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import (
    Project, Epic, Feature, Issue, Sprint, Comment, TimeEntry, LinkedWorkItem, Backlog
)
from app.schemas.project_management import (
    EpicCreate, EpicUpdate, EpicOut,
    IssueCreate, IssueUpdate, IssueOut,
    SprintCreate, SprintUpdate, SprintOut,
    FeatureCreate, FeatureUpdate, FeatureOut,
    CommentCreate, CommentOut,
    LinkCreate, LinkOut,
    TimeClockIn, TimeClockOut, TimeAddManual, TimeEntryOut,
)

from app.services.permission import PermissionService
from app.core.timezone_utils import format_datetime_ist

security = HTTPBearer()


# -------- helpers (pure, no functionality change) --------
def _id_of(link_or_doc) -> Optional[str]:
    """Return string id from a Beanie Link/Document/PydanticObjectId/None."""
    if not link_or_doc:
        return None
    # loaded document has .id
    _id = getattr(link_or_doc, "id", None)
    if _id is not None:
        return str(_id)
    # Link wrapper has .ref.id
    ref = getattr(link_or_doc, "ref", None)
    if ref is not None:
        _id = getattr(ref, "id", None)
        if _id is not None:
            return str(_id)
    # raw ObjectId-like
    try:
        return str(link_or_doc)
    except Exception:
        return None

async def _resolve_linked_id(link_obj) -> Optional[str]:
    """
    Return a string id for various link shapes:
      - beanie Link proxy with .id
      - Link proxy that needs .fetch()
      - DBRef, ObjectId, plain string
    """
    if link_obj is None:
        return None
    # direct ObjectId
    try:
        if isinstance(link_obj, ObjectId):
            return str(link_obj)
    except Exception:
        pass
    # DBRef
    try:
        if isinstance(link_obj, DBRef):
            return str(link_obj.id)
    except Exception:
        pass
    # beanie Link with .id attr
    try:
        if hasattr(link_obj, "id") and getattr(link_obj, "id"):
            return str(getattr(link_obj, "id"))
    except Exception:
        pass
    # try fetch() (Link proxy)
    try:
        if hasattr(link_obj, "fetch"):
            fetched = await link_obj.fetch()
            if fetched is not None:
                fid = getattr(fetched, "id", None) or getattr(fetched, "_id", None)
                if fid:
                    return str(fid)
    except Exception:
        pass
    # fallback: string with embedded ObjectId
    try:
        s = str(link_obj)
        m = re.search(r"([0-9a-fA-F]{24})", s)
        if m:
            return m.group(1)
        return s
    except Exception:
        return None

# ---------- EPICS ----------
class EpicsRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/epics", tags=["epics"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/", self.list_epics, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/", self.create_epic, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/{epic_id}", self.get_epic, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/{epic_id}", self.update_epic, methods=["PUT"], dependencies=deps)
        self.router.add_api_route("/{epic_id}", self.delete_epic, methods=["DELETE"], dependencies=deps)

    async def list_epics(
        self,
        project_id: str = Query(...),
        current_user: User = Depends(get_current_user)
    ):
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        epics = await Epic.find(Epic.project.id == PydanticObjectId(project_id), Epic.is_deleted != True).to_list()
        return [self._doc_epic(e) for e in epics]

    async def create_epic(self, data: EpicCreate, current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_edit_project(str(data.project_id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to create")

        project = await Project.get(str(data.project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        epic = Epic(
            name=data.name,
            description=data.description,
            project=project,
            start_date=data.start_date,
            end_date=data.end_date,
            created_by=current_user,
            updated_by=current_user,
        )
        await epic.insert()
        return self._doc_epic(epic)

    async def get_epic(self, epic_id: str, current_user: User = Depends(get_current_user)):
        epic = await Epic.get(epic_id)
        if not epic:
            raise HTTPException(status_code=404, detail="Epic not found")

        # resolve project id robustly (project may be Link proxy or DBRef)
        project = epic.project
        project_id = await _resolve_linked_id(project)
        if not project_id or not await PermissionService.can_view_project(str(project_id), str(current_user.id)):
             raise HTTPException(status_code=403, detail="No access to project")

        # Get all non-deleted issues for this epic
        issues = await Issue.find(Issue.epic.id == epic.id, Issue.is_deleted != True).to_list()
        
        # Convert epic to dict
        epic_data = self._doc_epic(epic)
        
        # Add issues to the response
        epic_data["issues"] = []
        for issue in issues:
            epic_data["issues"].append({
                "id": _id_of(issue),
                "key": getattr(issue, "key", None),
                "name": issue.name,
                "type": issue.type,
                "status": issue.status,
                "priority": issue.priority,
                "assignee_id": _id_of(issue.assignee),
                "story_points": issue.story_points,
                "estimated_hours": issue.estimated_hours,
                "time_spent_hours": issue.time_spent_hours,
                "created_at": getattr(issue, "created_at", None),
                "updated_at": getattr(issue, "updated_at", None),
            })
        epic_data["issues_count"] = len(issues)
        
        # Fetch comments for the epic
        epic_comments = await Comment.find(
            Comment.epic.id == epic.id,
            Comment.issue == None
        ).to_list()
        
        epic_data["comments"] = []
        for c in epic_comments:
            author_name = None
            if c.author:
                try:
                    if isinstance(c.author, User):
                        author_name = c.author.full_name or c.author.email
                    else:
                        u = await User.get(c.author.ref.id)
                        if u:
                            author_name = u.full_name or u.email
                except Exception:
                    pass

            epic_data["comments"].append({
                "id": _id_of(c),
                "project_id": _id_of(c.project),
                "epic_id": _id_of(getattr(c, "epic", None)),
                "sprint_id": _id_of(getattr(c, "sprint", None)),
                "issue_id": _id_of(c.issue),
                "author_id": _id_of(c.author),
                "author_name": author_name,
                "comment": c.comment,
                "created_at": format_datetime_ist(getattr(c, "created_at", None)),
            })
        
        return epic_data

    async def update_epic(self, epic_id: str, data: EpicUpdate, current_user: User = Depends(get_current_user)):
        epic = await Epic.get(epic_id)
        if not epic:
            raise HTTPException(status_code=404, detail="Epic not found")
        
        # Fetch the project to get its ID properly
        project = await epic.project.fetch()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if not await PermissionService.can_edit_project(str(project.id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        await epic.set({k: v for k, v in data.dict(exclude_unset=True).items()})
        epic.updated_by = current_user
        epic.updated_at = datetime.utcnow()
        await epic.save()
        return self._doc_epic(epic)

    async def delete_epic(self, epic_id: str, current_user: User = Depends(get_current_user)):
        epic = await Epic.get(epic_id)
        if not epic:
            raise HTTPException(status_code=404, detail="Epic not found")

        # resolve epic.project to an id (Link/DBRef/ObjectId/string)
        project_id = await _resolve_linked_id(epic.project)
        if not project_id or not await PermissionService.can_edit_project(str(project_id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        epic.is_deleted = True
        epic.deleted_at = datetime.utcnow()
        await epic.save()

        # optional: soft delete issues under this epic
        try:
            await Issue.find(Issue.epic.id == epic.id).update({"$set": {"is_deleted": True, "deleted_at": datetime.utcnow()}})
        except Exception:
            pass

        return {"message": "Epic moved to Recycle Bin"}

    def _doc_epic(self, e: Epic) -> Dict[str, Any]:
        # Safely get project ID whether it's fetched or a Link
        project_id = None
        try:
            if hasattr(e.project, 'id'):
                project_id = str(e.project.id)
            else:
                # If it's a Link, we need to handle it differently
                project_id = _id_of(e.project)
        except Exception:
            project_id = None
        
        return {
            "id": _id_of(e),
            "name": e.name,
            "description": e.description,
            "project_id": project_id,
           
            "end_date": e.end_date,
            "created_by": _id_of(getattr(e, "created_by", None)),
            "updated_by": _id_of(getattr(e, "updated_by", None)),
            "created_at": getattr(e, "created_at", None),
            "updated_at": getattr(e, "updated_at", None),
            "key": getattr(e, "key", None),
        }


# ---------- ISSUES ----------

# ---------- SPRINTS ----------


# ---------- COMMENTS ----------
class CommentsRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/comments", tags=["comments"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/", self.list_comments, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/", self.create_comment, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/{comment_id}", self.delete_comment, methods=["DELETE"], dependencies=deps)

    async def list_comments(
        self,
        issue_id: Optional[str] = Query(None),
        epic_id: Optional[str] = Query(None),
        sprint_id: Optional[str] = Query(None),
        project_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user)
    ):
        comments = []
        
        if issue_id:
            issue = await Issue.get(issue_id)
            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")
            if not await PermissionService.can_view_project(_id_of(issue.project), str(current_user.id)):
                raise HTTPException(status_code=403, detail="No access")
            comments = await Comment.find(Comment.issue.id == issue.id).to_list()

        elif sprint_id:
            sprint = await Sprint.get(sprint_id)
            if not sprint:
                raise HTTPException(status_code=404, detail="Sprint not found")
            if not await PermissionService.can_view_project(_id_of(sprint.project), str(current_user.id)):
                raise HTTPException(status_code=403, detail="No access")
            comments = await Comment.find(Comment.sprint.id == sprint.id).to_list()

        elif epic_id:
            epic = await Epic.get(epic_id)
            if not epic:
                raise HTTPException(status_code=404, detail="Epic not found")
            if not await PermissionService.can_view_project(_id_of(epic.project), str(current_user.id)):
                raise HTTPException(status_code=403, detail="No access")
            # Comments specifically on the Epic (not its issues)
            comments = await Comment.find(
                Comment.epic.id == epic.id,
                Comment.issue == None
            ).to_list()

        elif project_id:
            if not await PermissionService.can_view_project(project_id, str(current_user.id)):
                raise HTTPException(status_code=403, detail="No access")
            # Comments specifically on the Project
            comments = await Comment.find(
                Comment.project.id == PydanticObjectId(project_id),
                Comment.epic == None,
                Comment.issue == None,
                Comment.sprint == None
            ).to_list()
        else:
            # No filter provided
            return []

        out: List[Dict[str, Any]] = []
        for c in comments:
            out.append(await self._doc_comment(c))
        return out

    async def create_comment(self, data: CommentCreate, current_user: User = Depends(get_current_user)):
        # Ensure at least one target is provided
        if not any([data.issue_id, data.sprint_id, data.epic_id, data.project_id]):
            raise HTTPException(status_code=400, detail="Must provide at least one of issue_id, sprint_id, epic_id, or project_id")

        project = None
        issue = None
        sprint = None
        epic = None

        # Resolve Issue
        if data.issue_id:
            issue = await Issue.get(str(data.issue_id))
            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")
            # Infer project from issue if not set
            if not data.project_id:
                data.project_id = _id_of(issue.project)

        # Resolve Sprint
        if data.sprint_id:
            sprint = await Sprint.get(str(data.sprint_id))
            if not sprint:
                raise HTTPException(status_code=404, detail="Sprint not found")
            if not data.project_id:
                data.project_id = _id_of(sprint.project)

        # Resolve Epic
        if data.epic_id:
            epic = await Epic.get(str(data.epic_id))
            if not epic:
                raise HTTPException(status_code=404, detail="Epic not found")
            if not data.project_id:
                data.project_id = _id_of(epic.project)

        # Resolve Project
        if data.project_id:
            project = await Project.get(str(data.project_id))
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
        else:
            # Should not happen if logic above is correct, but safe fallback
            raise HTTPException(status_code=400, detail="Could not determine project context")

        # Permission check
        if not await PermissionService.can_view_project(str(project.id), str(current_user.id)):
             raise HTTPException(status_code=403, detail="No access")

        comment = Comment(
            project=project,
            epic=epic,
            sprint=sprint,
            issue=issue,
            author=current_user,
            comment=data.comment,
        )
        await comment.insert()
        return await self._doc_comment(comment)

    async def delete_comment(self, comment_id: str, current_user: User = Depends(get_current_user)):
        c = await Comment.get(comment_id)
        if not c:
            raise HTTPException(status_code=404, detail="Comment not found")

        if (_id_of(c.author) != str(current_user.id)) and (current_user.role != "admin"):
            raise HTTPException(status_code=403, detail="No access")

        await c.delete()
        return {"message": "Comment deleted"}

    async def _doc_comment(self, c: Comment) -> Dict[str, Any]:
        author_name = None
        if c.author:
            try:
                # If author is already loaded (Document)
                if isinstance(c.author, User):
                    author_name = c.author.full_name or c.author.email
                else:
                    # It's a Link, fetch it
                    u = await User.get(c.author.ref.id)
                    if u:
                        author_name = u.full_name or u.email
            except Exception:
                pass

        return {
            "id": _id_of(c),
            "project_id": _id_of(c.project),
            "epic_id": _id_of(getattr(c, "epic", None)),
            "sprint_id": _id_of(getattr(c, "sprint", None)),
            "issue_id": _id_of(c.issue),
            "author_id": _id_of(c.author),
            "author_name": author_name,
            "comment": c.comment,
            "created_at": format_datetime_ist(getattr(c, "created_at", None)),
        }


# ---------- LINKS ----------
class LinksRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/links", tags=["linked-workitems"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/", self.list_links, methods=["GET"])
        self.router.add_api_route("/{link_id}", self.get_link, methods=["GET"])
        self.router.add_api_route("/", self.create_link, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/{link_id}", self.delete_link, methods=["DELETE"], dependencies=deps)

    async def list_links(
        self, 
        item_id: str = Query(..., description="The ID of the item (Project/Epic/Issue etc) to list links for"),
        current_user: User = Depends(get_current_user)
    ):
        from beanie.operators import Or
        # Find links where this item is either source or target
        gid = PydanticObjectId(item_id)
        links = await LinkedWorkItem.find(
            Or(LinkedWorkItem.source_id == gid, LinkedWorkItem.target_id == gid)
        ).to_list()

        out_links = []
        for l in links:
            out_links.append(self._doc_link(l))
        return out_links

    async def get_link(self, link_id: str, current_user: User = Depends(get_current_user)):
        l = await LinkedWorkItem.get(link_id)
        if not l:
            raise HTTPException(status_code=404, detail="Link not found")
        return self._doc_link(l)
    async def create_link(self, data: LinkCreate, current_user: User = Depends(get_current_user)):
        # Validate that both source and target exist
        model_map = {
            "project": Project,
            "epic": Epic,
            "sprint": Sprint,
            "issue": Issue,
            "feature": Feature
        }
        
        source_model = model_map.get(data.source_type)
        target_model = model_map.get(data.target_type)
        
        if not source_model or not target_model:
            raise HTTPException(status_code=400, detail=f"Invalid source or target type: {data.source_type} / {data.target_type}")
            
        source = await source_model.get(str(data.source_id))
        target = await target_model.get(str(data.target_id))
        
        if not source or not target:
            raise HTTPException(status_code=404, detail="Source or target item not found")

        # Create the generic link
        link = LinkedWorkItem(
            source_id=data.source_id,
            source_type=data.source_type,
            target_id=data.target_id,
            target_type=data.target_type,
            reason=data.reason
        )
        await link.insert()
        return self._doc_link(link)

    async def delete_link(self, link_id: str, current_user: User = Depends(get_current_user)):
        link = await LinkedWorkItem.get(link_id)
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # permission check removed: allow authenticated users to delete links

        await link.delete()
        return {"message": "Link deleted"}

    def _doc_link(self, l: LinkedWorkItem) -> Dict[str, Any]:
        return {
            "id": str(l.id),
            "source_id": str(l.source_id),
            "source_type": l.source_type,
            "target_id": str(l.target_id),
            "target_type": l.target_type,
            "reason": l.reason,
            "created_at": l.created_at,
        }


# ---------- TIME TRACKING ----------
class TimeRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/time", tags=["time-tracking"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/entries", self.list_entries, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/clock-in", self.clock_in, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/clock-out", self.clock_out, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/add", self.add_manual, methods=["POST"], dependencies=deps)

    async def list_entries(
        self,
        project_id: str = Query(...),
        issue_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
    ):
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        q = TimeEntry.project.id == PydanticObjectId(project_id)
        entries = await TimeEntry.find(q).to_list()

        if issue_id:
            entries = [t for t in entries if _id_of(t.issue) == issue_id]

        out: List[Dict[str, Any]] = []
        for t in entries:
            out.append({
                "id": _id_of(t),
                "project_id": _id_of(t.project),
                "issue_id": _id_of(t.issue),
                "user_id": _id_of(t.user),
                "clock_in": t.clock_in,
                "clock_out": t.clock_out,
                "seconds": t.seconds,
            })
        return out

    async def clock_in(self, data: TimeClockIn, current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_view_project(str(data.project_id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        try:
            issue = await Issue.get(str(data.issue_id))
        except ValidationError as e:
            # fetch raw document to give actionable info
            raw = await Issue.get_motor_collection().find_one({"_id": ObjectId(str(data.issue_id))})
            detail = {
                "msg": "Issue document failed model validation (likely a subtask missing parent)",
                "issue_id": str(data.issue_id),
                "pydantic_errors": e.errors(),
                "raw_doc_snippet": {
                    "_id": str(raw["_id"]) if raw else None,
                    "type": raw.get("type") if raw else None,
                    "parent": raw.get("parent") if raw else None,
                    "name": raw.get("name") if raw else None,
                },
            }
            raise HTTPException(status_code=422, detail=detail)

        project = await Project.get(str(data.project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        entry = TimeEntry(
            project=project,
            issue=issue,
            user=current_user,
            clock_in=datetime.utcnow(),
            clock_out=None,
            seconds=0,
        )
        await entry.insert()
        return {"id": _id_of(entry)}

    async def clock_out(self, data: TimeClockOut, current_user: User = Depends(get_current_user)):
        entry = await TimeEntry.get(str(data.time_entry_id))
        if not entry:
            raise HTTPException(status_code=404, detail="Time entry not found")

        if _id_of(entry.user) != str(current_user.id) and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="No access")

        if entry.clock_out:
            raise HTTPException(status_code=400, detail="Already clocked out")

        entry.clock_out = datetime.utcnow()
        entry.seconds = int((entry.clock_out - entry.clock_in).total_seconds())
        await entry.save()
        return {"id": _id_of(entry), "seconds": entry.seconds}

    async def add_manual(self, data: TimeAddManual, current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_view_project(str(data.project_id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        project = await Project.get(str(data.project_id))
        issue = await Issue.get(str(data.issue_id))
        if not project or not issue:
            raise HTTPException(status_code=404, detail="Project/Issue not found")

        now = datetime.utcnow()
        entry = TimeEntry(
            project=project,
            issue=issue,
            user=current_user,
            clock_in=now,
            clock_out=now,
            seconds=int(data.seconds),
        )
        await entry.insert()
        return {"id": _id_of(entry), "seconds": entry.seconds}


# Expose routers
epics_router = EpicsRouter().router
comments_router = CommentsRouter().router
links_router = LinksRouter().router
time_router = TimeRouter().router
#features_router = FeaturesRouter().router

router = APIRouter()


@router.get("/projects/", response_model=List[Dict[str, Any]])
async def list_projects(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    """
    Admin -> return all projects (paged).
    Non-admin -> return only projects current_user can view (owner/member/public).
    """
    items: List[Dict[str, Any]] = []
    async for p in Project.find(Project.is_deleted != True).skip(skip).limit(limit):
        # admin sees everything
        if getattr(current_user, "role", None) == "admin":
            allowed = True
        else:
            # use PermissionService to decide per-project visibility
            allowed = await PermissionService.can_view_project(str(p.id), str(getattr(current_user, "id", None)))
        if not allowed:
            continue
        items.append({
            "id": str(p.id),
            "name": getattr(p, "name", None),
            "owner_id": PermissionService and (str(getattr(p, "owner", None)) if getattr(p, "owner", None) else None),
            "key": getattr(p, "key", None),
            "description": getattr(p, "description", None),
            "public": getattr(p, "public", False),
        })
    return items

@router.get("/projects/{project_id}")
async def get_project(project_id: str, current_user: User = Depends(get_current_user)):
    proj = await Project.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # require permission to view
    if not await PermissionService.can_view_project(project_id, str(getattr(current_user, "id", None))):
        raise HTTPException(status_code=403, detail="No access to project")

    return {
        "id": _id_of(proj),
        "name": proj.name,
        "owner_id": str(getattr(proj, "owner", None)) if getattr(proj, "owner", None) else None,
        "key": getattr(proj, "key", None),
        "description": getattr(proj, "description", None),
        "public": getattr(proj, "public", False),
        # add other fields you need
        "comments": [
            {
                "id": _id_of(c),
                "project_id": _id_of(c.project),
                "epic_id": _id_of(getattr(c, "epic", None)),
                "sprint_id": _id_of(getattr(c, "sprint", None)),
                "issue_id": _id_of(c.issue),
                "author_id": _id_of(c.author),
                "comment": c.comment,
                "created_at": format_datetime_ist(getattr(c, "created_at", None)),
            }
            for c in await Comment.find(
                Comment.project.id == PydanticObjectId(project_id),
                Comment.epic == None,
                Comment.issue == None,
                Comment.sprint == None
            ).to_list()
        ]
    }

# add a dedicated router for features (separate Swagger group)
features_router = APIRouter(prefix="/features", tags=["features"])

# replace the old @router.post("/features", ...) etc with these handlers

@features_router.post("/", response_model=FeatureOut)
async def create_feature(payload: FeatureCreate, current_user: User = Depends(get_current_user)):
    # permission check (ensure current_user can edit project)
    if not await PermissionService.can_edit_project(str(payload.project_id), str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")
    proj = await Project.get(PydanticObjectId(payload.project_id))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    f = Feature(
        name=payload.name,
        description=payload.description,
        project_id=PydanticObjectId(payload.project_id),
        epic_id=PydanticObjectId(payload.epic_id) if payload.epic_id else None,
        priority=payload.priority,
        status=payload.status,
        created_by=PydanticObjectId(str(current_user.id))
    )
    await f.insert()
    return FeatureOut(
        id=str(f.id),
        project_id=str(f.project_id),
        epic_id=str(f.epic_id) if f.epic_id else None,
        name=f.name,
        description=f.description,
        priority=f.priority,
        status=f.status,
        created_by=str(f.created_by) if f.created_by else None,
        created_at=f.created_at
    )

@features_router.get("/", response_model=List[FeatureOut])
async def list_features(project_id: str = Query(...), current_user: User = Depends(get_current_user)):
    items = []
    async for f in Feature.find(Feature.project_id == PydanticObjectId(project_id), Feature.is_deleted != True):
        items.append(FeatureOut(
            id=str(f.id),
            project_id=str(f.project_id),
            epic_id=str(f.epic_id) if f.epic_id else None,
            name=f.name,
            description=f.description,
            priority=f.priority,
            status=f.status,
            created_by=str(f.created_by) if f.created_by else None,
            created_at=f.created_at
        ))
    return items

@features_router.get("/{feature_id}", response_model=FeatureOut)
async def get_feature(feature_id: str, current_user: User = Depends(get_current_user)):
    f = await Feature.get(feature_id)
    if not f:
        raise HTTPException(status_code=404, detail="Feature not found")
    if not await PermissionService.can_view_project(str(f.project_id), str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")
    return FeatureOut(
        id=str(f.id),
        project_id=str(f.project_id),
        epic_id=str(f.epic_id) if f.epic_id else None,
        name=f.name,
        description=f.description,
        priority=f.priority,
        status=f.status,
        created_by=str(f.created_by) if f.created_by else None,
        created_at=f.created_at
    )

@features_router.put("/{feature_id}", response_model=FeatureOut)
async def update_feature(feature_id: str, payload: FeatureUpdate, current_user: User = Depends(get_current_user)):
    f = await Feature.get(feature_id)
    if not f:
        raise HTTPException(status_code=404, detail="Feature not found")
    if not await PermissionService.can_edit_project(str(f.project_id), str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")
    await f.set({k: v for k, v in payload.dict(exclude_unset=True).items()})
    await f.save()
    return FeatureOut(
        id=str(f.id),
        project_id=str(getattr(f, "project_id", None)) if getattr(f, "project_id", None) else None,
        epic_id=str(getattr(f, "epic_id", None)) if getattr(f, "epic_id", None) else None,
        name=getattr(f, "name", None),
        description=getattr(f, "description", None),
        priority=getattr(f, "priority", None),
        status=getattr(f, "status", None),
        created_by=str(getattr(f, "created_by", None)) if getattr(f, "created_by", None) else None,
        created_at=getattr(f, "created_at", None),
    )

@features_router.delete("/{feature_id}")
async def delete_feature(feature_id: str, current_user: User = Depends(get_current_user)):
    f = await Feature.get(feature_id)
    if not f:
        raise HTTPException(status_code=404, detail="Feature not found")
    
    if not await PermissionService.can_edit_project(str(f.project_id), str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")
    
    f.is_deleted = True
    f.deleted_at = datetime.utcnow()
    await f.save()

    return {"message": "Feature moved to Recycle Bin"}

