"""
Time Tracking Router - Enhanced time tracking with reports and analytics
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from beanie import PydanticObjectId

from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import Project, Issue, TimeEntry
from app.schemas.project_management import (
    TimeClockIn, TimeClockOut, TimeAddManual, TimeEntryOut, TimeEntryUpdate,
    EmployeeTimeReport, IssueTimeReport, ProjectTimeSummary, ActiveTimeEntry
)
from app.services.permission import PermissionService
from app.core.timezone_utils import format_datetime_ist

security = HTTPBearer()
router = APIRouter(prefix="/time", tags=["time-tracking"])


def _id_of(link_or_doc) -> Optional[str]:
    """Return string id from a Beanie Link/Document/PydanticObjectId/None."""
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


# ==================== Basic Time Tracking ====================

@router.get("/entries")
async def list_entries(
    project_id: str = Query(...),
    issue_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """List time entries with optional filters"""
    if not await PermissionService.can_view_project(project_id, str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")

    query = TimeEntry.project.id == PydanticObjectId(project_id)
    entries = await TimeEntry.find(query).to_list()

    # Apply filters
    if issue_id:
        entries = [e for e in entries if _id_of(e.issue) == issue_id]
    if user_id:
        entries = [e for e in entries if _id_of(e.user) == user_id]

    # Build response with user and issue details
    result = []
    for e in entries:
        # Get user details
        user = await User.get(_id_of(e.user))
        user_name = user.full_name or user.email if user else "Unknown"
        
        # Get issue details
        issue = await Issue.get(_id_of(e.issue))
        issue_name = issue.name if issue else "Unknown"
        issue_key = getattr(issue, "key", None) if issue else None
        
        result.append({
            "id": _id_of(e),
            "project_id": _id_of(e.project),
            "issue_id": _id_of(e.issue),
            "issue_key": issue_key,
            "issue_name": issue_name,
            "user_id": _id_of(e.user),
            "user_name": user_name,
            "clock_in": e.clock_in,
            "clock_out": e.clock_out,
            "seconds": e.seconds,
            "hours": round(e.seconds / 3600, 2) if e.seconds else 0.0,
        })
    
    return result


@router.post("/clock-in")
async def clock_in(
    data: TimeClockIn,
    current_user: User = Depends(get_current_user)
):
    """Clock in to start tracking time on an issue"""
    if not await PermissionService.can_view_project(str(data.project_id), str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")

    # ✅ IMPROVEMENT 1: Prevent multiple active sessions
    active_session = await TimeEntry.find(
        TimeEntry.user.id == current_user.id,
        TimeEntry.clock_out == None
    ).first_or_none()
    
    if active_session:
        # Get issue details for better error message
        active_issue = await Issue.get(_id_of(active_session.issue))
        issue_name = active_issue.name if active_issue else "Unknown"
        issue_key = getattr(active_issue, "key", None) if active_issue else None
        
        elapsed = int((datetime.utcnow() - active_session.clock_in).total_seconds())
        elapsed_hours = round(elapsed / 3600, 2)
        
        raise HTTPException(
            status_code=400,
            detail={
                "message": "You already have an active session. Please clock out first.",
                "active_session": {
                    "entry_id": _id_of(active_session),
                    "issue_key": issue_key,
                    "issue_name": issue_name,
                    "clock_in": active_session.clock_in,
                    "elapsed_hours": elapsed_hours
                }
            }
        )

    project = await Project.get(str(data.project_id))
    issue = await Issue.get(str(data.issue_id))
    
    if not project or not issue:
        raise HTTPException(status_code=404, detail="Project or Issue not found")

    entry = TimeEntry(
        project=project,
        issue=issue,
        user=current_user,
        clock_in=datetime.utcnow(),
        clock_out=None,
        seconds=0,
    )
    await entry.insert()
    
    return {
        "id": _id_of(entry),
        "message": "Clocked in successfully",
        "clock_in": entry.clock_in,
        "issue_key": getattr(issue, "key", None),
        "issue_name": issue.name
    }


@router.post("/clock-out")
async def clock_out(
    data: TimeClockOut,
    current_user: User = Depends(get_current_user)
):
    """Clock out to stop tracking time"""
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
    
    return {
        "id": _id_of(entry),
        "seconds": entry.seconds,
        "hours": round(entry.seconds / 3600, 2),
        "message": "Clocked out successfully"
    }


@router.post("/add")
async def add_manual(
    data: TimeAddManual,
    current_user: User = Depends(get_current_user)
):
    """Manually add time entry"""
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
    
    return {
        "id": _id_of(entry),
        "seconds": entry.seconds,
        "hours": round(entry.seconds / 3600, 2),
        "message": "Time added successfully"
    }


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: str,
    data: TimeEntryUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a time entry (owner or admin only)"""
    entry = await TimeEntry.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")

    # Only owner or admin can update
    if _id_of(entry.user) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="No access")

    # Update fields
    if data.clock_in is not None:
        entry.clock_in = data.clock_in
    if data.clock_out is not None:
        entry.clock_out = data.clock_out
    if data.seconds is not None:
        entry.seconds = data.seconds
    elif entry.clock_out and entry.clock_in:
        # Recalculate seconds if times changed
        entry.seconds = int((entry.clock_out - entry.clock_in).total_seconds())

    await entry.save()
    
    return {
        "id": _id_of(entry),
        "message": "Time entry updated successfully"
    }


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a time entry (owner or admin only)"""
    entry = await TimeEntry.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")

    # Only owner or admin can delete
    if _id_of(entry.user) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="No access")

    await entry.delete()
    
    return {"message": "Time entry deleted successfully"}


# ==================== Reports & Analytics ====================

@router.get("/reports/employee", response_model=List[EmployeeTimeReport])
async def get_employee_report(
    project_id: str = Query(...),
    user_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Get time tracking report grouped by employee"""
    if not await PermissionService.can_view_project(project_id, str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")

    # Get all time entries for the project
    query = TimeEntry.project.id == PydanticObjectId(project_id)
    entries = await TimeEntry.find(query).to_list()

    # Apply filters
    if user_id:
        entries = [e for e in entries if _id_of(e.user) == user_id]
    if start_date:
        entries = [e for e in entries if e.clock_in >= start_date]
    if end_date:
        entries = [e for e in entries if e.clock_in <= end_date]

    # Group by user
    user_data = defaultdict(lambda: {
        "total_seconds": 0,
        "entries": [],
        "issues": {}
    })

    for entry in entries:
        uid = _id_of(entry.user)
        user_data[uid]["total_seconds"] += entry.seconds
        user_data[uid]["entries"].append(entry)
        
        # Track issues worked on
        issue_id = _id_of(entry.issue)
        if issue_id not in user_data[uid]["issues"]:
            user_data[uid]["issues"][issue_id] = {
                "seconds": 0,
                "entries_count": 0
            }
        user_data[uid]["issues"][issue_id]["seconds"] += entry.seconds
        user_data[uid]["issues"][issue_id]["entries_count"] += 1

    # Build response
    reports = []
    for uid, data in user_data.items():
        user = await User.get(uid)
        if not user:
            continue

        # Get issue details
        issues_worked = []
        for issue_id, issue_data in data["issues"].items():
            issue = await Issue.get(issue_id)
            if issue:
                issues_worked.append({
                    "issue_id": issue_id,
                    "issue_key": getattr(issue, "key", None),
                    "issue_name": issue.name,
                    "hours": round(issue_data["seconds"] / 3600, 2),
                    "entries_count": issue_data["entries_count"]
                })

        reports.append(EmployeeTimeReport(
            user_id=uid,
            user_name=user.full_name or user.email,
            user_email=user.email,
            total_hours=round(data["total_seconds"] / 3600, 2),
            total_entries=len(data["entries"]),
            issues_worked=issues_worked
        ))

    return reports


@router.get("/reports/issue", response_model=List[IssueTimeReport])
async def get_issue_report(
    project_id: str = Query(...),
    issue_id: Optional[str] = Query(None),
    sprint_id: Optional[str] = Query(None),
    show_variance_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
):
    """Get time tracking report grouped by issue with estimated vs actual comparison"""
    if not await PermissionService.can_view_project(project_id, str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")

    # Get issues
    if issue_id:
        issue = await Issue.get(issue_id)
        issues = [issue] if issue else []
    elif sprint_id:
        issues = await Issue.find(Issue.sprint.id == PydanticObjectId(sprint_id)).to_list()
    else:
        issues = await Issue.find(Issue.project.id == PydanticObjectId(project_id)).to_list()

    # Build reports
    reports = []
    for issue in issues:
        # Get time entries for this issue
        entries = await TimeEntry.find(TimeEntry.issue.id == issue.id).to_list()
        
        actual_hours = issue.time_spent_hours or 0.0
        estimated_hours = issue.estimated_hours
        variance_hours = actual_hours - (estimated_hours or 0.0)
        
        # Calculate variance percentage
        variance_percentage = None
        if estimated_hours and estimated_hours > 0:
            variance_percentage = round((variance_hours / estimated_hours) * 100, 2)

        # Skip if show_variance_only and no variance
        if show_variance_only and abs(variance_hours) < 0.01:
            continue

        # Get assignee details
        assignee_id = None
        assignee_name = None
        if issue.assignee:
            assignee_id = _id_of(issue.assignee)
            assignee = await User.get(assignee_id)
            if assignee:
                assignee_name = assignee.full_name or assignee.email

        reports.append(IssueTimeReport(
            issue_id=_id_of(issue),
            issue_key=getattr(issue, "key", None),
            issue_name=issue.name,
            estimated_hours=estimated_hours,
            actual_hours=actual_hours,
            variance_hours=variance_hours,
            variance_percentage=variance_percentage,
            assignee_id=assignee_id,
            assignee_name=assignee_name,
            time_entries_count=len(entries),
            status=issue.status
        ))

    # Sort by variance (highest first)
    reports.sort(key=lambda x: abs(x.variance_hours), reverse=True)
    
    return reports


@router.get("/reports/project", response_model=ProjectTimeSummary)
async def get_project_summary(
    project_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Get overall project time summary"""
    if not await PermissionService.can_view_project(project_id, str(current_user.id)):
        raise HTTPException(status_code=403, detail="No access")

    project = await Project.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all issues for the project
    issues = await Issue.find(Issue.project.id == PydanticObjectId(project_id)).to_list()

    total_estimated = sum(i.estimated_hours or 0.0 for i in issues)
    total_actual = sum(i.time_spent_hours or 0.0 for i in issues)
    total_variance = total_actual - total_estimated

    # Get unique employees who logged time
    entries = await TimeEntry.find(TimeEntry.project.id == PydanticObjectId(project_id)).to_list()
    unique_users = set(_id_of(e.user) for e in entries)

    # Get active sessions (clocked in but not out)
    active_entries = await TimeEntry.find(
        TimeEntry.project.id == PydanticObjectId(project_id),
        TimeEntry.clock_out == None
    ).to_list()

    return ProjectTimeSummary(
        project_id=project_id,
        project_name=project.name,
        total_estimated_hours=round(total_estimated, 2),
        total_actual_hours=round(total_actual, 2),
        total_variance_hours=round(total_variance, 2),
        issues_count=len(issues),
        employees_count=len(unique_users),
        active_sessions_count=len(active_entries)
    )


@router.get("/active", response_model=List[ActiveTimeEntry])
async def get_active_entries(
    project_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Get all currently active time entries (clocked in but not clocked out)"""
    # Build query
    query_conditions = [TimeEntry.clock_out == None]
    
    if project_id:
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")
        query_conditions.append(TimeEntry.project.id == PydanticObjectId(project_id))
    
    if user_id:
        query_conditions.append(TimeEntry.user.id == PydanticObjectId(user_id))

    # Get active entries
    if len(query_conditions) == 1:
        entries = await TimeEntry.find(query_conditions[0]).to_list()
    else:
        entries = await TimeEntry.find(*query_conditions).to_list()

    # Build response
    active_entries = []
    now = datetime.utcnow()
    
    for entry in entries:
        # Get user details
        user = await User.get(_id_of(entry.user))
        if not user:
            continue

        # Get issue details
        issue = await Issue.get(_id_of(entry.issue))
        if not issue:
            continue

        # Calculate elapsed time
        elapsed_seconds = int((now - entry.clock_in).total_seconds())
        elapsed_hours = round(elapsed_seconds / 3600, 2)

        active_entries.append(ActiveTimeEntry(
            entry_id=_id_of(entry),
            user_id=_id_of(user),
            user_name=user.full_name or user.email,
            issue_id=_id_of(issue),
            issue_key=getattr(issue, "key", None),
            issue_name=issue.name,
            clock_in=entry.clock_in,
            elapsed_seconds=elapsed_seconds,
            elapsed_hours=elapsed_hours
        ))

    return active_entries


# ==================== Daily Summary ====================

@router.get("/my-summary")
async def get_my_daily_summary(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to today"),
    current_user: User = Depends(get_current_user),
):
    """✅ IMPROVEMENT 2: Get employee's daily time summary"""
    
    # Parse date or use today
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        target_date = datetime.utcnow()
    
    # Get start and end of day (UTC)
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Get all time entries for this user on this date
    entries = await TimeEntry.find(
        TimeEntry.user.id == current_user.id,
        TimeEntry.clock_in >= day_start,
        TimeEntry.clock_in <= day_end
    ).to_list()
    
    # Calculate totals
    total_seconds = sum(e.seconds for e in entries)
    total_hours = round(total_seconds / 3600, 2)
    
    # Group by issue
    issues_worked = {}
    for entry in entries:
        issue_id = _id_of(entry.issue)
        if issue_id not in issues_worked:
            issue = await Issue.get(issue_id)
            issues_worked[issue_id] = {
                "issue_id": issue_id,
                "issue_key": getattr(issue, "key", None) if issue else None,
                "issue_name": issue.name if issue else "Unknown",
                "hours": 0.0,
                "entries_count": 0
            }
        issues_worked[issue_id]["hours"] += round(entry.seconds / 3600, 2)
        issues_worked[issue_id]["entries_count"] += 1
    
    # Check for active session
    active_session = None
    for entry in entries:
        if entry.clock_out is None:
            issue = await Issue.get(_id_of(entry.issue))
            elapsed = int((datetime.utcnow() - entry.clock_in).total_seconds())
            active_session = {
                "entry_id": _id_of(entry),
                "issue_key": getattr(issue, "key", None) if issue else None,
                "issue_name": issue.name if issue else "Unknown",
                "clock_in": entry.clock_in,
                "elapsed_hours": round(elapsed / 3600, 2)
            }
            break
    
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "total_hours": total_hours,
        "total_entries": len(entries),
        "issues_worked": list(issues_worked.values()),
        "active_session": active_session,
        "overtime": total_hours > 8.0,  # Flag if more than 8 hours
        "overtime_hours": round(max(0, total_hours - 8.0), 2)
    }

