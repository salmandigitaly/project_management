from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.security import HTTPBearer
from typing import List
from beanie import PydanticObjectId
from bson import ObjectId
from pydantic.error_wrappers import ValidationError

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



class SprintsRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/sprints", tags=["sprints"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/", self.list_sprints, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/", self.create_sprint, methods=["POST"], dependencies=deps)
        # register completed before the parameterized route so "/completed" doesn't match "{sprint_id}"
        self.router.add_api_route("/completed", self.list_completed_sprints, methods=["GET"], dependencies=deps)
        # check running sprint (must be registered before parameterized routes)
        self.router.add_api_route("/running", self.running_sprint, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/running/all", self.list_running_sprints, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}", self.get_sprint, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}", self.update_sprint, methods=["PUT"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}", self.delete_sprint, methods=["DELETE"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}/start", self.start_sprint, methods=["POST"], dependencies=deps)
        # complete sprint
        self.router.add_api_route("/{sprint_id}/complete", self.complete_sprint, methods=["POST"], dependencies=deps)
    
    async def _can_manage_sprint(self, project_id: str, current_user: User) -> bool:
        """
        Robust permission helper: prefer PermissionService.can_manage_sprint if present,
        otherwise fall back to admin role or other PermissionService checks.
        """
        perm_fn = getattr(PermissionService, "can_manage_sprint", None)
        if callable(perm_fn):
            try:
                return await perm_fn(str(project_id), str(current_user.id))
            except Exception:
                pass

        # fallback: admin allowed
        if getattr(current_user, "role", None) == "admin":
            return True

        # try other available permission checks
        for fn_name in ("can_edit_project", "can_view_project", "can_edit_workitem"):
            fn = getattr(PermissionService, fn_name, None)
            if callable(fn):
                try:
                    allowed = await fn(str(project_id), str(current_user.id))
                    if allowed:
                        return True
                except Exception:
                    continue
        return False

    async def list_sprints(self, project_id: str = Query(...), current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        # get sprints for project
        sprints = await Sprint.find(Sprint.project.id == PydanticObjectId(project_id)).to_list()

        # fetch all issues for project and group by sprint id (safe for Link / id types)
        all_issues = await Issue.find(Issue.project.id == PydanticObjectId(project_id)).to_list()
        from collections import defaultdict
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for issue in all_issues:
            sid = _id_of(issue.sprint)
            if not sid:
                continue
            grouped[sid].append({
                "id": _id_of(issue),
                "key": getattr(issue, "key", None),
                "type": issue.type,
                "name": issue.name,
                "status": issue.status,
                "assignee_id": _id_of(getattr(issue, "assignee", None)),
                "story_points": issue.story_points,
                "estimated_hours": issue.estimated_hours,
                "time_spent_hours": issue.time_spent_hours,
                "location": issue.location,
                "feature_id": _id_of(getattr(issue, "feature", None) or getattr(issue, "feature_id", None)),
            })

        out: List[Dict[str, Any]] = []
        for s in sprints:
            doc = self._doc_sprint(s)
            sid = _id_of(s)
            doc["issues"] = grouped.get(sid, [])
            doc["issues_count"] = len(doc["issues"])
            out.append(doc)
        return out

    async def create_sprint(self, data: SprintCreate, current_user: User = Depends(get_current_user)):
        # robust permission check: prefer can_manage_sprint if available, else fallback
        perm_fn = getattr(PermissionService, "can_manage_sprint", None)
        if callable(perm_fn):
            allowed = await perm_fn(str(data.project_id), str(current_user.id))
        else:
            # fallback: allow admins OR use can_view_project if available
            allowed = getattr(current_user, "role", None) == "admin"
            view_fn = getattr(PermissionService, "can_view_project", None)
            if not allowed and callable(view_fn):
                allowed = await view_fn(str(data.project_id), str(current_user.id))
        if not allowed:
            raise HTTPException(status_code=403, detail="No access to create sprint")

        project = await Project.get(str(data.project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sprint = Sprint(
            name=data.name,
            project=project,
            goal=data.goal,
            start_date=data.start_date,
            end_date=data.end_date,
            created_by=current_user,
        )
        await sprint.insert()
        return self._doc_sprint(sprint)

    async def get_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        # use _id_of to support Links / fetched docs
        if not await PermissionService.can_view_project(_id_of(sprint.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        # build issues details from sprint.issue_ids
        issues_list: List[Dict[str, Any]] = []
        for iid in getattr(sprint, "issue_ids", []) or []:
            try:
                issue = await Issue.get(iid)
            except Exception:
                issue = None
            if not issue:
                continue
            issues_list.append({
                "id": str(issue.id),
                "key": getattr(issue, "key", None),
                "type": issue.type,
                "name": issue.name,
                "status": issue.status,
                "assignee_id": _id_of(getattr(issue, "assignee", None)),
                "story_points": issue.story_points,
                "estimated_hours": issue.estimated_hours,
                "time_spent_hours": issue.time_spent_hours,
                "location": issue.location,
                "feature_id": str(getattr(issue, "feature_id", None)) if getattr(issue, "feature_id", None) else None,
            })

        return {
            "id": _id_of(sprint),
            "name": sprint.name,
            "project_id": _id_of(sprint.project),
            "goal": sprint.goal,
            "start_date": getattr(sprint, "start_date", None),
            "end_date": getattr(sprint, "end_date", None),
            "issues": issues_list,
        }

    async def update_sprint(self, sprint_id: str, data: SprintUpdate, current_user: User = Depends(get_current_user)):
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        if not await self._can_manage_sprint(_id_of(sprint.project), current_user):
            raise HTTPException(status_code=403, detail="No access")

        await sprint.set({k: v for k, v in data.dict(exclude_unset=True).items()})
        return self._doc_sprint(sprint)

    async def delete_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        if not await self._can_manage_sprint(_id_of(sprint.project), current_user):
            raise HTTPException(status_code=403, detail="No access")

        await sprint.delete()
        return {"message": "Sprint deleted"}
    

    async def start_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
        """
        Start a sprint - move all sprint issues to board with correct status columns
        """
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        
        if not await self._can_manage_sprint(_id_of(sprint.project), current_user):
            raise HTTPException(status_code=403, detail="No access")

        # Get all issues in this sprint
        issues = await Issue.find(Issue.sprint.id == sprint.id).to_list()
        
        moved_issues = []
        errors = []

        for issue in issues:
            try:
                # Move issue to board (location remains the same for status mapping)
                issue.location = "board"
                
                # Status mapping:
                # "todo" → "todo" (To Do column)
                # "inprogress" → "inprogress" (In Progress column) 
                # "done" → "done" (Done column)
                # No change to status, just location to board
                
                await issue.save()
                moved_issues.append({
                    "id": _id_of(issue),
                    "key": getattr(issue, "key", None),
                    "name": issue.name,
                    "status": issue.status,
                    "location": issue.location
                })
                
            except Exception as e:
                errors.append(f"Error moving issue {_id_of(issue)}: {str(e)}")

        return {
            "sprint_id": sprint_id,
            "sprint_name": sprint.name,
            "moved_issues": moved_issues,
            "total_moved": len(moved_issues),
            "errors": errors,
            "message": f"Started sprint '{sprint.name}'. Moved {len(moved_issues)} issues to board."
        }

    async def complete_sprint(
        self,
        sprint_id: str,
        auto_move_incomplete_to: Optional[str] = Query(None, description="Specify 'backlog' or target sprint id; omit or leave empty to only check issues"),
        current_user: User = Depends(get_current_user),
    ):
        """
        Complete sprint:
         - When auto_move_incomplete_to is omitted/empty:
             * If all issues status == 'done' -> mark sprint completed and store snapshot.
             * If some issues are not done -> return lists of completed_issues and pending_issues (no moves).
         - When auto_move_incomplete_to is provided:
             * Move incomplete issues to backlog or provided sprint id, then mark sprint completed and store snapshot.
        """
        # treat empty string as omitted
        if auto_move_incomplete_to is not None and str(auto_move_incomplete_to).strip() == "":
            auto_move_incomplete_to = None

        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
 
        issues_col = Issue.get_motor_collection()
        sprints_col = Sprint.get_motor_collection()
        backlog_col = Backlog.get_motor_collection()
 
        # collect all sprint issues (prefer sprint.issue_ids)
        sprint_issue_ids = getattr(sprint, "issue_ids", []) or []
        docs = []
        if sprint_issue_ids:
            normalized = []
            for x in sprint_issue_ids:
                try:
                    normalized.append(ObjectId(str(x)))
                except Exception:
                    normalized.append(str(x))
            if normalized:
                docs = [d async for d in issues_col.find({"_id": {"$in": normalized}})]
        else:
            # fallback: find by issue.sprint link (match ObjectId and string)
            conds = []
            try:
                obj_id = ObjectId(str(sprint.id))
            except Exception:
                obj_id = None
            if obj_id:
                conds.append({"sprint": obj_id})
            conds.append({"sprint": str(sprint.id)})
            cursor_filter = conds[0] if len(conds) == 1 else {"$or": conds}
            docs = [d async for d in issues_col.find(cursor_filter)]

        # Snapshot all sprint issues (store as strings)
        snapshot_ids = [str(d.get("_id")) for d in docs]

        # If auto_move_incomplete_to is omitted -> only check statuses
        if not auto_move_incomplete_to:
            completed_issues = []
            pending_issues = []
            for d in docs:
                iid = str(d.get("_id"))
                name = d.get("name")
                status = d.get("status")
                if status == "done":
                    completed_issues.append({"id": iid, "name": name})
                else:
                    pending_issues.append({"id": iid, "name": name, "status": status})

            # If there are no pending issues -> mark sprint completed and persist snapshot
            if not pending_issues:
                completed_ts = datetime.utcnow()
                update_body = {"$set": {"completed_at": completed_ts, "active": False, "completed_issue_ids": snapshot_ids, "status": "completed"}}
                try:
                    await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, update_body)
                except Exception:
                    try:
                        await sprints_col.update_one({"_id": str(sprint.id)}, update_body)
                    except Exception:
                        pass
                try:
                    sprint.completed_at = completed_ts
                    sprint.active = False
                    sprint.completed_issue_ids = snapshot_ids
                    sprint.status = "completed"
                    await sprint.save()
                except Exception:
                    pass

                return {
                    "completed_issues": completed_issues,
                    "pending_issues": [],
                    "sprint_id": _id_of(sprint),
                    "completed_at": completed_ts.isoformat(),
                }

            # There are pending issues -> return lists, do not move anything or complete sprint
            return {
                "completed_issues": completed_issues,
                "pending_issues": pending_issues,
                "sprint_id": _id_of(sprint),
            }
 
        # auto_move_incomplete_to provided -> move incomplete issues (existing behavior)
        moved = []
        errors = []
        incomplete_docs = [d for d in docs if d.get("status") != "done"]
        for doc in incomplete_docs:
            iid_raw = doc.get("_id")
            try:
                iid_obj = iid_raw if isinstance(iid_raw, ObjectId) else ObjectId(str(iid_raw))
            except Exception:
                iid_obj = iid_raw
            iid_str = str(iid_raw)

            # remove from current sprint.issue_ids (try both forms)
            try:
                await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, {"$pull": {"issue_ids": iid_obj}})
            except Exception:
                try:
                    await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, {"$pull": {"issue_ids": iid_str}})
                except Exception:
                    try:
                        await sprints_col.update_one({"_id": str(sprint.id)}, {"$pull": {"issue_ids": iid_obj}})
                    except Exception:
                        await sprints_col.update_one({"_id": str(sprint.id)}, {"$pull": {"issue_ids": iid_str}})

            try:
                if auto_move_incomplete_to != "backlog":
                    moved_ok = False
                    try:
                        target_obj = ObjectId(str(auto_move_incomplete_to))
                        await sprints_col.update_one({"_id": target_obj}, {"$addToSet": {"issue_ids": iid_obj}})
                        await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": target_obj, "location": "sprint"}})
                        moved_ok = True
                    except Exception:
                        try:
                            await sprints_col.update_one({"_id": auto_move_incomplete_to}, {"$addToSet": {"issue_ids": iid_str}})
                            await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": iid_str, "location": "sprint"}})
                            moved_ok = True
                        except Exception:
                            moved_ok = False

                    if not moved_ok:
                        await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": None, "location": "backlog"}})
                        try:
                            proj_id = _id_of(sprint.project) or str(getattr(sprint, "project", None))
                            await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": iid_obj}}, upsert=True)
                        except Exception:
                            await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": iid_str}}, upsert=True)
                else:
                    await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": None, "location": "backlog"}})
                    try:
                        proj_id = _id_of(sprint.project) or str(getattr(sprint, "project", None))
                        await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": iid_obj}}, upsert=True)
                    except Exception:
                        await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": iid_str}}, upsert=True)

                moved.append(iid_str)
            except Exception as e:
                errors.append({"issue": iid_str, "error": str(e)})

        # persist sprint completion + snapshot of issue ids and mark status/active
        completed_ts = datetime.utcnow()
        update_body = {"$set": {"completed_at": completed_ts, "active": False, "completed_issue_ids": snapshot_ids, "status": "completed"}}
        try:
            await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, update_body)
        except Exception:
            try:
                await sprints_col.update_one({"_id": str(sprint.id)}, update_body)
            except Exception:
                pass

        try:
            sprint.completed_at = completed_ts
            sprint.active = False
            sprint.completed_issue_ids = snapshot_ids
            sprint.status = "completed"
            await sprint.save()
        except Exception:
            pass

        return {
            "ok": True,
            "sprint_id": _id_of(sprint),
            "completed_at": completed_ts.isoformat(),
            "moved_incomplete_issues": moved,
            "snapshot_issue_ids": snapshot_ids,
            "errors": errors,
        }

    async def list_completed_sprints(self, project_id: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
        """
        GET /sprints/completed
        - Any authenticated user can call this.
        - Optional project_id filters results to that project.
        """
        sprints_col = Sprint.get_motor_collection()

        # find sprints that have a completed_at timestamp (completed)
        docs = [d async for d in sprints_col.find({"completed_at": {"$ne": None}})]

        import re

        def _extract_hex(s: Any) -> Optional[str]:
            """Return 24-hex substring from s (lowercased) or None."""
            if s is None:
                return None
            try:
                # dicts like DBRef / nested docs: try common keys first
                if isinstance(s, dict):
                    for k in ("$id", "id", "_id"):
                        if k in s and s[k]:
                            try:
                                return re.search(r"[0-9a-fA-F]{24}", str(s[k])).group(0).lower()
                            except Exception:
                                pass
                    # final attempt: stringification of dict
                    s = str(s)
                else:
                    s = str(s)
            except Exception:
                return None
            m = re.search(r"[0-9a-fA-F]{24}", s)
            return m.group(0).lower() if m else s

        # normalize incoming project_id (may already be hex, or long form)
        project_hex = None
        if project_id:
            project_hex = _extract_hex(project_id)

        # filter by normalized hex string (robust across shapes)
        if project_hex:
            filtered = [d for d in docs if _extract_hex(d.get("project") or d.get("project_id")) == project_hex]
        else:
            filtered = docs

        out: List[Dict[str, Any]] = []
        for d in filtered:
            proj_id = _extract_hex(d.get("project") or d.get("project_id"))
            completed_ids = d.get("completed_issue_ids") or []
            out.append({
                "id": str(d.get("_id")),
                "name": d.get("name"),
                "project_id": proj_id,
                "start_date": d.get("start_date"),
                "end_date": d.get("end_date"),
                "completed_at": d.get("completed_at"),
                "completed_issue_ids": [str(i) for i in completed_ids],
                "issue_count": len(completed_ids),
            })
        return out

    async def running_sprint(self, current_user: User = Depends(get_current_user)):
        """
        GET /sprints/running
        Return whether any sprint is currently running.
        Priority:
         1) sprint with active == True
         2) sprint where start_date <= now <= end_date and completed_at is missing/null
        """
        sprints_col = Sprint.get_motor_collection()

        # 1) explicit active flag
        doc = await sprints_col.find_one({"active": True})
        if not doc:
            now = datetime.utcnow()
            doc = await sprints_col.find_one({
                "start_date": {"$lte": now},
                "end_date": {"$gte": now},
                "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}]
            })

        if not doc:
            return {"sprint_running": False}

        return {
            "sprint_running": True,
            "sprint_id": str(doc.get("_id")),
            "sprint_name": doc.get("name"),
        }
    async def list_running_sprints(self, current_user: User = Depends(get_current_user)):
        """
        GET /sprints/running/all
        Return a list of all running sprints (matches active OR date range & not completed).
        """
        sprints_col = Sprint.get_motor_collection()
        now = datetime.utcnow()
        query = {
            "$or": [
                {"active": True},
                {
                    "$and": [
                        {"start_date": {"$lte": now}},
                        {"end_date": {"$gte": now}},
                        {"$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}]}
                    ]
                }
            ]
        }

        docs = [d async for d in sprints_col.find(query).sort([("start_date", 1)])]
        out: List[Dict[str, Any]] = []
        for d in docs:
            out.append({
                "sprint_running": True,
                "sprint_id": str(d.get("_id")),
                "sprint_name": d.get("name"),
                "project_id": (str(d.get("project")) if d.get("project") is not None else None),
                "start_date": d.get("start_date"),
               "end_date": d.get("end_date"),
            })
        # if nothing matched return a single object for consistency or empty list per your preference
        return out
# ...existing code...

    def _doc_sprint(self, s: Sprint) -> Dict[str, Any]:
        return {
            "id": _id_of(s),
            "name": s.name,
            "project_id": _id_of(s.project),
            "goal": s.goal,
            "start_date": s.start_date,
            "end_date": s.end_date,
        }


sprints_router = SprintsRouter().router

router = APIRouter()

@router.get("/sprints/{sprint_id}", response_model=SprintOut)
async def get_sprint(sprint_id: str, user=Depends(get_current_user)):
    sprint = await Sprint.get(PydanticObjectId(sprint_id))
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    data = sprint.dict()
    data["id"] = str(sprint.id)
    # ensure issue_ids are strings
    data["issue_ids"] = [str(i) for i in getattr(sprint, "issue_ids", [])]
    # project is a Link; expose project id string
    # use _id_of to consistently produce project id string from Link or doc
    data["project_id"] = _id_of(sprint.project) or str(data.get("project"))
    return data

@router.get("/sprints/", response_model=List[SprintOut])
async def list_sprints(page: int = 1, limit: int = 50, user=Depends(get_current_user)):
    items = []
    async for s in Sprint.find().skip((page-1)*limit).limit(limit):
        d = s.dict()
        d["id"] = str(s.id)
        d["issue_ids"] = [str(i) for i in getattr(s, "issue_ids", [])]
        try:
            d["project_id"] = str(s.project.id)
        except Exception:
            d["project_id"] = str(d.get("project"))
        items.append(d)
    return items
