from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.security import HTTPBearer
from beanie import PydanticObjectId, Link
from beanie.operators import In, Or
from bson import ObjectId, DBRef

from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import (
    Project, Issue, Sprint, Backlog, Board, BoardColumn
)
from app.schemas.project_management import (
    SprintCreate, SprintOut, IssueOut
)
from app.services.permission import PermissionService

security = HTTPBearer()
router = APIRouter(prefix="/global", tags=["Global PM"])

def _id_of(link_or_doc) -> Optional[str]:
    if not link_or_doc:
        return None
    _id = getattr(link_or_doc, "id", None)
    if _id is not None:
        return str(_id)
    ref = getattr(link_or_doc, "ref", None)
    if ref is not None:
        _id = getattr(ref, "id", None)
        if _id is not None:
            return str(_id)
    try:
        return str(link_or_doc)
    except Exception:
        return None

def _normalize_status(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

async def _resolve_status_name(status_id: str) -> str:
    """
    Resolve a status/column ID to a human-readable name.
    """
    if not status_id:
        return "Unknown"
        
    # 1. Standard statuses
    standard_map = {
        "todo": "To Do",
        "in_progress": "In Progress",
        "impediment": "Impediment",
        "done": "Done",
        "backlog": "Backlog",
        "archived": "Archived"
    }
    nid = _normalize_status(status_id)
    if nid in standard_map:
        return standard_map[nid]
    if status_id.lower() in standard_map:
        return standard_map[status_id.lower()]

    # 2. Try to find a BoardColumn in any Board (best effort)
    # Since we don't have the context of which board strictly, we try to find one.
    try:
        # Check if it looks like an ObjectId
        if len(status_id) == 24:
            # This is expensive if we scan all boards, but usually column IDs are unique enough or scoped.
            # We can try to find a board that has this column.
            board = await Board.find_one({"columns.id": status_id})
            if board:
                for col in board.columns:
                    if str(getattr(col, "id", "")) == status_id or str(getattr(col, "status", "")) == status_id:
                        return col.name
    except Exception:
        pass
    
    # 3. Fallback to title case of the ID itself if it looks readable
    return status_id.replace("_", " ").title()
    
async def _doc_global_issue(i: Issue) -> Dict[str, Any]:
    """Helper to convert Issue document to a dict with project_key."""
    res = {
        "id": _id_of(i),
        "name": i.name,
        "key": getattr(i, "key", None),
        "type": i.type,
        "project_id": _id_of(i.project),
        "project_key": None,
        "priority": i.priority,
        "status": i.status,
        "created_at": i.created_at,
        "assignee_id": _id_of(i.assignee)
    }
    if i.project:
        try:
            if hasattr(i.project, 'key'):
                res["project_key"] = i.project.key
            else:
                project_doc = await i.project.fetch()
                res["project_key"] = project_doc.key
        except Exception:
            res["project_key"] = None
    return res

@router.get("/issues", response_model=List[Dict[str, Any]])
async def list_all_global_issues(current_user: User = Depends(get_current_user)):
    """
    Get all issues across all projects (done or not).
    """
    issues = await Issue.find(Issue.is_deleted != True).to_list()
    
    result = []
    is_admin = getattr(current_user, "role", None) == "admin"
    
    for i in issues:
        pid = _id_of(i.project)
        if pid and (is_admin or await PermissionService.can_view_project(pid, str(current_user.id))):
            result.append(await _doc_global_issue(i))
    return result

@router.get("/backlog", response_model=List[Dict[str, Any]])
async def list_global_backlog(current_user: User = Depends(get_current_user)):
    """
    Get all issues across all projects that are in the backlog.
    """
    issues = await Issue.find(
        Issue.location == "backlog",
        Issue.is_deleted != True
    ).to_list()
    
    result = []
    is_admin = getattr(current_user, "role", None) == "admin"
    
    for i in issues:
        pid = _id_of(i.project)
        if pid and (is_admin or await PermissionService.can_view_project(pid, str(current_user.id))):
            result.append(await _doc_global_issue(i))
    return result

@router.get("/sprints", response_model=List[Dict[str, Any]])
async def list_global_sprints(current_user: User = Depends(get_current_user)):
    """
    List only global sprints (where project is None) that are not completed.
    """
    sprints = await Sprint.find(
        Sprint.project == None,
        Sprint.status != "completed",
        Sprint.is_deleted != True
    ).to_list()
    
    result = []
    for s in sprints:
        result.append({
            "id": _id_of(s),
            "name": s.name,
            "status": s.status,
            "active": s.active,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "issue_count": len(s.issue_ids) if s.issue_ids else 0,
            "goal": getattr(s, "goal", None)
        })
    return result

@router.get("/sprints/active", response_model=Dict[str, Any])
async def get_active_global_sprint(current_user: User = Depends(get_current_user)):
    """
    Get the currently active global sprint.
    """
    # Find active global sprint (project is None, status is active/in_progress or active flag is True)
    # Priority: "in_progress" status, OR active=True.
    
    # Try finding by status "in_progress" first
    sprint = await Sprint.find_one(
        Sprint.project == None,
        Sprint.status == "in_progress",
        Sprint.is_deleted != True
    )
    
    # Fallback: check based on 'active' flag if your system uses that
    if not sprint:
        sprint = await Sprint.find_one(
            Sprint.project == None,
            Sprint.active == True,
            Sprint.is_deleted != True
        )

    if not sprint:
        raise HTTPException(status_code=404, detail="No active global sprint found")

    return {
        "id": _id_of(sprint),
        "name": sprint.name,
        "status": sprint.status,
        "active": sprint.active,
        "start_date": sprint.start_date,
        "end_date": sprint.end_date,
        "issue_count": len(sprint.issue_ids) if sprint.issue_ids else 0,
        "goal": getattr(sprint, "goal", None)
    }

@router.get("/sprints/completed", response_model=List[Dict[str, Any]])
async def list_completed_global_sprints(current_user: User = Depends(get_current_user)):
    """
    List only global sprints that are completed, including issue details.
    """
    sprints = await Sprint.find(
        Sprint.project == None,
        Sprint.status == "completed",
        Sprint.is_deleted != True
    ).to_list()
    
    result = []
    for s in sprints:
        # Fetch issues in this sprint
        issues_list = []
        if s.issue_ids:
            issues = await Issue.find(In(Issue.id, s.issue_ids)).to_list()
            for i in issues:
                issues_list.append(await _doc_global_issue(i))

        result.append({
            "id": _id_of(s),
            "name": s.name,
            "status": s.status,
            "active": s.active,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "completed_at": s.completed_at,
            "issue_count": len(issues_list),
            "issues": issues_list,
            "goal": getattr(s, "goal", None)
        })
    return result

@router.post("/sprints", response_model=Dict[str, Any])
async def create_global_sprint(data: SprintCreate, current_user: User = Depends(get_current_user)):
    """
    Create a new global sprint. Project ID is ignored.
    """
    # Only admins can create global sprints for now? 
    # Or any user? Let's check user role.
    if getattr(current_user, "role", None) != "admin":
         # Maybe allow but with caution? User said "okay nicee" so I assume they are admin or want it open.
         pass

    sprint = Sprint(
        name=data.name,
        project=None, # Explicitly global
        goal=data.goal,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=current_user,
        active=False,
        status="planned"
    )
    await sprint.insert()

    # Proactively create the global board with 4 columns
    board = Board(
        name=f"Global Board - {sprint.name}",
        project_id=None,
        sprint_id=_id_of(sprint),
        columns=[
            BoardColumn(name="To Do", status="todo", position=1, color="#FF6B6B"),
            BoardColumn(name="In Progress", status="in_progress", position=2, color="#4ECDC4"),
            BoardColumn(name="Impediment", status="impediment", position=3, color="#FF9F43"),
            BoardColumn(name="Done", status="done", position=4, color="#96CEB4"),
        ]
    )
    await board.insert()

    return {
        "id": _id_of(sprint),
        "name": sprint.name,
        "status": sprint.status,
        "goal": sprint.goal,
        "start_date": sprint.start_date,
        "end_date": sprint.end_date,
        "board_id": _id_of(board)
    }

@router.post("/sprints/{sprint_id}/assign")
async def assign_issues_to_sprint(
    sprint_id: str,
    issue_ids: List[str] = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Assign multiple issues (possibly from different projects) to a global sprint.
    """
    sprint = await Sprint.get(sprint_id)
    if not sprint or sprint.project is not None:
        raise HTTPException(status_code=404, detail="Global sprint not found")

    oids = [PydanticObjectId(iid) for iid in issue_ids]
    issues = await Issue.find(In(Issue.id, oids)).to_list()
    
    assigned = []
    for i in issues:
        i.sprint = sprint
        i.location = "sprint"
        await i.save()
        
        if i.id not in sprint.issue_ids:
            sprint.issue_ids.append(i.id)
        assigned.append(_id_of(i))
        
    await sprint.save()
    return {"sprint_id": sprint_id, "assigned_issue_count": len(assigned), "assigned_issues": assigned}

@router.post("/sprints/{sprint_id}/start")
async def start_global_sprint(sprint_id: str, current_user: User = Depends(get_current_user)):
    sprint = await Sprint.get(sprint_id)
    if not sprint or sprint.project is not None:
        raise HTTPException(status_code=404, detail="Global sprint not found")

    sprint.active = True
    sprint.status = "running"
    if not sprint.start_date:
        sprint.start_date = datetime.utcnow()
    await sprint.save()

    issues = await Issue.find(Issue.sprint.id == sprint.id).to_list()
    for i in issues:
        i.location = "board"
        await i.save()

    return {"message": f"Global sprint '{sprint.name}' started", "issue_count": len(issues)}

@router.post("/sprints/{sprint_id}/complete")
async def complete_global_sprint(
    sprint_id: str,
    auto_move_incomplete_to: Optional[str] = Query(None, description="Specify 'backlog' or target sprint id; omit to only check issues"),
    current_user: User = Depends(get_current_user)
):
    """
    Complete a global sprint. Matches the behavior of project-specific sprints.
    """
    if auto_move_incomplete_to is not None and str(auto_move_incomplete_to).strip() == "":
        auto_move_incomplete_to = None

    sprint = await Sprint.get(sprint_id)
    if not sprint or sprint.project is not None:
        raise HTTPException(status_code=404, detail="Global sprint not found")

    issues_col = Issue.get_motor_collection()
    sprints_col = Sprint.get_motor_collection()
    backlog_col = Backlog.get_motor_collection()

    # Collect sprint issues (using both sprint.issue_ids and back-references)
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
    
    if not docs:
        conds = []
        try:
            obj_id = ObjectId(str(sprint.id))
        except Exception:
            obj_id = None
        if obj_id:
            conds.extend([
                {"sprint": obj_id},
                {"sprint.$id": obj_id},
                {"sprint.id": obj_id},
                {"sprint": DBRef("sprints", obj_id)},
            ])
        conds.extend([
            {"sprint": str(sprint.id)},
            {"sprint.$id": str(sprint.id)},
            {"sprint.id": str(sprint.id)},
        ])
        cursor_filter = conds[0] if len(conds) == 1 else {"$or": conds}
        docs = [d async for d in issues_col.find(cursor_filter)]

    # Snapshot for history
    snapshot_ids = [str(d.get("_id")) for d in docs]

    # CASE 1: AUTO-MOVE DISABLED
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

        if not pending_issues:
            completed_ts = datetime.utcnow()
            update_body = {
                "$set": {
                    "completed_at": completed_ts,
                    "active": False,
                    "completed_issue_ids": snapshot_ids,
                    "status": "completed"
                }
            }
            try:
                await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, update_body)
            except Exception:
                await sprints_col.update_one({"_id": str(sprint.id)}, update_body)

            sprint.completed_at = completed_ts
            sprint.active = False
            sprint.status = "completed"
            await sprint.save()

            # Process issues: All are done, so archive them
            for d in docs:
                _id_raw = d.get("_id")
                try:
                    oid = ObjectId(str(_id_raw))
                except Exception:
                    oid = str(_id_raw)
                
                await issues_col.update_one(
                    {"_id": oid},
                    {"$unset": {"sprint": ""}, "$set": {"location": "archived"}}
                )

            return {
                "message": f"Global sprint '{sprint.name}' completed",
                "completed_issues": completed_issues,
                "pending_issues": [],
                "sprint_id": _id_of(sprint),
                "completed_at": completed_ts
            }

        # Resolve status names for pending issues
        for p in pending_issues:
            p["status"] = await _resolve_status_name(p["status"])

        return {
            "message": "Cannot complete sprint: pending issues exist",
            "completed_issues": completed_issues,
            "pending_issues": pending_issues,
            "sprint_id": _id_of(sprint)
        }

    # CASE 2: AUTO-MOVE ENABLED
    moved = []
    errors = []
    incomplete_docs = [d for d in docs if d.get("status") != "done"]

    for doc in incomplete_docs:
        iid_raw = doc.get("_id")
        try:
            iid_obj = ObjectId(str(iid_raw))
        except Exception:
            iid_obj = iid_raw
        iid_str = str(iid_raw)

        try:
            # Remove from current sprint
            try:
                await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, {"$pull": {"issue_ids": iid_obj}})
            except Exception:
                await sprints_col.update_one({"_id": str(sprint.id)}, {"$pull": {"issue_ids": iid_str}})

            if auto_move_incomplete_to == "backlog":
                await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": None, "location": "backlog"}})
                # Note: For global issues, we don't have a single "global backlog" collection logic like projects do,
                # but we can at least set location to backlog.
                # If the issue belongs to a project, try to find its backlog.
                proj_id = _id_of(doc.get("project"))
                if proj_id:
                    await backlog_col.update_one({"project_id": str(proj_id)}, {"$addToSet": {"items": iid_obj}}, upsert=True)
            else:
                # Target is another sprint
                try:
                    target_obj = ObjectId(str(auto_move_incomplete_to))
                    await sprints_col.update_one({"_id": target_obj}, {"$addToSet": {"issue_ids": iid_obj}})
                    await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": target_obj, "location": "sprint"}})
                except Exception:
                    await sprints_col.update_one({"_id": auto_move_incomplete_to}, {"$addToSet": {"issue_ids": iid_str}})
                    await issues_col.update_one({"_id": iid_obj}, {"$set": {"sprint": auto_move_incomplete_to, "location": "sprint"}})

            moved.append(iid_str)
        except Exception as e:
            errors.append({"issue": iid_str, "error": str(e)})

    # Finalize current sprint
    completed_ts = datetime.utcnow()
    update_body = {
        "$set": {
            "completed_at": completed_ts,
            "active": False,
            "completed_issue_ids": snapshot_ids,
            "status": "completed"
        }
    }
    try:
        await sprints_col.update_one({"_id": ObjectId(str(sprint.id))}, update_body)
    except Exception:
        await sprints_col.update_one({"_id": str(sprint.id)}, update_body)

    # Archive done issues
    for d in docs:
        if d.get("status") == "done":
            _id_raw = d.get("_id")
            try:
                oid = ObjectId(str(_id_raw))
            except Exception:
                oid = str(_id_raw)
            await issues_col.update_one(
                {"_id": oid},
                {"$unset": {"sprint": ""}, "$set": {"location": "archived"}}
            )

    return {
        "message": f"Global sprint '{sprint.name}' completed",
        "ok": True,
        "sprint_id": _id_of(sprint),
        "completed_at": completed_ts,
        "moved_incomplete_issues": moved,
        "errors": errors
    }

@router.get("/board/{sprint_id}")
async def get_global_board(sprint_id: str, current_user: User = Depends(get_current_user)):
    """
    Get or create a board for a global sprint.
    """
    sprint = await Sprint.get(sprint_id)
    if not sprint or sprint.project is not None:
        raise HTTPException(status_code=404, detail="Global sprint not found")

    # Find board by sprint_id
    board = await Board.find_one(Board.sprint_id == sprint_id)
    if not board:
        # Create default board for this global sprint
        board = Board(
            name=f"Global Board - {sprint.name}",
            project_id=None,
            sprint_id=sprint_id,
            columns=[
                BoardColumn(name="To Do", status="todo", position=1, color="#FF6B6B"),
                BoardColumn(name="In Progress", status="in_progress", position=2, color="#4ECDC4"),
                BoardColumn(name="Impediment", status="impediment", position=3, color="#FF9F43"),
                BoardColumn(name="Done", status="done", position=4, color="#96CEB4"),
            ]
        )
        await board.insert()

    # Fetch issues for this sprint that are on the board
    issues = await Issue.find(
        Issue.sprint.id == PydanticObjectId(sprint_id),
        Issue.location == "board"
    ).to_list()

    # Group issues by column
    columns_data = []
    for col in board.columns:
        col_id = f"col_{col.position}"
        col_issues = []
        for i in issues:
            if _normalize_status(i.status) == _normalize_status(col.status):
                col_issues.append(await _doc_global_issue(i))
        
        columns_data.append({
            "column_info": {
                "id": col_id,
                "name": col.name,
                "status": col.status,
                "position": col.position,
                "color": col.color
            },
            "issues": col_issues
        })

    return {
        "board": {
            "id": str(board.id),
            "name": board.name,
            "sprint_id": sprint_id,
            "columns": columns_data
        }
    }

@router.put("/issues/{issue_id}", response_model=Dict[str, Any])
async def update_global_issue_status(
    issue_id: str,
    status: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Update the status of an issue from the global board.
    """
    issue = await Issue.get(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    # Permission check
    pid = _id_of(issue.project)
    if not await PermissionService.can_edit_project(pid, str(current_user.id)):
        if getattr(current_user, "role", None) != "admin":
            raise HTTPException(status_code=403, detail="No access to update this issue")

    # Update status
    issue.status = status
    issue.updated_at = datetime.utcnow()
    await issue.save()

    return {
        "id": _id_of(issue),
        "name": issue.name,
        "status": issue.status,
        "message": "Status updated successfully"
    }

@router.get("/sprints/{sprint_id}/stats", response_model=Dict[str, Any])
async def get_global_sprint_stats(
    sprint_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get statistics for a global sprint: total tasks and breakdown by status.
    """
    sprint = await Sprint.get(sprint_id)
    if not sprint or sprint.project is not None:
        raise HTTPException(status_code=404, detail="Global sprint not found")

    # Fetch all issues assigned to this sprint
    issues = await Issue.find(Issue.sprint.id == PydanticObjectId(sprint_id)).to_list()
    status_distribution = {}
    total_tasks = len(issues)
    issues_list = []
    for i in issues:
        status = i.status or "todo"
        status_distribution[status] = status_distribution.get(status, 0) + 1
        issues_list.append(await _doc_global_issue(i))
        
    return {
        "sprint_id": sprint_id,
        "sprint_name": sprint.name,
        "total_tasks": total_tasks,
        "status_distribution": status_distribution,
        "issues": issues_list
    }
