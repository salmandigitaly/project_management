from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from beanie import PydanticObjectId
from bson import ObjectId

from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import (
    Project, Epic, Feature, Issue, Sprint, Comment
)
from app.schemas.project_management import (
    RecycleBinItem, RecycleBinResponse
)
from app.services.permission import PermissionService

security = HTTPBearer()
router = APIRouter(prefix="/recycle-bin", tags=["recycle-bin"])

def _id_of(doc) -> str:
    return str(doc.id) if hasattr(doc, "id") else str(doc)

@router.get("/", response_model=RecycleBinResponse)
async def list_deleted_items(
    project_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """
    List all soft-deleted items. 
    Admin sees everything. Regular users see only items from projects they can view.
    If project_id is provided, filter items by that project.
    """
    items = []
    
    # helper to check access
    async def can_access(proj_id_in):
        pid_s = str(proj_id_in)
        if project_id and pid_s != project_id:
            return False
        if current_user.role == "admin":
            return True
        return await PermissionService.can_view_project(pid_s, str(current_user.id))

    # 1. Projects
    # If project_id is provided, we only check that specific project if it is deleted
    if project_id:
        p = await Project.get(project_id)
        if p and p.is_deleted and await can_access(p.id):
            items.append(RecycleBinItem(
                id=str(p.id),
                type="project",
                name=p.name,
                key=p.key,
                deleted_at=p.deleted_at or datetime.utcnow(),
                details={"description": p.description}
            ))
    else:
        async for p in Project.find(Project.is_deleted == True):
            if await can_access(p.id):
                items.append(RecycleBinItem(
                    id=str(p.id),
                    type="project",
                    name=p.name,
                    key=p.key,
                    deleted_at=p.deleted_at or datetime.utcnow(),
                    details={"description": p.description}
                ))

    # 2. Epics
    epics_find = Epic.find(Epic.is_deleted == True)
    if project_id:
        try:
            pid = PydanticObjectId(project_id)
            epics_find = Epic.find(Epic.is_deleted == True, Epic.project.id == pid)
        except Exception:
            pass
    
    async for e in epics_find:
        try:
            # resolve pid for access check
            actual_pid = str(e.project.id) if hasattr(e.project, "id") else str(e.project.ref.id)
            if await can_access(actual_pid):
                items.append(RecycleBinItem(
                    id=str(e.id),
                    type="epic",
                    name=e.name,
                    key=e.key,
                    deleted_at=e.deleted_at or datetime.utcnow(),
                    details={"description": e.description}
                ))
        except Exception:
            continue

    # 3. Sprints
    sprints_find = Sprint.find(Sprint.is_deleted == True)
    if project_id:
        try:
            pid = PydanticObjectId(project_id)
            sprints_find = Sprint.find(Sprint.is_deleted == True, Sprint.project.id == pid)
        except Exception:
            pass

    async for s in sprints_find:
        try:
            actual_pid = str(s.project.id) if hasattr(s.project, "id") else str(s.project.ref.id)
            if await can_access(actual_pid):
                items.append(RecycleBinItem(
                    id=str(s.id),
                    type="sprint",
                    name=s.name,
                    deleted_at=s.deleted_at or datetime.utcnow(),
                    details={
                        "goal": s.goal,
                        "status": getattr(s, "status", "planned"),
                        "start_date": s.start_date,
                        "end_date": s.end_date
                    }
                ))
        except Exception:
            continue

    # 4. Issues
    issues_find = Issue.find(Issue.is_deleted == True)
    if project_id:
        try:
            pid = PydanticObjectId(project_id)
            issues_find = Issue.find(Issue.is_deleted == True, Issue.project.id == pid)
        except Exception:
            pass

    async for i in issues_find:
        try:
            actual_pid = str(i.project.id) if hasattr(i.project, "id") else str(i.project.ref.id)
            if await can_access(actual_pid):
                items.append(RecycleBinItem(
                    id=str(i.id),
                    type="issue",
                    name=i.name,
                    key=getattr(i, "key", None),
                    deleted_at=i.deleted_at or datetime.utcnow(),
                    details={
                        "status": i.status,
                        "priority": i.priority,
                        "type": i.type,
                        "assignee_id": str(i.assignee.id) if hasattr(i.assignee, "id") else str(i.assignee.ref.id) if i.assignee else None,
                        "location": i.location
                    }
                ))
        except Exception:
            continue

    # 5. Features
    features_find = Feature.find(Feature.is_deleted == True)
    if project_id:
        try:
            pid = PydanticObjectId(project_id)
            features_find = Feature.find(Feature.is_deleted == True, Feature.project_id == pid)
        except Exception:
            pass

    async for f in features_find:
        try:
            actual_pid = str(f.project_id)
            if await can_access(actual_pid):
                items.append(RecycleBinItem(
                    id=str(f.id),
                    type="feature",
                    name=f.name,
                    deleted_at=f.deleted_at or datetime.utcnow(),
                    details={
                        "status": f.status,
                        "priority": f.priority,
                        "description": f.description
                    }
                ))
        except Exception:
            continue

    # sort by deleted_at descending
    items.sort(key=lambda x: x.deleted_at, reverse=True)
    
    return RecycleBinResponse(items=items, total=len(items))

@router.post("/restore/{item_type}/{item_id}")
async def restore_item(
    item_type: Literal["project", "epic", "sprint", "issue", "feature"],
    item_id: str,
    current_user: User = Depends(get_current_user)
):
    model_map = {
        "project": Project,
        "epic": Epic,
        "sprint": Sprint,
        "issue": Issue,
        "feature": Feature
    }
    
    model = model_map.get(item_type)
    if not model:
        raise HTTPException(status_code=400, detail="Invalid item type")
    
    item = await model.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"{item_type.capitalize()} not found")
    
    # Permission check (simplified: must be admin or have access to project)
    # For now, let's just check if they can edit the project
    proj_id = None
    if item_type == "project":
        proj_id = str(item.id)
    elif item_type == "feature":
        proj_id = str(item.project_id)
    else:
        proj_id = str(item.project.id) if hasattr(item.project, "id") else str(item.project.ref.id)

    if not await PermissionService.can_edit_project(proj_id, str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access to restore")

    item.is_deleted = False
    item.deleted_at = None
    await item.save()
    
    # --- Cascade Restore ---
    async def _cascade_restore(parent_id, item_type):
        update_q = {"$set": {"is_deleted": False, "deleted_at": None}}
        oid = ObjectId(str(parent_id))
        
        models = [Epic, Feature, Issue, Sprint, Comment]
        for m in models:
            try:
                col = m.get_motor_collection()
                # Query shapes for project or epic
                if item_type == "project":
                    qs = [{"project": oid}, {"project.$id": oid}, {"project.id": oid}, {"project_id": str(parent_id)}]
                else: # epic
                    qs = [{"epic": oid}, {"epic.$id": oid}, {"epic.id": oid}, {"epic_id": str(parent_id)}]
                
                for q in qs:
                    await col.update_many(q, update_q)
            except Exception:
                pass

    if item_type == "project":
        await _cascade_restore(item.id, "project")
    elif item_type == "epic":
        await _cascade_restore(item.id, "epic")
    elif item_type == "issue":
        # Restore subtasks
        try:
            await Issue.find(Issue.parent.id == item.id).update({"$set": {"is_deleted": False, "deleted_at": None}})
        except Exception:
            pass

    return {"message": f"{item_type.capitalize()} and its children restored successfully"}

@router.delete("/permanent/{item_type}/{item_id}")
async def permanent_delete(
    item_type: Literal["project", "epic", "sprint", "issue", "feature"],
    item_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Permanently delete an item from the database.
    Only admin can do this.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can permanently delete items")

    model_map = {
        "project": Project,
        "epic": Epic,
        "sprint": Sprint,
        "issue": Issue,
        "feature": Feature
    }
    
    model = model_map.get(item_type)
    if not model:
        raise HTTPException(status_code=400, detail="Invalid item type")
    
    item = await model.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"{item_type.capitalize()} not found")

    # --- Cascade Permanent Delete ---
    async def _cascade_hard_delete(parent_id, item_type):
        oid = ObjectId(str(parent_id))
        models = [Epic, Feature, Issue, Sprint, Comment]
        for m in models:
            try:
                col = m.get_motor_collection()
                if item_type == "project":
                    qs = [{"project": oid}, {"project.$id": oid}, {"project.id": oid}, {"project_id": str(parent_id)}]
                else: # epic
                    qs = [{"epic": oid}, {"epic.$id": oid}, {"epic.id": oid}, {"epic_id": str(parent_id)}]
                
                for q in qs:
                    await col.delete_many(q)
            except Exception:
                pass

    if item_type == "project":
        await _cascade_hard_delete(item.id, "project")
    elif item_type == "epic":
        await _cascade_hard_delete(item.id, "epic")
    elif item_type == "issue":
        # Hard delete subtasks
        try:
            await Issue.find(Issue.parent.id == item.id).delete()
        except Exception:
            pass

    await item.delete()
    return {"message": f"{item_type.capitalize()} and its children permanently deleted"}
