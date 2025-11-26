from __future__ import annotations
from typing import Optional, List, Dict, Literal
from datetime import datetime
from pydantic import BaseModel, Field, validator
from beanie import PydanticObjectId
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

Platform = Literal["ios", "android", "web"]
IssueType = Literal["story", "task", "bug", "subtask"]
Priority = Literal["highest", "high", "medium", "low", "lowest"]
Status = Literal["todo", "inprogress", "done"]
LinkReason = Literal["blocks", "is_blocked_by", "relates_to", "duplicates", "is_duplicated_by"]

FIB_POINTS = {0, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89}


# -------- Common --------
class IDModel(BaseModel):
    id: PydanticObjectId = Field(..., alias="_id")

    class Config:
        allow_population_by_field_name = True
        orm_mode = True


class TimeStampMixin(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# -------- Project --------
class ProjectCreate(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    platform: Optional[Platform] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # request can still send ObjectId-like string; PydanticObjectId parses it
    project_lead: Optional[PydanticObjectId] = None
    # ✅ keep only member_roles
    member_roles: Dict[str, str] = Field(default_factory=dict)
    # created_by comes from auth user; don't accept in request
    created_by: Optional[PydanticObjectId] = None  # (ignored by router)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    platform: Optional[Platform] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    project_lead: Optional[PydanticObjectId] = None
    # ✅ only member_roles; members removed
    member_roles: Optional[Dict[str, str]] = None
    updated_by: Optional[PydanticObjectId] = None
    updated_at: Optional[datetime] = None


class UserSummary(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None


class MemberSummary(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None

    # ✅ keep only member_roles in response
    #member_roles: Dict[str, str] = Field(default_factory=dict)

    # timestamps
    # epics_count: int = 0
    # sprints_count: int = 0
    # issues_count: int = 0
    # created_at: Optional[datetime] = None
    # updated_at: Optional[datetime] = None


class ProjectOut(BaseModel):
    id: str
    key: str
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    platform: Optional[Platform] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # ✅ now they accept nested objects
    project_lead: Optional[UserSummary] = None
    created_by: Optional[UserSummary] = None
    updated_by: Optional[UserSummary] = None

    # ✅ members list instead of member_roles
    members: Optional[List[MemberSummary]] = None

    epics_count: int = 0
    sprints_count: int = 0
    issues_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# class ProjectOut(BaseModel):
#     # ✅ expose plain strings in responses to avoid {} serialization
#     id: str
#     key: str
#     name: str
#     description: Optional[str] = None
#     avatar_url: Optional[str] = None
#     platform: Optional[Platform] = None
#     start_date: Optional[datetime] = None
#     end_date: Optional[datetime] = None

    # ✅ only string ids in response
    # project_lead: Optional[str] = None
    # created_by: Optional[str] = None
    # updated_by: Optional[str] = None
class EpicCreate(BaseModel):
    name: str
    project_id: PydanticObjectId
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_by: Optional[PydanticObjectId] = None


class EpicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    updated_by: Optional[PydanticObjectId] = None
    updated_at: Optional[datetime] = None


class EpicOut(IDModel, TimeStampMixin):
    name: str
    project_id: PydanticObjectId
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_by: PydanticObjectId
    updated_by: Optional[PydanticObjectId] = None
    key: Optional[str] = None


# -------- Sprint --------
class SprintCreate(BaseModel):
    name: str
    project_id: PydanticObjectId
    goal: Optional[str] = None
    start_date: datetime
    end_date: datetime
    created_by: Optional[PydanticObjectId] = None


class SprintUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class SprintOut(BaseModel):
    id: str
    name: str
    project_id: str
    goal: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    state: Optional[str] = None
    issue_ids: List[str] = []   # <-- new field exposed to clients

    class Config:
        orm_mode = True


# -------- Issue --------
class IssueBase(BaseModel):
    project_id: PydanticObjectId
    epic_id: Optional[PydanticObjectId] = None
    sprint_id: Optional[PydanticObjectId] = None
    feature_id: Optional[PydanticObjectId] = None
    type: IssueType
    name: str
    description: Optional[str] = None
    priority: Priority = "medium"
    status: Status = "todo"
    assignee_id: Optional[PydanticObjectId] = None
    parent_id: Optional[PydanticObjectId] = None
    story_points: Optional[int] = None
    estimated_hours: Optional[float] = None
    location: Literal["backlog", "sprint", "board"] = "backlog"

    @validator("story_points")
    def validate_points(cls, v, values):
        if v is None:
            return v
        if v not in FIB_POINTS:
            raise ValueError(f"story_points must be one of {sorted(FIB_POINTS)}")
        t = values.get("type")
        if t != "story":
            raise ValueError("story_points allowed only for type=story")
        return v

    @validator("parent_id")
    def validate_parent(cls, parent, values):
        t: Optional[IssueType] = values.get("type")
        if t == "subtask" and parent is None:
            raise ValueError("subtask requires parent")
        if t != "subtask" and parent is not None:
            raise ValueError("parent allowed only when type=subtask")
        return parent


class IssueCreate(IssueBase):
    created_by: Optional[PydanticObjectId] = None


class IssueUpdate(BaseModel):
    epic_id: Optional[PydanticObjectId] = None
    sprint_id: Optional[PydanticObjectId] = None
    type: Optional[IssueType] = None
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[Status] = None
    assignee_id: Optional[PydanticObjectId] = None
    parent_id: Optional[PydanticObjectId] = None
    story_points: Optional[int] = None
    estimated_hours: Optional[float] = None
    location: Optional[Literal["backlog", "sprint", "board"]] = None
    updated_by: Optional[PydanticObjectId] = None
    updated_at: Optional[datetime] = None

    @validator("story_points")
    def _val_points(cls, v):
        if v is None:
            return v
        if v not in FIB_POINTS:
            raise ValueError(f"story_points must be one of {sorted(FIB_POINTS)}")
        return v


class IssueOut(IDModel, TimeStampMixin):
    key: Optional[str] = None
    project_id: PydanticObjectId
    epic_id: Optional[PydanticObjectId] = None
    sprint_id: Optional[PydanticObjectId] = None
    feature_id: Optional[PydanticObjectId] = None
    type: IssueType
    name: str
    description: Optional[str] = None
    priority: Priority
    status: Status
    assignee_id: Optional[PydanticObjectId] = None
    parent_id: Optional[PydanticObjectId] = None
    story_points: Optional[int] = None
    estimated_hours: Optional[float] = None
    time_spent_hours: float = 0.0
    created_by: PydanticObjectId
    updated_by: Optional[PydanticObjectId] = None
    location: Literal["backlog", "sprint", "board"]


# -------- Comment --------
class CommentCreate(BaseModel):
    project_id: PydanticObjectId
    issue_id: PydanticObjectId
    epic_id: Optional[PydanticObjectId] = None
    author_id: PydanticObjectId
    comment: str


class CommentOut(IDModel):
    project_id: PydanticObjectId
    issue_id: PydanticObjectId
    epic_id: Optional[PydanticObjectId] = None
    author_id: PydanticObjectId
    comment: str
    created_at: datetime


# -------- Linked Work Items --------
class LinkCreate(BaseModel):
    issue_id: PydanticObjectId
    linked_issue_id: PydanticObjectId
    reason: LinkReason = "relates_to"

    @validator("linked_issue_id")
    def no_self_link(cls, v, values):
        if v == values.get("issue_id"):
            raise ValueError("issue_id and linked_issue_id cannot be same")
        return v


class LinkOut(IDModel):
    issue_id: PydanticObjectId
    linked_issue_id: PydanticObjectId
    reason: LinkReason
    created_at: datetime


# -------- Time Tracking --------
class TimeClockIn(BaseModel):
    project_id: PydanticObjectId
    issue_id: PydanticObjectId


class TimeClockOut(BaseModel):
    time_entry_id: PydanticObjectId


class TimeAddManual(BaseModel):
    project_id: PydanticObjectId
    issue_id: PydanticObjectId
    seconds: int


class TimeEntryOut(IDModel):
    project_id: PydanticObjectId
    issue_id: PydanticObjectId
    user_id: PydanticObjectId
    clock_in: datetime
    clock_out: Optional[datetime] = None
    seconds: int = 0

# -------- Board Columns --------
class ColumnCreate(BaseModel):
    name: str
    status: str
    position: int
    color: Optional[str] = None

class ColumnUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    position: Optional[int] = None
    color: Optional[str] = None

# class ColumnsResponse(BaseModel):
#     columns: List[Dict[str, Any]]
#     total_columns: int

class FeatureCreate(BaseModel):
    project_id: PydanticObjectId
    epic_id: Optional[PydanticObjectId] = None
    name: str
    description: Optional[str] = None
    priority: Optional[str] = "medium"
    status: Optional[str] = "todo"

class FeatureUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    priority: Optional[str]
    status: Optional[str]

class FeatureOut(BaseModel):
    id: str
    project_id: str
    epic_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True