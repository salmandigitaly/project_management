# # app/routers/workitems.py
# from __future__ import annotations
# from datetime import datetime
# from typing import List, Optional, Literal, Dict, Any

# from fastapi import APIRouter, Depends, HTTPException, Query
# from fastapi.security import HTTPBearer
# from beanie import PydanticObjectId

# from app.routers.auth import get_current_user
# from app.models.users import User
# from app.models.workitems import (
#     Project, Epic, Issue, Sprint, Comment, TimeEntry, LinkedWorkItem
# )
# from app.schemas.project_management import (
#     EpicCreate, EpicUpdate, EpicOut,
#     IssueCreate, IssueUpdate, IssueOut,
#     SprintCreate, SprintUpdate, SprintOut,
#     CommentCreate, CommentOut,
#     LinkCreate, LinkOut,
#     TimeClockIn, TimeClockOut, TimeAddManual, TimeEntryOut,
# )

# from app.services.permission import PermissionService

# security = HTTPBearer()


# # ---------- EPICS ----------
# class EpicsRouter:
#     def __init__(self):
#         self.router = APIRouter(prefix="/epics", tags=["epics"])
#         self.setup_routes()

#     def setup_routes(self):
#         deps = [Depends(security), Depends(get_current_user)]
#         self.router.add_api_route("/", self.list_epics, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/", self.create_epic, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/{epic_id}", self.get_epic, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/{epic_id}", self.update_epic, methods=["PUT"], dependencies=deps)
#         self.router.add_api_route("/{epic_id}", self.delete_epic, methods=["DELETE"], dependencies=deps)

#     async def list_epics(
#         self,
#         project_id: str = Query(...),
#         current_user: User = Depends(get_current_user)
#     ):
#         if not await PermissionService.can_view_project(project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access to project")

#         epics = await Epic.find(Epic.project.id == PydanticObjectId(project_id)).to_list()
#         return [self._doc(e) for e in epics]

#     async def create_epic(self, data: EpicCreate, current_user: User = Depends(get_current_user)):
#         if not await PermissionService.can_edit_project(data.project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access to create")

#         project = await Project.get(data.project_id)
#         if not project:
#             raise HTTPException(status_code=404, detail="Project not found")

#         epic = Epic(
#             name=data.name,
#             description=data.description,
#             project=project,
#             start_date=data.start_date,
#             end_date=data.end_date,
#             created_by=current_user,
#             updated_by=current_user,
#         )
#         await epic.insert()
#         return self._doc(epic)

#     async def get_epic(self, epic_id: str, current_user: User = Depends(get_current_user)):
#         epic = await Epic.get(epic_id)
#         if not epic:
#             raise HTTPException(status_code=404, detail="Epic not found")
#         if not await PermissionService.can_view_project(str(epic.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")
#         return self._doc(epic)

#     async def update_epic(self, epic_id: str, data: EpicUpdate, current_user: User = Depends(get_current_user)):
#         epic = await Epic.get(epic_id)
#         if not epic:
#             raise HTTPException(status_code=404, detail="Epic not found")
#         if not await PermissionService.can_edit_project(str(epic.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         await epic.set({k: v for k, v in data.dict(exclude_unset=True).items()})
#         epic.updated_by = current_user
#         epic.updated_at = datetime.utcnow()
#         await epic.save()
#         return self._doc(epic)

#     async def delete_epic(self, epic_id: str, current_user: User = Depends(get_current_user)):
#         epic = await Epic.get(epic_id)
#         if not epic:
#             raise HTTPException(status_code=404, detail="Epic not found")
#         if not await PermissionService.can_edit_project(str(epic.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         await epic.delete()
#         return {"message": "Epic deleted"}

#     def _doc(self, e: Epic) -> Dict[str, Any]:
#         d = e.dict()
#         d["id"] = str(e.id)
#         d["project_id"] = str(e.project.id) if e.project else None
#         return d


# # ---------- ISSUES ----------
# class IssuesRouter:
#     def __init__(self):
#         self.router = APIRouter(prefix="/issues", tags=["issues"])
#         self.setup_routes()

