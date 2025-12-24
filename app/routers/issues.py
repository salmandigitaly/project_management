from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
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
        # assign/unassign an issue (PATCH) - body: {"assignee_id": "<user_id>" } or {"assignee_id": null} to unassign
        self.router.add_api_route("/{issue_id}/assign", self.assign_issue, methods=["PATCH"], dependencies=deps)

    async def list_issues(
        self,
        project_id: str = Query(...),
        sprint_id: Optional[str] = Query(None),
        epic_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
    ):
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        issues = await Issue.find(Issue.project.id == PydanticObjectId(project_id), Issue.is_deleted != True).to_list()

        # exclude completed issues from this listing
        issues = [i for i in issues if getattr(i, "status", None) != "done"]

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
        print(f"DEBUG: create_issue called with data={data}")
        try:
            if not await PermissionService.can_view_project(str(data.project_id), str(current_user.id)):
                raise HTTPException(status_code=403, detail="No access to project")

            project = await Project.get(str(data.project_id))
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            # Generate key
            issue_count = await Issue.find(Issue.project.id == project.id).count()
            key = f"{project.key}-{issue_count + 1}"
            print(f"DEBUG: Generated key {key}")

            epic = await Epic.get(str(data.epic_id)) if getattr(data, "epic_id", None) else None
            sprint = await Sprint.get(str(data.sprint_id)) if getattr(data, "sprint_id", None) else None
            assignee = await User.get(str(data.assignee_id)) if getattr(data, "assignee_id", None) else None
            parent = await Issue.get(str(data.parent_id)) if getattr(data, "parent_id", None) else None
            feature = await Feature.get(str(data.feature_id)) if getattr(data, "feature_id", None) else None

            print("DEBUG: Creating Issue object")
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
            print(f"DEBUG: Issue inserted with id {issue.id}")

            # ADD ISSUE TO BACKLOG
            print("DEBUG: Updating backlog")
            backlog = await Backlog.find_one({"project_id": str(project.id)})
            if backlog:
                # compare as strings to avoid ObjectId / string mismatches
                if not any(str(i) == str(issue.id) for i in backlog.items):
                    # store as ObjectId-like (PydanticObjectId) to match model type
                    backlog.items.append(PydanticObjectId(issue.id))
                    await backlog.save()
            
            print("DEBUG: Returning response")
            return await self._doc_issue(issue)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERROR in create_issue: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create issue: {str(e)}")

    async def get_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue or issue.is_deleted:
            raise HTTPException(status_code=404, detail="Issue not found")
        if not await PermissionService.can_view_project(_id_of(issue.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")
        return await self._doc_issue(issue)

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
        return await self._doc_issue(issue)

    async def delete_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        # permission check removed: allow authenticated users to delete issues

        issue.is_deleted = True
        issue.deleted_at = datetime.utcnow()
        await issue.save()

        # optional: soft delete children (subtasks)
        try:
            await Issue.find(Issue.parent.id == issue.id).update({"$set": {"is_deleted": True, "deleted_at": datetime.utcnow()}})
        except Exception:
            pass

        return {"message": "Issue moved to Recycle Bin"}

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
        return await self._doc_issue(issue)

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
        return await self._doc_issue(sub)
    

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
                moved_issues.append(await self._doc_issue(issue))

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

    async def assign_issue(
        self,
        issue_id: str,
        assignee_id: Optional[str] = Body(None, embed=True),
        current_user: User = Depends(get_current_user)
    ):
        """
        PATCH /issues/{issue_id}/assign
        Body: { "assignee_id": "<user_id>" }  or { "assignee_id": null } to unassign
        """
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

        # permission: require edit rights on the workitem
        if not await PermissionService.can_edit_workitem(_id_of(issue), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to assign this issue")

        if assignee_id is None:
            # unassign
            issue.assignee = None
        else:
            user = await User.get(str(assignee_id))
            if not user:
                raise HTTPException(status_code=404, detail="Assignee user not found")
            issue.assignee = user

        issue.updated_by = current_user
        issue.updated_at = datetime.utcnow()
        await issue.save()

        return await self._doc_issue(issue)

    async def _doc_issue(self, i: Issue) -> Dict[str, Any]:
        comments = await Comment.find(Comment.issue.id == i.id).to_list()
        comments_list = []
        for c in comments:
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
            comments_list.append({
                "id": _id_of(c),
                "project_id": _id_of(c.project),
                "epic_id": _id_of(getattr(c, "epic", None)),
                "sprint_id": _id_of(getattr(c, "sprint", None)),
                "issue_id": _id_of(c.issue),
                "author_id": _id_of(c.author),
                "author_name": author_name,
                "comment": c.comment,
                "created_at": getattr(c, "created_at", None),
            })
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
            "comments": comments_list,
        }

issues_router = IssuesRouter().router