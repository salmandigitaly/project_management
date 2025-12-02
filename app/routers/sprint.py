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
    Project, Epic, Feature, Issue, Sprint, Comment, TimeEntry, LinkedWorkItem, Backlog ,Board
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
        # self.router.add_api_route("/running", self.running_sprint, methods=["GET"], dependencies=deps)
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
            # ensure new sprint is NOT running until start_sprint is invoked
            active=False,
            status="planned",
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
    

    # ...existing code...
  # ...existing code...
    async def start_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
        """
        Start a sprint - move all sprint issues to board with correct status columns
        """
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        
        if not await self._can_manage_sprint(_id_of(sprint.project), current_user):
            raise HTTPException(status_code=403, detail="No access")

        sprints_col = Sprint.get_motor_collection()

        # mark sprint as running (update both document and DB to ensure persistence)
        try:
            if not getattr(sprint, "start_date", None):
                sprint.start_date = datetime.utcnow()
            sprint.active = True
            sprint.status = "running"
            # try model save first
            await sprint.save()
        except Exception:
            # ignore model save errors
            pass

        # Ensure DB record is updated (guarantee boolean flag in DB)
        try:
            update_body = {
                "$set": {
                    "active": True,
                    "status": "running",
                    "start_date": sprint.start_date or datetime.utcnow()
                }
            }
            try:
                await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, update_body)
            except Exception:
                await sprints_col.update_one({"_id": str(sprint.id)}, update_body)
        except Exception:
            # non-fatal — continue to move issues even if DB update fails
            pass

        # Get all issues in this sprint
        issues = await Issue.find(Issue.sprint.id == sprint.id).to_list()

        moved_issues = []
        errors = []

        for issue in issues:
            try:
                # set location to 'board' (or whatever your workflow requires)
                issue.location = "board"
                # optionally adjust status mapping here if needed
                await issue.save()
                moved_issues.append({
                    "id": _id_of(issue),
                    "key": getattr(issue, "key", None),
                    "name": issue.name,
                    "status": issue.status,
                    "location": issue.location
                })
            except Exception as e:
                errors.append({"id": _id_of(issue) or str(getattr(issue, "id", None)), "error": str(e)})

        # Return a useful summary so client is not getting an empty/null response
        return {
            "sprint_id": _id_of(sprint),
            "sprint_name": sprint.name,
            "started_at": getattr(sprint, "start_date", None),
            "moved_issues_count": len(moved_issues),
            "moved_issues": moved_issues,
            "errors": errors,
            "message": f"Started sprint '{sprint.name}'"
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
            # fallback: find by issue.sprint link (match many common shapes: ObjectId, DBRef, nested $id/id, and string)
            conds = []
            try:
                obj_id = ObjectId(str(sprint.id))
            except Exception:
                obj_id = None
            if obj_id:
                # match when sprint stored as ObjectId, nested $id or id, or DBRef
                conds.extend([
                    {"sprint": obj_id},
                    {"sprint.$id": obj_id},
                    {"sprint.id": obj_id},
                    {"sprint": DBRef("sprints", obj_id)},
                ])
            # always include string forms (some records store link as plain string)
            conds.extend([
                {"sprint": str(sprint.id)},
                {"sprint.$id": str(sprint.id)},
                {"sprint.id": str(sprint.id)},
            ])
            # deduplicate and build $or
            unique = []
            seen = set()
            for c in conds:
                key = str(c)
                if key not in seen:
                    unique.append(c)
                    seen.add(key)
            cursor_filter = unique[0] if len(unique) == 1 else {"$or": unique}
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

                # Move ALL sprint issues off the board: clear sprint link and set location=backlog
                try:
                    # build list of ObjectId values where possible
                    ids_obj = []
                    for d in docs:
                        _id_raw = d.get("_id")
                        try:
                            ids_obj.append(ObjectId(str(_id_raw)))
                        except Exception:
                            ids_obj.append(str(_id_raw))
                    # attempt ObjectId-based update first
                    try:
                        await issues_col.update_many({"_id": {"$in": [i for i in ids_obj if isinstance(i, ObjectId)]}}, {"$set": {"sprint": None, "location": "backlog"}})
                    except Exception:
                        pass
                    # ensure string forms are updated too
                    try:
                        await issues_col.update_many({"_id": {"$in": [i for i in ids_obj if not isinstance(i, ObjectId)]}}, {"$set": {"sprint": None, "location": "backlog"}})
                    except Exception:
                        pass
                    # also ensure backlog document contains these items
                    try:
                        proj_id = _id_of(sprint.project) or str(getattr(sprint, "project", None))
                        await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": {"$each": ids_obj}}}, upsert=True)
                    except Exception:
                        pass
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

        # ensure ALL sprint issues are removed from board after completion (clear sprint + move to backlog)
        try:
            ids_obj = []
            for d in docs:
                _id_raw = d.get("_id")
                try:
                    ids_obj.append(ObjectId(str(_id_raw)))
                except Exception:
                    ids_obj.append(str(_id_raw))

            try:
                await issues_col.update_many({"_id": {"$in": [i for i in ids_obj if isinstance(i, ObjectId)]}}, {"$set": {"sprint": None, "location": "backlog"}})
            except Exception:
                pass
            try:
                await issues_col.update_many({"_id": {"$in": [i for i in ids_obj if not isinstance(i, ObjectId)]}}, {"$set": {"sprint": None, "location": "backlog"}})
            except Exception:
                pass
            try:
                proj_id = _id_of(sprint.project) or str(getattr(sprint, "project", None))
                await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": {"$each": ids_obj}}}, upsert=True)
            except Exception:
                pass
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
        Return completed sprints (optionally filtered by project_id).
        For each sprint include only issues that are actually in the final column (treated as completed),
        and include simple issue details.
        """
        sprints_col = Sprint.get_motor_collection()
        issues_col = Issue.get_motor_collection()

        # load completed sprints
        docs = [d async for d in sprints_col.find({"completed_at": {"$ne": None}})]

        import re

        def _extract_hex(s: Any) -> Optional[str]:
            if s is None:
                return None
            try:
                if isinstance(s, dict):
                    for k in ("$id", "id", "_id"):
                        if k in s and s[k]:
                            try:
                                return re.search(r"[0-9a-fA-F]{24}", str(s[k])).group(0).lower()
                            except Exception:
                                pass
                    s = str(s)
                else:
                    s = str(s)
            except Exception:
                return None
            m = re.search(r"[0-9a-fA-F]{24}", s)
            return m.group(0).lower() if m else s

        def _norm_status(s: Any) -> str:
            if not s:
                return ""
            return re.sub(r"[^a-z0-9]", "", str(s).lower())

        # normalize incoming project_id (may already be hex, or long form)
        project_hex = None
        if project_id:
            project_hex = _extract_hex(project_id)

        if project_hex:
            filtered = [d for d in docs if _extract_hex(d.get("project") or d.get("project_id")) == project_hex]
        else:
            filtered = docs

        out: List[Dict[str, Any]] = []
        for d in filtered:
            proj_hex = _extract_hex(d.get("project") or d.get("project_id"))
            completed_ids = d.get("completed_issue_ids") or []

            # determine board final status for this project (fallback to 'done')
            final_status = "done"
            try:
                if proj_hex:
                    board = await Board.find_one({"project_id": proj_hex})
                else:
                    board = await Board.find_one({"project_id": _extract_hex(d.get("project") or d.get("project_id") or "")})
                if board and getattr(board, "columns", None):
                    last_col = max(board.columns, key=lambda c: getattr(c, "position", 0))
                    final_status = getattr(last_col, "status", None) or getattr(last_col, "name", None) or final_status
            except Exception:
                final_status = "done"

            # fetch issue documents for the stored completed_issue_ids
            issues_list: List[Dict[str, Any]] = []
            if completed_ids:
                # build ObjectId/string list
                q_ids = []
                for iid in completed_ids:
                    try:
                        q_ids.append(ObjectId(str(iid)))
                    except Exception:
                        q_ids.append(str(iid))
                # query issues
                try:
                    raw_issues = [r async for r in issues_col.find({"_id": {"$in": q_ids}})]
                except Exception:
                    raw_issues = []
                # include only issues whose status matches final_status (normalized)
                for ri in raw_issues:
                    st = ri.get("status")
                    if _norm_status(st) == _norm_status(final_status):
                        issues_list.append({
                            "id": str(ri.get("_id")),
                            "key": ri.get("key"),
                            "name": ri.get("name"),
                            "status": ri.get("status"),
                            "type": ri.get("type"),
                            "assignee_id": ri.get("assignee_id") or None,
                            "created_at": ri.get("created_at"),
                        })

            out.append({
                "id": str(d.get("_id")),
                "name": d.get("name"),
                "project_id": proj_hex,
                "start_date": d.get("start_date"),
                "end_date": d.get("end_date"),
                "completed_at": d.get("completed_at"),
                # filtered ids and details
                "completed_issue_ids": [i["id"] for i in issues_list],
                "completed_issues": issues_list,
                "issue_count": len(issues_list),
            })

        return out


# ...existing code...
    async def list_running_sprints(self, project_id: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
        """
        GET /sprints/running/all
        Return running sprints; if project_id provided, return running sprints for that project.
        Only sprints explicitly marked active (started) are considered running.
        Response: {"running_count": n, "sprints": [{"sprint_running": True, "sprint_id": "...", "sprint_name": "..."}, ...]}
        """
        # permission: if filtering by project ensure the user can view it
        # if project_id:
        #     if not await PermissionService.can_view_project(project_id, str(current_user.id)):
        #         raise HTTPException(status_code=403, detail="No access to project")

        sprints_col = Sprint.get_motor_collection()

        # ...existing code...
        def _proj_clause(pid: str):
            clauses = []
            try:
                pid_obj = ObjectId(str(pid))
                clauses.append({"project": pid_obj})
                clauses.append({"project.$id": pid_obj})
                clauses.append({"project.id": pid_obj})
            except Exception:
                pass
            # also match string forms
            clauses.append({"project": str(pid)})
            clauses.append({"project_id": str(pid)})
            clauses.append({"project.id": str(pid)})
            return {"$or": clauses}


        # Only consider sprints that were explicitly started (active=True) and not completed
        base = {
            "active": True,
            "$or": [
                {"completed_at": {"$exists": False}},
                {"completed_at": None}
            ]
        }

        query = {"$and": [base, _proj_clause(project_id)]} if project_id else base

        docs = [d async for d in sprints_col.find(query).sort([("start_date", 1)])]
        out: List[Dict[str, Any]] = []
        for d in docs:
            out.append({
                "sprint_running": True,
                "sprint_id": str(d.get("_id")),
                "sprint_name": d.get("name"),
            })
        running_count = len(out)
        if running_count == 0:
            # explicit, non-empty response when no running sprint for the project
            return {
                "running": False,
                "running_count": 0,
                "sprints": [],
                "message": "No sprint running in this project"
            }

        return {
            "running": True,
            "running_count": running_count,
            "sprints": out
        }

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