#     def setup_routes(self):
#         deps = [Depends(security), Depends(get_current_user)]
#         self.router.add_api_route("/", self.list_issues, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/", self.create_issue, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/{issue_id}", self.get_issue, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/{issue_id}", self.update_issue, methods=["PUT"], dependencies=deps)
#         self.router.add_api_route("/{issue_id}", self.delete_issue, methods=["DELETE"], dependencies=deps)
#         self.router.add_api_route("/{issue_id}/move", self.move_issue, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/{issue_id}/subtasks", self.add_subtask, methods=["POST"], dependencies=deps)

#     async def list_issues(
#         self,
#         project_id: str = Query(...),
#         sprint_id: Optional[str] = Query(None),
#         epic_id: Optional[str] = Query(None),
#         current_user: User = Depends(get_current_user),
#     ):
#         if not await PermissionService.can_view_project(project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access to project")

#         base_q = Issue.project.id == PydanticObjectId(project_id)
#         issues = await Issue.find(base_q).to_list()

#         if sprint_id:
#             issues = [i for i in issues if (i.sprint and str(i.sprint.id) == sprint_id)]
#         if epic_id:
#             issues = [i for i in issues if (i.epic and str(i.epic.id) == epic_id)]

#         return [self._doc(i) for i in issues]

#     async def create_issue(self, data: IssueCreate, current_user: User = Depends(get_current_user)):
#         if not await PermissionService.can_view_project(data.project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access to project")

#         project = await Project.get(data.project_id)
#         if not project:
#             raise HTTPException(status_code=404, detail="Project not found")

#         epic = await Epic.get(data.epic_id) if getattr(data, "epic_id", None) else None
#         sprint = await Sprint.get(data.sprint_id) if getattr(data, "sprint_id", None) else None
#         assignee = await User.get(data.assignee_id) if getattr(data, "assignee_id", None) else None
#         parent = await Issue.get(data.parent_id) if getattr(data, "parent_id", None) else None

#         issue = Issue(
#             project=project,
#             epic=epic,
#             sprint=sprint,
#             type=data.type,
#             name=data.name,
#             description=data.description,
#             priority=data.priority,
#             assignee=assignee,
#             parent=parent,
#             story_points=data.story_points,
#             estimated_hours=data.estimated_hours,
#             created_by=current_user,
#             updated_by=current_user,
#             location=data.location,
#         )
#         await issue.insert()
#         return self._doc(issue)

#     async def get_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
#         issue = await Issue.get(issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_view_project(str(issue.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")
#         return self._doc(issue)

#     async def update_issue(self, issue_id: str, data: IssueUpdate, current_user: User = Depends(get_current_user)):
#         issue = await Issue.get(issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         payload = data.dict(exclude_unset=True)

#         # handle relation id fields explicitly
#         if "epic_id" in payload:
#             epic_id = payload.pop("epic_id")
#             issue.epic = await Epic.get(epic_id) if epic_id else None
#         if "sprint_id" in payload:
#             sprint_id = payload.pop("sprint_id")
#             issue.sprint = await Sprint.get(sprint_id) if sprint_id else None
#         if "assignee_id" in payload:
#             assignee_id = payload.pop("assignee_id")
#             issue.assignee = await User.get(assignee_id) if assignee_id else None
#         if "parent_id" in payload:
#             parent_id = payload.pop("parent_id")
#             issue.parent = await Issue.get(parent_id) if parent_id else None

#         await issue.set(payload)
#         issue.updated_by = current_user
#         issue.updated_at = datetime.utcnow()
#         await issue.save()
#         return self._doc(issue)

#     async def delete_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
#         issue = await Issue.get(issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         await issue.delete()
#         return {"message": "Issue deleted"}

#     async def move_issue(
#         self,
#         issue_id: str,
#         to: Literal["backlog", "sprint", "board"] = Query(...),
#         sprint_id: Optional[str] = Query(None),
#         current_user: User = Depends(get_current_user),
#     ):
#         issue = await Issue.get(issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         if to == "sprint":
#             if not sprint_id:
#                 raise HTTPException(status_code=400, detail="sprint_id required")
#             sprint = await Sprint.get(sprint_id)
#             if not sprint:
#                 raise HTTPException(status_code=404, detail="Sprint not found")
#             issue.sprint = sprint
#         else:  # backlog or board
#             issue.sprint = None

#         issue.location = to
#         await issue.save()
#         return self._doc(issue)

