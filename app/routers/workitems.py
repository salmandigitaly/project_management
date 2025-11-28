# app/routers/workitems.py
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

        epics = await Epic.find(Epic.project.id == PydanticObjectId(project_id)).to_list()
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
        
        # Fetch the project to get its ID properly
        project = await epic.project.fetch()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if not await PermissionService.can_view_project(str(project.id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        # Get all issues for this epic
        issues = await Issue.find(Issue.epic.id == epic.id).to_list()
        
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
        if not await PermissionService.can_edit_project(str(epic.project.id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        await epic.delete()
        return {"message": "Epic deleted"}

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
class IssuesRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/issues", tags=["issues"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/", self.list_issues, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/", self.create_issue, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/{issue_id}", self.get_issue, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/{issue_id}", self.update_issue, methods=["PUT"], dependencies=deps)
        self.router.add_api_route("/{issue_id}", self.delete_issue, methods=["DELETE"], dependencies=deps)
        self.router.add_api_route("/{issue_id}/move", self.move_issue, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/{issue_id}/subtasks", self.add_subtask, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/move-multiple", self.move_multiple_issues, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/sprints/{sprint_id}/issues/{issue_id}", self.remove_issue_from_sprint, methods=["DELETE"], dependencies=deps)
    # async def list_issues(
    #     self,
    #     project_id: str = Query(...),
    #     sprint_id: Optional[str] = Query(None),
    #     epic_id: Optional[str] = Query(None),
    #     current_user: User = Depends(get_current_user),
    # ):
    #     if not await PermissionService.can_view_project(project_id, str(current_user.id)):
    #         raise HTTPException(status_code=403, detail="No access to project")

    #     base_q = Issue.project.id == PydanticObjectId(project_id)
    #     issues = await Issue.find(base_q).to_list()

    #     if sprint_id:
    #         issues = [i for i in issues if (i.sprint and _id_of(i.sprint) == sprint_id)]
    #     if epic_id:
    #         issues = [i for i in issues if (i.epic and _id_of(i.epic) == epic_id)]

    #     return [self._doc_issue(i) for i in issues]

    async def list_issues(
        self,
        project_id: str = Query(...),
        sprint_id: Optional[str] = Query(None),
        epic_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
    ):
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        base_q = Issue.project.id == PydanticObjectId(project_id)
        issues = await Issue.find(base_q).to_list()

        if sprint_id:
            issues = [i for i in issues if (i.sprint and _id_of(i.sprint) == sprint_id)]
        if epic_id:
            issues = [i for i in issues if (i.epic and _id_of(i.epic) == epic_id)]

        # Return issues with epic details
        return [await self._doc_issue_with_epic(i) for i in issues]
    

    async def _doc_issue_with_epic(self, i: Issue) -> Dict[str, Any]:
        issue_data = {
            "id": _id_of(i),
            "key": getattr(i, "key", None),
            "project_id": _id_of(i.project),
            "epic_id": _id_of(i.epic),
            "epic_name": None,  # Initialize as None
            "sprint_id": _id_of(i.sprint),
            "type": i.type,
            "name": i.name,
            "description": i.description,
            "priority": i.priority,
            "status": i.status,
            "assignee_id": _id_of(i.assignee),
            "parent_id": _id_of(i.parent),
            "story_points": i.story_points,
            "estimated_hours": i.estimated_hours,
            "time_spent_hours": i.time_spent_hours,
            "created_by": _id_of(getattr(i, "created_by", None)),
            "updated_by": _id_of(getattr(i, "updated_by", None)),
            "created_at": getattr(i, "created_at", None),
            "updated_at": getattr(i, "updated_at", None),
            "location": i.location,
        }
        
        # Add epic name if issue has an epic
        if i.epic:
            try:
                # If epic is already fetched, get name directly
                if hasattr(i.epic, 'name'):
                    issue_data["epic_name"] = i.epic.name
                else:
                    # If it's a Link, fetch it to get the name
                    epic_doc = await i.epic.fetch()
                    issue_data["epic_name"] = epic_doc.name
            except Exception:
                issue_data["epic_name"] = None
        
        return issue_data

    async def create_issue(self, data: IssueCreate, current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_view_project(str(data.project_id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        project = await Project.get(str(data.project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Generate key
        issue_count = await Issue.find(Issue.project.id == project.id).count()
        key = f"{project.key}-{issue_count + 1}"

        epic = await Epic.get(str(data.epic_id)) if getattr(data, "epic_id", None) else None
        sprint = await Sprint.get(str(data.sprint_id)) if getattr(data, "sprint_id", None) else None
        assignee = await User.get(str(data.assignee_id)) if getattr(data, "assignee_id", None) else None
        parent = await Issue.get(str(data.parent_id)) if getattr(data, "parent_id", None) else None
        feature = await Feature.get(str(data.feature_id)) if getattr(data, "feature_id", None) else None

        issue = Issue(
             key=key,
             project=project,
             epic=epic,
             sprint=sprint,
             type=data.type,
             name=data.name,
             description=data.description,
             priority=data.priority,
             assignee=assignee,
             parent=parent,
             story_points=data.story_points,
             estimated_hours=data.estimated_hours,
             created_by=current_user,
             updated_by=current_user,
             location=data.location,
            # persist feature id explicitly so it appears in API responses
            feature_id=PydanticObjectId(feature.id) if feature else None,
         )
        await issue.insert()

        # ADD ISSUE TO BACKLOG
        backlog = await Backlog.find_one({"project_id": str(project.id)})
        if backlog:
            # compare as strings to avoid ObjectId / string mismatches
            if not any(str(i) == str(issue.id) for i in backlog.items):
                # store as ObjectId-like (PydanticObjectId) to match model type
                backlog.items.append(PydanticObjectId(issue.id))
                await backlog.save()
        return self._doc_issue(issue)
    async def get_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        if not await PermissionService.can_view_project(_id_of(issue.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")
        return self._doc_issue(issue)

    async def update_issue(self, issue_id: str, data: IssueUpdate, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        # permission check removed: all authenticated users can update issues

        payload = data.dict(exclude_unset=True)

        # relation fields
        if "epic_id" in payload:
            epic_id = payload.pop("epic_id")
            issue.epic = await Epic.get(str(epic_id)) if epic_id else None
        if "sprint_id" in payload:
            sprint_id = payload.pop("sprint_id")
            issue.sprint = await Sprint.get(str(sprint_id)) if sprint_id else None
        if "assignee_id" in payload:
            assignee_id = payload.pop("assignee_id")
            issue.assignee = await User.get(str(assignee_id)) if assignee_id else None
        if "parent_id" in payload:
            parent_id = payload.pop("parent_id")
            issue.parent = await Issue.get(str(parent_id)) if parent_id else None
        if "feature_id" in payload:
            feature_id = payload.pop("feature_id")
            issue.feature = await Feature.get(str(feature_id)) if feature_id else None
            # also persist feature id field
            issue.feature_id = PydanticObjectId(feature_id) if feature_id else None

        await issue.set(payload)
        issue.updated_by = current_user
        issue.updated_at = datetime.utcnow()
        await issue.save()
        return self._doc_issue(issue)

    async def delete_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        # permission check removed: allow authenticated users to delete issues

        await issue.delete()
        return {"message": "Issue deleted"}

    async def move_issue(
        self,
        issue_id: str,
        to: Literal["backlog", "sprint"] = Query(...),
        sprint_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
    ):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        # permission check removed: allow authenticated users to move issues

        # Remove from old sprint's issue_ids (try both ObjectId and string)
        if issue.sprint:
            try:
                old_sid = _id_of(issue.sprint)
                # try as ObjectId container
                try:
                    await Sprint.get_motor_collection().update_one(
                        {"_id": ObjectId(str(old_sid))}, {"$pull": {"issue_ids": ObjectId(str(issue.id))}}
                    )
                except Exception:
                    await Sprint.get_motor_collection().update_one(
                        {"_id": ObjectId(str(old_sid))}, {"$pull": {"issue_ids": str(issue.id)}}
                    )
            except Exception:
                pass

        # Add to new sprint's issue_ids
        if to == "sprint":
            if not sprint_id:
                raise HTTPException(status_code=400, detail="sprint_id required when to=sprint")
            sprint = await Sprint.get(sprint_id)
            if not sprint:
                raise HTTPException(status_code=404, detail="Sprint not found")

            # attempt to add as ObjectId-like; fallback to string
            try:
                # try to store ObjectId form
                await Sprint.get_motor_collection().update_one(
                    {"_id": ObjectId(str(sprint.id))},
                    {"$addToSet": {"issue_ids": ObjectId(str(issue.id))}},
                    upsert=False,
                )
            except Exception:
                await Sprint.get_motor_collection().update_one(
                    {"_id": str(sprint.id)},
                    {"$addToSet": {"issue_ids": str(issue.id)}},
                    upsert=False,
                )

            # set issue.sprint to the Sprint document (Beanie link) and persist
            issue.sprint = sprint
        else:
            issue.sprint = None

        issue.location = to
        await issue.save()
        return self._doc_issue(issue)

    async def add_subtask(self, issue_id: str, data: IssueCreate, current_user: User = Depends(get_current_user)):
        parent = await Issue.get(issue_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent issue not found")
        # use helper to get parent id string
        if not await PermissionService.can_edit_workitem(_id_of(parent), str(current_user.id)):
             raise HTTPException(status_code=403, detail="No access")

        project = await Project.get(str(data.project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sub = Issue(
            project=project,
            epic=parent.epic,
            sprint=parent.sprint,
            type="subtask",
            name=data.name,
            description=data.description,
            priority=data.priority,
            assignee=await User.get(str(data.assignee_id)) if getattr(data, "assignee_id", None) else None,
            parent=parent,
            created_by=current_user,
            updated_by=current_user,
            location=parent.location,
        )
        await sub.insert()
        return self._doc_issue(sub)
    

    async def move_multiple_issues(
        self,
        move_data: Dict[str, Any] = None,
        to: Literal["backlog", "sprint"] = Query(...),
        sprint_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
    ):
        """
        Move multiple issues to a new location (backlog, sprint, or board)
        """
        if not move_data or "issue_ids" not in move_data:
            raise HTTPException(status_code=400, detail="No issue IDs provided")
        
        issue_ids = move_data["issue_ids"]
        
        if not issue_ids:
            raise HTTPException(status_code=400, detail="No issue IDs provided")

        moved_issues = []
        errors = []

        for issue_id in issue_ids:
            try:
                issue = await Issue.get(issue_id)
                if not issue:
                    errors.append(f"Issue {issue_id} not found")
                    continue

                # Remove from old sprint's issue_ids (both forms)
                if issue.sprint:
                    try:
                        old_sid = _id_of(issue.sprint)
                        try:
                            await Sprint.get_motor_collection().update_one(
                                {"_id": ObjectId(str(old_sid))},
                                {"$pull": {"issue_ids": ObjectId(str(issue.id))}},
                            )
                        except Exception:
                            await Sprint.get_motor_collection().update_one(
                                {"_id": ObjectId(str(old_sid))},
                                {"$pull": {"issue_ids": str(issue.id)}},
                            )
                    except Exception:
                        pass

                # Add to new sprint's issue_ids  
                if to == "sprint":
                    if not sprint_id:
                        errors.append(f"sprint_id required for issue {issue_id}")
                        continue
                    sprint = await Sprint.get(sprint_id)
                    if not sprint:
                        errors.append(f"Sprint not found for issue {issue_id}")
                        continue

                    # try to add as ObjectId then string
                    try:
                        await Sprint.get_motor_collection().update_one(
                            {"_id": ObjectId(str(sprint.id))},
                            {"$addToSet": {"issue_ids": ObjectId(str(issue.id))}},
                        )
                    except Exception:
                        await Sprint.get_motor_collection().update_one(
                            {"_id": str(sprint.id)},
                            {"$addToSet": {"issue_ids": str(issue.id)}},
                        )

                    issue.sprint = sprint
                else:
                    issue.sprint = None

                issue.location = to
                await issue.save()
                moved_issues.append(self._doc_issue(issue))

            except Exception as e:
                errors.append(f"Error moving issue {issue_id}: {str(e)}")

        return {
            "moved_issues": moved_issues,
            "total_moved": len(moved_issues),
            "errors": errors,
            "message": f"Successfully moved {len(moved_issues)} issues to {to}"
        }

    async def remove_issue_from_sprint(self, sprint_id: str = Path(...), issue_id: str = Path(...), current_user: User = Depends(get_current_user)):
        """
        DELETE /sprints/{sprint_id}/issues/{issue_id}
        Remove the issue from its sprint and move it to backlog.
        """
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Remove from old sprint.issue_ids if present
        if issue.sprint:
            try:
                old_sprint = await Sprint.get(_id_of(issue.sprint))
            except Exception:
                old_sprint = None
            if old_sprint:
                current_ids = getattr(old_sprint, "issue_ids", []) or []
                filtered = [i for i in current_ids if str(i) != str(issue.id)]
                old_sprint.issue_ids = filtered
                await old_sprint.save()

        # clear sprint reference on issue and move to backlog
        issue.sprint = None
        issue.location = "backlog"
        await issue.save()

        return {"message": "Issue removed", "issue_id": issue_id, "sprint_id": sprint_id}

    def _doc_issue(self, i: Issue) -> Dict[str, Any]:
        return {
            "id": _id_of(i),
            "key": getattr(i, "key", None),
            "project_id": _id_of(i.project),
            "epic_id": _id_of(i.epic),
            "sprint_id": _id_of(i.sprint),
            "type": i.type,
            "name": i.name,
            "description": i.description,
            "priority": i.priority,
            "status": i.status,
            "assignee_id": _id_of(i.assignee),
            "parent_id": _id_of(i.parent),
            "story_points": i.story_points,
            "estimated_hours": i.estimated_hours,
            "time_spent_hours": i.time_spent_hours,
            "created_by": _id_of(getattr(i, "created_by", None)),
            "updated_by": _id_of(getattr(i, "updated_by", None)),
            "created_at": getattr(i, "created_at", None),
            "updated_at": getattr(i, "updated_at", None),
            "location": i.location,
            # safe: support either a linked Feature (i.feature) or plain feature_id field
            "feature_id": _id_of(getattr(i, "feature", None) or getattr(i, "feature_id", None)),
        }


# ---------- SPRINTS ----------
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

    # ...existing code...
    async def running_sprint(self, project_id: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
        """
        GET /sprints/running
        If project_id provided, return a running sprint for that project (first match).
        Otherwise return any running sprint.
        """
        sprints_col = Sprint.get_motor_collection()

        def _proj_clause(pid: str):
            clauses = []
            try:
                pid_obj = ObjectId(str(pid))
                clauses.append({"project": pid_obj})
                clauses.append({"project.$id": pid_obj})
            except Exception:
                pass
            clauses.append({"project": str(pid)})
            clauses.append({"project_id": str(pid)})
            return {"$or": clauses}

        now = datetime.utcnow()
        base = {
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

        query = {"$and": [base, _proj_clause(project_id)]} if project_id else base

        doc = await sprints_col.find_one(query)
        if not doc:
            return {"sprint_running": False}

        return {
            "sprint_running": True,
            "sprint_id": str(doc.get("_id")),
            "sprint_name": doc.get("name"),
        }

    async def list_running_sprints(self, project_id: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
        """
        GET /sprints/running/all
        Return all running sprints; if project_id provided, return running sprints for that project.
        """
        sprints_col = Sprint.get_motor_collection()
        now = datetime.utcnow()

        def _proj_clause(pid: str):
            clauses = []
            try:
                pid_obj = ObjectId(str(pid))
                clauses.append({"project": pid_obj})
                clauses.append({"project.$id": pid_obj})
            except Exception:
                pass
            clauses.append({"project": str(pid)})
            clauses.append({"project_id": str(pid)})
            return {"$or": clauses}

        base = {
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

        query = {"$and": [base, _proj_clause(project_id)]} if project_id else base

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
        return out
# ...existing code...

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
        issue_id: str = Query(...),
        current_user: User = Depends(get_current_user)
    ):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        if not await PermissionService.can_view_project(_id_of(issue.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        comments = await Comment.find(Comment.issue.id == issue.id).to_list()
        out: List[Dict[str, Any]] = []
        for c in comments:
            out.append(self._doc_comment(c))
        return out

    async def create_comment(self, data: CommentCreate, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(str(data.issue_id))
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

        project = await Project.get(str(data.project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        epic = await Epic.get(str(data.epic_id)) if getattr(data, "epic_id", None) else None

        comment = Comment(
            project=project,
            epic=epic,
            issue=issue,
            author=current_user,
            comment=data.comment,
        )
        await comment.insert()
        return self._doc_comment(comment)

    async def delete_comment(self, comment_id: str, current_user: User = Depends(get_current_user)):
        c = await Comment.get(comment_id)
        if not c:
            raise HTTPException(status_code=404, detail="Comment not found")

        if (str(c.author.id) != str(current_user.id)) and (current_user.role != "admin"):
            raise HTTPException(status_code=403, detail="No access")

        await c.delete()
        return {"message": "Comment deleted"}

    def _doc_comment(self, c: Comment) -> Dict[str, Any]:
        return {
            "id": _id_of(c),
            "project_id": _id_of(c.project),
            "epic_id": _id_of(getattr(c, "epic", None)),
            "issue_id": _id_of(c.issue),
            "author_id": _id_of(c.author),
            "comment": c.comment,
            "created_at": getattr(c, "created_at", None),
        }


# ---------- LINKS ----------
class LinksRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/links", tags=["linked-workitems"])
        self.setup_routes()

    def setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route("/", self.list_links, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/", self.create_link, methods=["POST"], dependencies=deps)
        self.router.add_api_route("/{link_id}", self.delete_link, methods=["DELETE"], dependencies=deps)

    async def list_links(self, issue_id: str = Query(...), current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        if not await PermissionService.can_view_project(_id_of(issue.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        links = await LinkedWorkItem.find(
            (LinkedWorkItem.issue.id == issue.id) | (LinkedWorkItem.linked_issue.id == issue.id)
        ).to_list()

        out: List[Dict[str, Any]] = []
        for l in links:
            out.append(self._doc_link(l))
        return out

    async def create_link(self, data: LinkCreate, current_user: User = Depends(get_current_user)):
        main = await Issue.get(str(data.issue_id))
        other = await Issue.get(str(data.linked_issue_id))
        if not main or not other:
            raise HTTPException(status_code=404, detail="Issue(s) not found")

        if not await PermissionService.can_edit_workitem(_id_of(main), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        if _id_of(main) == _id_of(other):
            raise HTTPException(status_code=400, detail="Cannot link issue to itself")

        link = LinkedWorkItem(issue=main, linked_issue=other, reason=data.reason)
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
            "id": _id_of(l),
            "issue_id": _id_of(l.issue),
            "linked_issue_id": _id_of(l.linked_issue),
            "reason": l.reason,
            "created_at": getattr(l, "created_at", None),
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
issues_router = IssuesRouter().router
sprints_router = SprintsRouter().router
comments_router = CommentsRouter().router
links_router = LinksRouter().router
time_router = TimeRouter().router
#features_router = FeaturesRouter().router

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

@router.get("/projects/", response_model=List[Dict[str, Any]])
async def list_projects(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    """
    Admin -> return all projects (paged).
    Non-admin -> return only projects current_user can view (owner/member/public).
    """
    items: List[Dict[str, Any]] = []
    async for p in Project.find().skip(skip).limit(limit):
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
    async for f in Feature.find(Feature.project_id == PydanticObjectId(project_id)):
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
    await f.delete()
    return {"message": "Feature deleted"}

