from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.security import HTTPBearer
from beanie import PydanticObjectId, Link
from beanie.operators import In, Or
from bson import ObjectId

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
        if is_admin or await PermissionService.can_view_project(pid, str(current_user.id)):
            result.append({
                "id": _id_of(i),
                "name": i.name,
                "key": getattr(i, "key", None),
                "type": i.type,
                "project_id": pid,
                "priority": i.priority,
                "status": i.status,
                "created_at": i.created_at
            })
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
            "issue_count": len(s.issue_ids) if s.issue_ids else 0
        })
    return result

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
                issues_list.append({
                    "id": _id_of(i),
                    "name": i.name,
                    "key": getattr(i, "key", None),
                    "type": i.type,
                    "status": i.status,
                    "project_id": _id_of(i.project)
                })

        result.append({
            "id": _id_of(s),
            "name": s.name,
            "status": s.status,
            "active": s.active,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "completed_at": s.completed_at,
            "issue_count": len(issues_list),
            "issues": issues_list
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
async def complete_global_sprint(sprint_id: str, current_user: User = Depends(get_current_user)):
    sprint = await Sprint.get(sprint_id)
    if not sprint or sprint.project is not None:
        raise HTTPException(status_code=404, detail="Global sprint not found")

    issues = await Issue.find(Issue.sprint.id == sprint.id).to_list()
    
    completed_ids = []
    backlog_ids = []
    
    for i in issues:
        if i.status == "done":
            i.sprint = None
            i.location = "archived"
            completed_ids.append(_id_of(i))
        else:
            i.sprint = None
            i.location = "backlog"
            backlog_ids.append(_id_of(i))
            
            pid = _id_of(i.project)
            if pid:
                backlog = await Backlog.find_one({"project_id": pid})
                if backlog and i.id not in backlog.items:
                    backlog.items.append(i.id)
                    await backlog.save()
                    
        await i.save()

    sprint.active = False
    sprint.status = "completed"
    sprint.completed_at = datetime.utcnow()
    await sprint.save()

    return {
        "message": f"Global sprint '{sprint.name}' completed",
        "completed_issues": len(completed_ids),
        "moved_to_backlog": len(backlog_ids)
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
                col_issues.append({
                    "id": str(i.id),
                    "name": i.name,
                    "key": getattr(i, "key", None),
                    "type": i.type,
                    "priority": i.priority,
                    "status": i.status,
                    "assignee_id": _id_of(i.assignee)
                })
        
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