#     async def add_subtask(self, issue_id: str, data: IssueCreate, current_user: User = Depends(get_current_user)):
#         parent = await Issue.get(issue_id)
#         if not parent:
#             raise HTTPException(status_code=404, detail="Parent issue not found")
#         if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         project = await Project.get(data.project_id)
#         if not project:
#             raise HTTPException(status_code=404, detail="Project not found")

#         sub = Issue(
#             project=project,
#             epic=parent.epic,
#             sprint=parent.sprint,
#             type="subtask",
#             name=data.name,
#             description=data.description,
#             priority=data.priority,
#             assignee=await User.get(data.assignee_id) if getattr(data, "assignee_id", None) else None,
#             parent=parent,
#             created_by=current_user,
#             updated_by=current_user,
#             location=parent.location,
#         )
#         await sub.insert()
#         return self._doc(sub)

#     def _doc(self, i: Issue) -> Dict[str, Any]:
#         d = i.dict()
#         d["id"] = str(i.id)
#         d["project_id"] = str(i.project.id) if i.project else None
#         d["epic_id"] = str(i.epic.id) if i.epic else None
#         d["sprint_id"] = str(i.sprint.id) if i.sprint else None
#         d["assignee_id"] = str(i.assignee.id) if i.assignee else None
#         d["parent_id"] = str(i.parent.id) if i.parent else None
#         return d


# # ---------- SPRINTS ----------
# class SprintsRouter:
#     def __init__(self):
#         self.router = APIRouter(prefix="/sprints", tags=["sprints"])
#         self.setup_routes()

#     def setup_routes(self):
#         deps = [Depends(security), Depends(get_current_user)]
#         self.router.add_api_route("/", self.list_sprints, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/", self.create_sprint, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/{sprint_id}", self.get_sprint, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/{sprint_id}", self.update_sprint, methods=["PUT"], dependencies=deps)
#         self.router.add_api_route("/{sprint_id}", self.delete_sprint, methods=["DELETE"], dependencies=deps)

#     async def list_sprints(self, project_id: str = Query(...), current_user: User = Depends(get_current_user)):
#         if not await PermissionService.can_view_project(project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access to project")
#         sprints = await Sprint.find(Sprint.project.id == PydanticObjectId(project_id)).to_list()
#         return [self._doc(s) for s in sprints]

#     async def create_sprint(self, data: SprintCreate, current_user: User = Depends(get_current_user)):
#         if not await PermissionService.can_manage_sprint(data.project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access to create sprint")

#         project = await Project.get(data.project_id)
#         if not project:
#             raise HTTPException(status_code=404, detail="Project not found")

#         sprint = Sprint(
#             name=data.name,
#             project=project,
#             goal=data.goal,
#             start_date=data.start_date,
#             end_date=data.end_date,
#             created_by=current_user,
#         )
#         await sprint.insert()
#         return self._doc(sprint)

#     async def get_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
#         sprint = await Sprint.get(sprint_id)
#         if not sprint:
#             raise HTTPException(status_code=404, detail="Sprint not found")
#         if not await PermissionService.can_view_project(str(sprint.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")
#         return self._doc(sprint)

#     async def update_sprint(self, sprint_id: str, data: SprintUpdate, current_user: User = Depends(get_current_user)):
#         sprint = await Sprint.get(sprint_id)
#         if not sprint:
#             raise HTTPException(status_code=404, detail="Sprint not found")
#         if not await PermissionService.can_manage_sprint(str(sprint.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         await sprint.set({k: v for k, v in data.dict(exclude_unset=True).items()})
#         return self._doc(sprint)

#     async def delete_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
#         sprint = await Sprint.get(sprint_id)
#         if not sprint:
#             raise HTTPException(status_code=404, detail="Sprint not found")
#         if not await PermissionService.can_manage_sprint(str(sprint.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         await sprint.delete()
#         return {"message": "Sprint deleted"}

#     def _doc(self, s: Sprint) -> Dict[str, Any]:
#         d = s.dict()
#         d["id"] = str(s.id)
#         d["project_id"] = str(s.project.id) if s.project else None
#         return d


# # ---------- COMMENTS ----------
# class CommentsRouter:
#     def __init__(self):
#         self.router = APIRouter(prefix="/comments", tags=["comments"])
#         self.setup_routes()

