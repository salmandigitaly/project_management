from __future__ import annotations
from typing import Optional, List, Dict, Literal
from datetime import datetime

from pydantic import BaseModel, Field, validator, root_validator

from beanie import (
    DeleteRules, Document, Link, BackLink, PydanticObjectId,
    before_event, after_event,
    Delete, Insert, Replace
)

from app.models.users import User  # existing User model
#from app.models.workitems import Project, Epic  # adjust if circular imports happen

from bson import ObjectId
from bson.dbref import DBRef
import logging
import re

logger = logging.getLogger(__name__)

# ---- Enums / constants ----
Platform = Literal["ios", "android", "web"]
IssueType = Literal["story", "task", "bug", "subtask"]
Priority = Literal["highest", "high", "medium", "low", "lowest"]
#Status = Literal["todo", "inprogress", "done"]
Status = Literal["todo", "inprogress", "done", "backlog", "impediment"]
Location = Literal["backlog", "sprint", "board", "archived"]
LinkReason = Literal["blocks", "is_blocked_by", "relates_to", "duplicates", "is_duplicated_by"]

FIB_POINTS = {0, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89}


# ================= Projects =================
class Project(Document):
    key: str = Field(unique=True, description="e.g. PROJ")
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    platform: Optional[Platform] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    project_lead: Link[User]
    members: Dict[str, str] = Field(default_factory=dict) 
    created_by: Link[User]
    updated_by: Optional[Link[User]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = None

    # These are VIRTUAL backlinks - they work when you fetch with populate
    # epics: List[BackLink["Epic"]] = Field(default_factory=list)
    # sprints: List[BackLink["Sprint"]] = Field(default_factory=list)
    # issues: List[BackLink["Issue"]] = Field(default_factory=list)


    # cascade handled by module-level handler below
    # (removed per-instance cascade to avoid duplicate/conflicting handlers)

    class Settings:
        name = "projects"
        use_state_management = True


# ================= Epics =================
class Epic(Document):
    key: Optional[str] = None
    name: str
    description: Optional[str] = None
    project: Link[Project]
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    created_by: Link[User]
    updated_by: Optional[Link[User]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = None

    # REMOVE THIS - BackLinks cause encoding errors
    # issues: List[BackLink["Issue"]] = Field(default_factory=list)

    @before_event(Delete)
    async def _cascade_delete_issues(self):
        # Delete child issues and comments one-by-one to avoid passing unsupported kwargs to motor
        try:
            issues = await Issue.find(Issue.epic.id == self.id).to_list()
        except Exception:
            issues = []
        for it in issues:
            try:
                await it.delete()
            except Exception:
                pass

        try:
            comments = await Comment.find(Comment.epic.id == self.id).to_list()
        except Exception:
            comments = []
        for c in comments:
            try:
                await c.delete()
            except Exception:
                pass

    @before_event(Insert)
    async def _generate_key(self):
        if not self.key:
            # Check if project is already fetched (it should be when creating)
            if self.project and hasattr(self.project, 'key'):
                # Use the already fetched project
                epic_count = await Epic.find(Epic.project.id == self.project.id).count()
                self.key = f"{self.project.key}-EPIC-{epic_count + 1}"
            else:
                # Fallback: fetch the project if it's a Link
                try:
                    project = await self.project.fetch()
                    epic_count = await Epic.find(Epic.project.id == project.id).count()
                    self.key = f"{project.key}-EPIC-{epic_count + 1}"
                except Exception:
                    # If all else fails, generate a basic key
                    self.key = f"EPIC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    class Settings:
        name = "epics"
        use_state_management = True

# ================= Sprints =================
class Sprint(Document):
    name: str
    project: Link[Project]
    goal: Optional[str] = None
    start_date: datetime
    end_date: datetime
    created_by: Optional[Link[User]] = None
    active: bool = False
    status: Optional[str] = "planned"
    issue_ids: List[PydanticObjectId] = Field(default_factory=list)
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = None
    # issues: List[BackLink["Issue"]] = Field(default_factory=list)

    class Settings:
        name = "sprints"
        use_state_management = True


# ================= Issues =================
class Issue(Document):
    key: Optional[str] = None
    project: Link[Project]
    epic: Optional[Link[Epic]] = None
    sprint: Optional[Link[Sprint]] = None

    type: IssueType
    name: str
    description: Optional[str] = None
    priority: Priority = "medium"
    #status: Status = "todo"
    status: str = Field(default="todo")

    assignee: Optional[Link[User]] = None

    parent: Optional[Link["Issue"]] = None  # if subtask
    story_points: Optional[int] = None      # only for stories (fib series)
    estimated_hours: Optional[float] = None
    time_spent_hours: float = 0.0

    created_by: Link[User]
    updated_by: Optional[Link[User]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    location: Location = "backlog"
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = None

    # backlinks
    # subtasks: List[BackLink["Issue"]] = Field(default_factory=list)
    # comments: List[BackLink["Comment"]] = Field(default_factory=list)

    # add this persisted field so API responses include the feature id
    feature_id: Optional[PydanticObjectId] = None

    @validator("story_points")
    def _validate_fib(cls, v):
        if v is None:
            return v
        if v not in FIB_POINTS:
            raise ValueError(f"story_points must be one of {sorted(FIB_POINTS)}")
        return v

    @root_validator(skip_on_failure=True)
    def _check_subtask_rules(cls, values):
        t = values.get("type")
        parent = values.get("parent")
        sp = values.get("story_points")

        # subtask must have parent; others must not
        if t == "subtask" and parent is None:
            raise ValueError("subtask requires parent")
        if t != "subtask" and parent is not None:
            raise ValueError("only subtasks can have parent")

        # story points only for stories
        # if t != "story" and sp is not None:
        #    raise ValueError("story_points allowed only for 'story'")
        return values

    @before_event(Delete)
    async def _cascade_children(self):
        # Remove subtasks, comments, linked items and time entries one-by-one
        try:
            subtasks = await Issue.find(Issue.parent.id == self.id).to_list()
        except Exception:
            subtasks = []
        for st in subtasks:
            try:
                await st.delete()
            except Exception:
                pass

        try:
            comments = await Comment.find(Comment.issue.id == self.id).to_list()
        except Exception:
            comments = []
        for c in comments:
            try:
                await c.delete()
            except Exception:
                pass

        try:
            linked = await LinkedWorkItem.find(
                (LinkedWorkItem.issue.id == self.id) | (LinkedWorkItem.linked_issue.id == self.id)
            ).to_list()
        except Exception:
            linked = []
        for li in linked:
            try:
                await li.delete()
            except Exception:
                pass

        try:
            times = await TimeEntry.find(TimeEntry.issue.id == self.id).to_list()
        except Exception:
            times = []
        for te in times:
            try:
                await te.delete()
            except Exception:
                pass

    @validator("status", pre=True, always=True)
    def _normalize_status(cls, v):
        if v is None:
            return "todo"
        s = str(v).strip().lower()
        # convert common variants to normalized token (e.g. "in progress" -> "in_progress")
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = s.strip("_")
        return s or "todo"

    class Settings:
        name = "issues"
        use_state_management = True


# ================= Comments =================
class Comment(Document):
    project: Link[Project]
    epic: Optional[Link[Epic]] = None
    sprint: Optional[Link[Sprint]] = None
    issue: Optional[Link[Issue]] = None
    author: Link[User]
    comment: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "comments"
        use_state_management = True


# ================= Links (issue ↔ issue) =================
class LinkedWorkItem(Document):
    issue: Link[Issue]          # main
    linked_issue: Link[Issue]   # other
    reason: LinkReason = "relates_to"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "linked_work_items"
        use_state_management = True


# ================= Time tracking =================
class TimeEntry(Document):
    project: Link[Project]
    issue: Link[Issue]
    user: Link[User]
    clock_in: datetime
    clock_out: Optional[datetime] = None
    seconds: int = 0  # compute at save/clock_out

    class Settings:
        name = "time_entries"
        use_state_management = True

    @after_event([Insert, Replace])
    async def _sync_issue_spent(self):
        # recompute seconds if clock_out present but seconds not set
        if self.clock_out and self.seconds == 0:
            self.seconds = int((self.clock_out - self.clock_in).total_seconds())
            await self.save()

        # aggregate to issue.time_spent_hours
        total = 0
        async for te in TimeEntry.find(TimeEntry.issue.id == self.issue.id):
            total += te.seconds
        hours = round(total / 3600.0, 2)

        issue = await Issue.get(self.issue.id)
        if issue:
            issue.time_spent_hours = hours
            await issue.save()


# ================= Boards & Backlog (minimal) =================
class BoardColumn(BaseModel):
    name: str
    status: str                  # e.g. "backlog", "todo", "in_progress", "in_review", "done"
    position: int
    color: Optional[str] = None

class Board(Document):
    name: str
    project_id: str
    sprint_id: Optional[str] = None
    columns: List[BoardColumn] = Field(default_factory=list)
    visible_to_roles: List[str] = Field(default_factory=list)   # [] => visible to all

    class Settings:
        name = "boards"
        use_state_management = True

class Backlog(Document):
    project_id: str
    items: List[PydanticObjectId] = Field(default_factory=list)              # store work-item ObjectId strings
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "backlogs"
        use_state_management = True

# ================= Features =================
class Feature(Document):
    name: str
    description: Optional[str] = None
    project_id: PydanticObjectId
    epic_id: Optional[PydanticObjectId] = None
    status: str = "todo"
    priority: str = "medium"
    created_by: Optional[PydanticObjectId] = None
    updated_by: Optional[PydanticObjectId] = None
    created_at: datetime = datetime.utcnow()
    updated_at: Optional[datetime] = None
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = None

    class Settings:
        name = "features"

# ---------- robust cascade delete for Project ----------
@before_event(Delete)
async def _project_cascade_delete(sender, document, **kwargs):
    """
    When a Project is deleted, find child documents in Epics/Features/Issues/Sprints/Boards/Backlogs/Comments/TimeEntries/LinkedWorkItems
    using multiple query shapes (ObjectId, DBRef, string) and delete them one-by-one via .delete() so Beanie per-document hooks run.
    """
    try:
        # Only run when a Project document is being deleted
        try:
            is_project = (sender.__name__ == "Project") or (getattr(document, "__class__", None).__name__ == "Project")
        except Exception:
            is_project = False
        if not is_project:
            return

        pid = getattr(document, "id", None) or getattr(document, "_id", None)
        if not pid:
            return
        pid_str = str(pid)

        # build candidate query shapes
        q_candidates = []
        try:
            oid = ObjectId(pid_str)
            q_candidates += [
                {"project": oid},
                {"project.$id": oid},
                {"project.id": oid},
                {"project": DBRef("projects", oid)},
            ]
        except Exception:
            oid = None

        # string / nested string shapes
        q_candidates += [
            {"project": pid_str},
            {"project_id": pid_str},
            {"project.id": pid_str},
            {"project.$id": pid_str},
        ]

        # models to consider for deletion (order: dependent -> children)
        models = [
            globals().get("LinkedWorkItem"),
            globals().get("Comment"),
            globals().get("TimeEntry"),
            globals().get("Issue"),
            globals().get("Feature"),
            globals().get("Epic"),
            globals().get("Sprint"),
            globals().get("Board"),
            globals().get("Backlog"),
        ]

        for m in models:
            if not m:
                continue
            try:
                # collect matching documents using $or across candidate queries
                docs = []
                try:
                    if len(q_candidates) > 1:
                        docs = await m.find({"$or": q_candidates}).to_list()
                    else:
                        docs = await m.find(q_candidates[0]).to_list()
                except Exception:
                    # fallback: try each query individually
                    tmp = []
                    for q in q_candidates:
                        try:
                            tmp.extend(await m.find(q).to_list())
                        except Exception:
                            pass
                    docs = tmp

                # also ensure projects saved under project_id are included
                try:
                    more = await m.find({"project_id": pid_str}).to_list()
                    if more:
                        docs.extend(more)
                except Exception:
                    pass

                # deduplicate and delete one-by-one to trigger Beanie delete hooks
                seen = set()
                for d in docs:
                    doc_id = getattr(d, "id", None) or getattr(d, "_id", None)
                    if not doc_id:
                        continue
                    doc_id_s = str(doc_id)
                    if doc_id_s in seen:
                        continue
                    seen.add(doc_id_s)
                    try:
                        await d.delete()
                    except Exception:
                        # ignore per-document delete errors and continue
                        pass
            except Exception:
                # ignore model-level failures and continue with others
                pass

    except Exception:
        # swallow to avoid failing the parent Project delete operation
        pass