#     def setup_routes(self):
#         deps = [Depends(security), Depends(get_current_user)]
#         self.router.add_api_route("/", self.list_comments, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/", self.create_comment, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/{comment_id}", self.delete_comment, methods=["DELETE"], dependencies=deps)

#     async def list_comments(
#         self,
#         issue_id: str = Query(...),
#         current_user: User = Depends(get_current_user)
#     ):
#         issue = await Issue.get(issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_view_project(str(issue.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         comments = await Comment.find(Comment.issue.id == issue.id).to_list()
#         out: List[Dict[str, Any]] = []
#         for c in comments:
#             d = c.dict()
#             d["id"] = str(c.id)
#             d["issue_id"] = str(c.issue.id)
#             d["project_id"] = str(c.project.id)
#             d["author_id"] = str(c.author.id)
#             out.append(d)
#         return out

#     async def create_comment(self, data: CommentCreate, current_user: User = Depends(get_current_user)):
#         issue = await Issue.get(data.issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_comment(data.issue_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         project = await Project.get(data.project_id)
#         if not project:
#             raise HTTPException(status_code=404, detail="Project not found")

#         epic = await Epic.get(data.epic_id) if getattr(data, "epic_id", None) else None

#         comment = Comment(
#             project=project,
#             epic=epic,
#             issue=issue,
#             author=current_user,
#             comment=data.comment,
#         )
#         await comment.insert()
#         d = comment.dict()
#         d["id"] = str(comment.id)
#         return d

#     async def delete_comment(self, comment_id: str, current_user: User = Depends(get_current_user)):
#         c = await Comment.get(comment_id)
#         if not c:
#             raise HTTPException(status_code=404, detail="Comment not found")

#         # author or admin may delete
#         if (str(c.author.id) != str(current_user.id)) and (current_user.role != "admin"):
#             raise HTTPException(status_code=403, detail="No access")

#         await c.delete()
#         return {"message": "Comment deleted"}


# # ---------- LINKS ----------
# class LinksRouter:
#     def __init__(self):
#         self.router = APIRouter(prefix="/links", tags=["linked-workitems"])
#         self.setup_routes()

#     def setup_routes(self):
#         deps = [Depends(security), Depends(get_current_user)]
#         self.router.add_api_route("/", self.list_links, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/", self.create_link, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/{link_id}", self.delete_link, methods=["DELETE"], dependencies=deps)

#     async def list_links(self, issue_id: str = Query(...), current_user: User = Depends(get_current_user)):
#         issue = await Issue.get(issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")
#         if not await PermissionService.can_view_project(str(issue.project.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         links = await LinkedWorkItem.find(
#             (LinkedWorkItem.issue.id == issue.id) | (LinkedWorkItem.linked_issue.id == issue.id)
#         ).to_list()

#         out: List[Dict[str, Any]] = []
#         for l in links:
#             d = l.dict()
#             d["id"] = str(l.id)
#             d["issue_id"] = str(l.issue.id)
#             d["linked_issue_id"] = str(l.linked_issue.id)
#             out.append(d)
#         return out

#     async def create_link(self, data: LinkCreate, current_user: User = Depends(get_current_user)):
#         main = await Issue.get(data.issue_id)
#         other = await Issue.get(data.linked_issue_id)
#         if not main or not other:
#             raise HTTPException(status_code=404, detail="Issue(s) not found")

#         if not await PermissionService.can_edit_workitem(str(main.id), str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         if str(main.id) == str(other.id):
#             raise HTTPException(status_code=400, detail="Cannot link issue to itself")

#         link = LinkedWorkItem(issue=main, linked_issue=other, reason=data.reason)
#         await link.insert()
#         d = link.dict()
#         d["id"] = str(link.id)
#         return d

#     async def delete_link(self, link_id: str, current_user: User = Depends(get_current_user)):
#         link = await LinkedWorkItem.get(link_id)
#         if not link:
#             raise HTTPException(status_code=404, detail="Link not found")

#         if not (
#             await PermissionService.can_edit_workitem(str(link.issue.id), str(current_user.id))
#             or await PermissionService.can_edit_workitem(str(link.linked_issue.id), str(current_user.id))
#         ):
#             raise HTTPException(status_code=403, detail="No access")

#         await link.delete()
#         return {"message": "Link deleted"}


# # ---------- TIME TRACKING ----------
# class TimeRouter:
#     def __init__(self):
#         self.router = APIRouter(prefix="/time", tags=["time-tracking"])
#         self.setup_routes()

#     def setup_routes(self):
#         deps = [Depends(security), Depends(get_current_user)]
#         self.router.add_api_route("/entries", self.list_entries, methods=["GET"], dependencies=deps)
#         self.router.add_api_route("/clock-in", self.clock_in, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/clock-out", self.clock_out, methods=["POST"], dependencies=deps)
#         self.router.add_api_route("/add", self.add_manual, methods=["POST"], dependencies=deps)

#     async def list_entries(
#         self,
#         project_id: str = Query(...),
#         issue_id: Optional[str] = Query(None),
#         current_user: User = Depends(get_current_user),
#     ):
#         if not await PermissionService.can_view_project(project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         q = TimeEntry.project.id == PydanticObjectId(project_id)
#         entries = await TimeEntry.find(q).to_list()

#         if issue_id:
#             entries = [t for t in entries if str(t.issue.id) == issue_id]

#         out: List[Dict[str, Any]] = []
#         for t in entries:
#             out.append({
#                 "id": str(t.id),
#                 "project_id": str(t.project.id),
#                 "issue_id": str(t.issue.id),
#                 "user_id": str(t.user.id),
#                 "clock_in": t.clock_in,
#                 "clock_out": t.clock_out,
#                 "seconds": t.seconds,
#             })
#         return out

#     async def clock_in(self, data: TimeClockIn, current_user: User = Depends(get_current_user)):
#         if not await PermissionService.can_view_project(data.project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         issue = await Issue.get(data.issue_id)
#         if not issue:
#             raise HTTPException(status_code=404, detail="Issue not found")

#         project = await Project.get(data.project_id)
#         if not project:
#             raise HTTPException(status_code=404, detail="Project not found")

#         entry = TimeEntry(
#             project=project,
#             issue=issue,
#             user=current_user,
#             clock_in=datetime.utcnow(),
#             clock_out=None,
#             seconds=0,
#         )
#         await entry.insert()
#         return {"id": str(entry.id)}

#     async def clock_out(self, data: TimeClockOut, current_user: User = Depends(get_current_user)):
#         entry = await TimeEntry.get(data.time_entry_id)
#         if not entry:
#             raise HTTPException(status_code=404, detail="Time entry not found")

#         if str(entry.user.id) != str(current_user.id) and current_user.role != "admin":
#             raise HTTPException(status_code=403, detail="No access")

#         if entry.clock_out:
#             raise HTTPException(status_code=400, detail="Already clocked out")

#         entry.clock_out = datetime.utcnow()
#         entry.seconds = int((entry.clock_out - entry.clock_in).total_seconds())
#         await entry.save()
#         return {"id": str(entry.id), "seconds": entry.seconds}

#     async def add_manual(self, data: TimeAddManual, current_user: User = Depends(get_current_user)):
#         if not await PermissionService.can_view_project(data.project_id, str(current_user.id)):
#             raise HTTPException(status_code=403, detail="No access")

#         project = await Project.get(data.project_id)
#         issue = await Issue.get(data.issue_id)
#         if not project or not issue:
#             raise HTTPException(status_code=404, detail="Project/Issue not found")

#         now = datetime.utcnow()
#         entry = TimeEntry(
#             project=project,
#             issue=issue,
#             user=current_user,
#             clock_in=now,
#             clock_out=now,
#             seconds=int(data.seconds),
#         )
#         await entry.insert()
#         return {"id": str(entry.id), "seconds": entry.seconds}


# # Expose routers
# epics_router = EpicsRouter().router
# issues_router = IssuesRouter().router
# sprints_router = SprintsRouter().router
# comments_router = CommentsRouter().router
# links_router = LinksRouter().router
# time_router = TimeRouter().router
















































# app/routers/workitems.py
from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from beanie import PydanticObjectId

from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import (
    Backlog, Project, Epic, Issue, Sprint, Comment, TimeEntry, LinkedWorkItem
)
from app.schemas.project_management import (
    EpicCreate, EpicUpdate,
    IssueCreate, IssueUpdate,
    SprintCreate, SprintUpdate,
    CommentCreate,
    LinkCreate,
    TimeClockIn, TimeClockOut, TimeAddManual,
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
            "start_date": e.start_date,
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
        )
        await issue.insert()

        # ADD ISSUE TO BACKLOG
        backlog = await Backlog.find_one({"project_id": str(project.id)})
        if backlog:
            if str(issue.id) not in backlog.items:
                backlog.items.append(str(issue.id))
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
        if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

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

        await issue.set(payload)
        issue.updated_by = current_user
        issue.updated_at = datetime.utcnow()
        await issue.save()
        return self._doc_issue(issue)

    async def delete_issue(self, issue_id: str, current_user: User = Depends(get_current_user)):
        issue = await Issue.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

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
        if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        # Remove from old sprint's issue_ids list
        # Remove from old sprint's issue_ids
        if issue.sprint:
            old_sprint = await Sprint.get(_id_of(issue.sprint))
            if old_sprint and issue.id in old_sprint.issue_ids:
                old_sprint.issue_ids.remove(issue.id)
                await old_sprint.save()

        # Add to new sprint's issue_ids  
        if to == "sprint":
            sprint = await Sprint.get(sprint_id)
            if issue.id not in sprint.issue_ids:
                sprint.issue_ids.append(issue.id)
                await sprint.save()
            
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
        if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
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

                if not await PermissionService.can_edit_workitem(issue_id, str(current_user.id)):
                    errors.append(f"No access to issue {issue_id}")
                    continue

                # Remove from old sprint's issue_ids
                if issue.sprint:
                    old_sprint = await Sprint.get(_id_of(issue.sprint))
                    if old_sprint and issue.id in old_sprint.issue_ids:
                        old_sprint.issue_ids.remove(issue.id)
                        await old_sprint.save()

                # Add to new sprint's issue_ids  
                if to == "sprint":
                    if not sprint_id:
                        errors.append(f"sprint_id required for issue {issue_id}")
                        continue
                    sprint = await Sprint.get(sprint_id)
                    if not sprint:
                        errors.append(f"Sprint not found for issue {issue_id}")
                        continue
                    
                    if issue.id not in sprint.issue_ids:
                        sprint.issue_ids.append(issue.id)
                        await sprint.save()
                    
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
        self.router.add_api_route("/{sprint_id}", self.get_sprint, methods=["GET"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}", self.update_sprint, methods=["PUT"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}", self.delete_sprint, methods=["DELETE"], dependencies=deps)
        self.router.add_api_route("/{sprint_id}/start", self.start_sprint, methods=["POST"], dependencies=deps)
    async def list_sprints(self, project_id: str = Query(...), current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")
        sprints = await Sprint.find(Sprint.project.id == PydanticObjectId(project_id)).to_list()
        return [self._doc_sprint(s) for s in sprints]

    async def create_sprint(self, data: SprintCreate, current_user: User = Depends(get_current_user)):
        if not await PermissionService.can_manage_sprint(str(data.project_id), str(current_user.id)):
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
        if not await PermissionService.can_view_project(_id_of(sprint.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")
        return self._doc_sprint(sprint)

    async def update_sprint(self, sprint_id: str, data: SprintUpdate, current_user: User = Depends(get_current_user)):
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        if not await PermissionService.can_manage_sprint(_id_of(sprint.project), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        await sprint.set({k: v for k, v in data.dict(exclude_unset=True).items()})
        return self._doc_sprint(sprint)

    async def delete_sprint(self, sprint_id: str, current_user: User = Depends(get_current_user)):
        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=404, detail="Sprint not found")
        if not await PermissionService.can_manage_sprint(_id_of(sprint.project), str(current_user.id)):
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
        
        if not await PermissionService.can_manage_sprint(_id_of(sprint.project), str(current_user.id)):
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
        if not await PermissionService.can_comment(str(data.issue_id), str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

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

        if not (
            await PermissionService.can_edit_workitem(_id_of(link.issue), str(current_user.id))
            or await PermissionService.can_edit_workitem(_id_of(link.linked_issue), str(current_user.id))
        ):
            raise HTTPException(status_code=403, detail="No access")

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

        issue = await Issue.get(str(data.issue_id))
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

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
