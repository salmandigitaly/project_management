from fastapi import APIRouter, Depends, HTTPException, Query, Path
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Dict, Any
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeProfileOut,
    AttendanceIn,
    LeaveCreate,
    EmployeeUpdate,  # added
)
from app.core.security import get_password_hash
from pydantic import BaseModel
from bson import ObjectId, errors as bson_errors
from app.routers.auth import get_current_user
from app.models.users import User
from app.models.employee import Attendance, LeaveRequest  # existing models

router = APIRouter(prefix="/employees", tags=["employees"])


def ensure_admin(user: User):
    if not user or getattr(user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="admin required")


class SimpleUserOut(BaseModel):
    id: str
    email: str
    name: Optional[str] = None


# helper to generate emp_id
async def _generate_emp_id() -> str:
    users = await User.find({"emp_id": {"$regex": "^DIGI"}}).to_list()
    nums = []
    for u in users:
        v = getattr(u, "emp_id", None)
        if v and v.startswith("DIGI"):
            suffix = v.replace("DIGI", "")
            if suffix.isdigit():
                nums.append(int(suffix))
    next_n = max(nums) + 1 if nums else 1
    return f"DIGI{next_n:04d}"


def _default_leave_balance_entry(year: int) -> Dict[str, Any]:
    return {
        "year": year,
        "casual_leave": 12,
        "sick_leave": 10,
        "last_updated": datetime.utcnow().replace(tzinfo=timezone.utc),
    }


def _sanitize_dates(obj):
    """
    Recursively convert date/datetime objects to ISO strings so Beanie can encode them.
    """
    if obj is None:
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _sanitize_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_dates(v) for v in obj]
    return obj


@router.post("/admin/create", response_model=EmployeeProfileOut)
async def admin_create_employee(payload: EmployeeCreate, current_user: User = Depends(get_current_user)):
    ensure_admin(current_user)
    exists = await User.find_one(User.email == payload.email)
    if exists:
        raise HTTPException(status_code=400, detail="User with email already exists")

    # emp_id uniqueness / auto-generate
    emp_id = payload.emp_id
    if emp_id:
        dup = await User.find_one(User.emp_id == emp_id)
        if dup:
            raise HTTPException(status_code=400, detail="emp_id already exists")
    else:
        emp_id = await _generate_emp_id()

    hashed = get_password_hash(payload.password)

    # sanitize nested date fields before saving
    personal = _sanitize_dates(payload.personal_info.dict()) if payload.personal_info else {}
    work = _sanitize_dates(payload.work_info.dict()) if payload.work_info else {}

    now_year = datetime.utcnow().year
    leave_entry = _default_leave_balance_entry(now_year)

    new_user = User(
        email=payload.email,
        hashed_password=hashed,
        role="employee",
        full_name=payload.full_name,
        emp_id=emp_id,
        personal_info=personal,
        work_info=work,
        payroll_group=payload.payroll_group,
        leave_balances=[leave_entry],
    )
    await new_user.insert()

    # reload full doc from DB to ensure defaults and linked fields are present
    created = await User.get(str(new_user.id))
    return {
        "id": str(created.id),
        "emp_id": getattr(created, "emp_id", None),
        "full_name": getattr(created, "full_name", None),
        "email": getattr(created, "email", None),
        "personal_info": getattr(created, "personal_info", None),
        "work_info": getattr(created, "work_info", None),
        "payroll_group": getattr(created, "payroll_group", None),
        "leave_balances": getattr(created, "leave_balances", []),
        # "joined_at": getattr(created, "joined_at", None),
    }


# update get_my_profile response to include new fields
@router.get("/me", response_model=EmployeeProfileOut)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    # load fresh document from DB to include emp_id, personal_info, work_info etc.
    try:
        uid = str(current_user.id)
    except Exception:
        uid = getattr(current_user, "id", None)
    user_doc = await User.get(uid) if uid else None
    if not user_doc:
        # fallback to token object but most fields will be missing
        user_doc = current_user

    profile = {
        "id": str(user_doc.id),
        "emp_id": getattr(user_doc, "emp_id", None),
        "email": getattr(user_doc, "email", None),
        "full_name": getattr(user_doc, "full_name", None),
        "personal_info": getattr(user_doc, "personal_info", None),
        "work_info": getattr(user_doc, "work_info", None),
        "payroll_group": getattr(user_doc, "payroll_group", None),
        "leave_balances": getattr(user_doc, "leave_balances", []),
        # "joined_at": getattr(user_doc, "joined_at", None),
    }
    return profile


# allow employee to update only allowed profile fields (personal_info, work_info, profile_image)
@router.put("/me", response_model=EmployeeProfileOut)
async def update_my_profile(payload: EmployeeUpdate, current_user: User = Depends(get_current_user)):
    """
    Update current user's editable profile fields.
    Request body shows full editable schema — send only fields you want to change.
    """
    # load full user doc
    try:
        uid = str(current_user.id)
    except Exception:
        uid = getattr(current_user, "id", None)
    user_doc = await User.get(uid) if uid else None
    if not user_doc:
        raise HTTPException(status_code=404, detail="user not found")

    data = payload.dict(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="no valid fields to update")

    # only allow these fields to be set
    allowed = {"full_name", "personal_info", "work_info", "profile_image", "phone", "location", "payroll_group"}
    for k, v in data.items():
        if k in allowed:
            setattr(user_doc, k, v)

    await user_doc.save()

    # return updated profile
    return {
        "id": str(user_doc.id),
        "emp_id": getattr(user_doc, "emp_id", None),
        "full_name": getattr(user_doc, "full_name", None),
        "email": getattr(user_doc, "email", None),
        "personal_info": getattr(user_doc, "personal_info", None),
        "work_info": getattr(user_doc, "work_info", None),
        "payroll_group": getattr(user_doc, "payroll_group", None),
        "leave_balances": getattr(user_doc, "leave_balances", []),
        # "joined_at": getattr(user_doc, "joined_at", None),
    }


@router.post("/me/attendance/checkin")
async def attendance_checkin(note: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    # prevent duplicate check-in for same day
    today = date.today()
    start_dt = datetime.combine(today, datetime.min.time())
    existing = await Attendance.find_one({"user_id": str(current_user.id), "check_in": {"$gte": start_dt}})
    if existing and existing.check_out is None:
        raise HTTPException(status_code=400, detail="Already checked in and not checked out")

    # reload full user doc to get emp_id/full_name
    try:
        uid = str(current_user.id)
    except Exception:
        uid = getattr(current_user, "id", None)
    user_doc = await User.get(uid) if uid else None
    emp_id = getattr(user_doc, "emp_id", None) if user_doc else None
    full_name = getattr(user_doc, "full_name", None) or getattr(user_doc, "name", None) or ""

    att = Attendance(
        user_id=str(current_user.id),
        user_name=full_name,
        check_in=datetime.utcnow(),
        note=note,
        status="present",
    )
    await att.insert()

    return {
        "id": str(att.id),
        "emp_id": emp_id,
        "full_name": full_name,
        "check_in": att.check_in.isoformat() if att.check_in else None,
        "status": att.status,
    }


@router.post("/me/attendance/checkout")
async def attendance_checkout(note: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    # find last open attendance by user_id
    att = await Attendance.find_one({"user_id": str(current_user.id), "check_out": None})
    if not att:
        raise HTTPException(status_code=400, detail="No active check-in found")

    att.check_out = datetime.utcnow()
    if note:
        att.note = (att.note or "") + " | " + note
    att.status = "checked_out"
    await att.save()

    # resolve user for emp_id/full_name
    user_doc = await User.get(att.user_id) if att.user_id else None
    emp_id = getattr(user_doc, "emp_id", None) if user_doc else None
    full_name = getattr(user_doc, "full_name", None) or getattr(user_doc, "name", None) or att.user_name

    return {
        "id": str(att.id),
        "emp_id": emp_id,
        "full_name": full_name,
        "check_in": att.check_in.isoformat() if att.check_in else None,
        "check_out": att.check_out.isoformat() if att.check_out else None,
        "status": att.status,
    }


@router.post("/me/leaves", response_model=dict)
async def create_leave(payload: LeaveCreate, current_user: User = Depends(get_current_user)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    # resolve full user document from DB (token/current_user may be lightweight)
    try:
        uid = str(current_user.id)
    except Exception:
        uid = getattr(current_user, "id", None)
    user_doc = await User.get(uid) if uid else None

    leave = LeaveRequest(
        user=user_doc or current_user,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        status="pending",
        created_at=datetime.utcnow(),
    )
    await leave.insert()

    # compute inclusive total days
    try:
        total_days = (leave.end_date.date() - leave.start_date.date()).days + 1
    except Exception:
        total_days = None

    emp_id = getattr(user_doc, "emp_id", None) if user_doc else None
    full_name = (
        getattr(user_doc, "full_name", None)
        or getattr(current_user, "full_name", None)
        or getattr(current_user, "name", None)
        or None
    )

    return {
        "id": str(leave.id),
        "status": leave.status,
        "emp_id": emp_id,
        "full_name": full_name,
        "leave_type": leave.leave_type,
        "reason": leave.reason,
        "total_days": total_days,
    }


@router.get("/me/leaves")
async def my_leaves(current_user: User = Depends(get_current_user)):
    items = await LeaveRequest.find(LeaveRequest.user.id == current_user.id).to_list()
    return [{"id": str(i.id), "start": i.start_date, "end": i.end_date, "status": i.status, "reason": i.reason} for i in items]


# admin_list_leaves: return emp_id and full_name; safe resolution of linked user
@router.get("/admin/leaves")
async def admin_list_leaves(status: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    ensure_admin(current_user)
    q = {}
    if status:
        q["status"] = status
    items = await LeaveRequest.find(q).to_list()

    result = []
    for i in items:
        # resolve user
        user_doc = await _resolve_user_from_link(i.user)
        user_emp_id = getattr(user_doc, "emp_id", None) if user_doc else None
        user_full_name = getattr(user_doc, "full_name", None) if user_doc else None

        # compute inclusive total days safely
        total_days = None
        try:
            total_days = (i.end_date.date() - i.start_date.date()).days + 1
        except Exception:
            try:
                # fallback if start/end are strings
                from datetime import datetime as _dt
                s = _dt.fromisoformat(str(i.start_date))
                e = _dt.fromisoformat(str(i.end_date))
                total_days = (e.date() - s.date()).days + 1
            except Exception:
                total_days = None

        result.append({
            "id": str(i.id),
            "user_emp_id": user_emp_id,
            "user_full_name": user_full_name,
            "start": i.start_date,
            "end": i.end_date,
            "status": i.status,
            "total_days": total_days,
        })
    return result


# admin approve leave: update leave_balances automatically when approved
@router.post("/admin/leaves/{leave_id}/approve")
async def admin_approve_leave(leave_id: str = Path(...), current_user: User = Depends(get_current_user)):
    ensure_admin(current_user)
    leave = await LeaveRequest.get(leave_id)
    if not leave:
        raise HTTPException(status_code=404, detail="leave not found")

    # resolve user document from the Link / id / emp_id / email
    user_doc = await _resolve_user_from_link(leave.user)

    # compute inclusive days safely (handles date/datetime or ISO strings)
    days = 0
    try:
        days = (leave.end_date.date() - leave.start_date.date()).days + 1
    except Exception:
        try:
            from datetime import datetime as _dt
            s = _dt.fromisoformat(str(leave.start_date))
            e = _dt.fromisoformat(str(leave.end_date))
            days = (e.date() - s.date()).days + 1
        except Exception:
            days = 0

    # map leave_type to balance key
    lt = (leave.leave_type or "").lower()
    balance_key = None
    if "casual" in lt:
        balance_key = "casual_leave"
    elif "sick" in lt:
        balance_key = "sick_leave"

    # update balances if user exists and we have a valid balance key and days
    if user_doc and balance_key and days > 0:
        year = getattr(leave.start_date, "year", datetime.utcnow().year)
        balances = user_doc.leave_balances or []
        entry = next((b for b in balances if b.get("year") == year), None)
        if not entry:
            entry = _default_leave_balance_entry(year)
            balances.append(entry)
        entry[balance_key] = max(0, entry.get(balance_key, 0) - days)
        entry["last_updated"] = datetime.utcnow().replace(tzinfo=timezone.utc)
        user_doc.leave_balances = balances
        await user_doc.save()

    leave.status = "approved"
    leave.reviewed_by = current_user
    leave.reviewed_at = datetime.utcnow()
    await leave.save()
    return {"ok": True, "id": str(leave.id), "status": leave.status}


@router.post("/admin/leaves/{leave_id}/reject")
async def admin_reject_leave(leave_id: str = Path(...), current_user: User = Depends(get_current_user)):
    ensure_admin(current_user)
    leave = await LeaveRequest.get(leave_id)
    if not leave:
        raise HTTPException(status_code=404, detail="leave not found")
    leave.status = "rejected"
    leave.reviewed_by = current_user
    leave.reviewed_at = datetime.utcnow()
    await leave.save()
    return {"ok": True, "id": str(leave.id), "status": leave.status}


@router.get("/admin/list", response_model=List[EmployeeProfileOut])
async def admin_list_employees(
    current_user: User = Depends(get_current_user),
    include_password: bool = Query(False, description="If true returns 'password':'REDACTED' (never returns plaintext)")
):
    """
    Admin-only: return all users with full stored profile fields.
    Note: plaintext passwords are never returned. If you need a one-time password
    for a newly created user, return it from the create endpoint at creation time only.
    """
    ensure_admin(current_user)

    users = await User.find({}).to_list()  # load full documents from DB
    result: List[Dict[str, Any]] = []
    for u in users:
        # build response using DB fields (may be dicts / lists or None)
        item: Dict[str, Any] = {
            "id": str(u.id),
            "emp_id": getattr(u, "emp_id", None),
            "full_name": getattr(u, "full_name", None),
            "email": getattr(u, "email", None),
            "personal_info": getattr(u, "personal_info", None),
            "work_info": getattr(u, "work_info", None),
            "payroll_group": getattr(u, "payroll_group", None),
            "leave_balances": getattr(u, "leave_balances", None),
        }
        if include_password:
            # do NOT expose hashed_password or plain password
            item["password"] = "REDACTED"
        result.append(item)

    return result


def _parse_report_date(s: str) -> date:
    """
    Accepts 'DD.MM.YYYY' or 'YYYY-MM-DD' (ISO) or 'DD-MM-YYYY'.
    Returns date object or raises ValueError.
    """
    from datetime import datetime as _dt
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return _dt.strptime(s, fmt).date()
        except Exception:
            continue
    raise ValueError("date must be DD.MM.YYYY or YYYY-MM-DD")


@router.get("/admin/attendance")
async def admin_attendance_report(date: str = Query(..., description="date as DD.MM.YYYY or YYYY-MM-DD"), current_user: User = Depends(get_current_user)):
    """
    Admin-only: return attendance (present) for the provided date.
    Returns list of { emp_id, full_name, check_in, check_out, status }.
    """
    ensure_admin(current_user)
    try:
        report_date = _parse_report_date(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_dt = datetime.combine(report_date, datetime.min.time())
    end_dt = start_dt + timedelta(days=1)

    items = await Attendance.find({"check_in": {"$gte": start_dt, "$lt": end_dt}}).to_list()

    result: List[Dict[str, Any]] = []
    for a in items:
        user_doc = await User.get(a.user_id) if a.user_id else None
        emp_id = getattr(user_doc, "emp_id", None) if user_doc else None
        full_name = getattr(user_doc, "full_name", None) or getattr(user_doc, "name", None) or a.user_name
        result.append({
            "emp_id": emp_id,
            "full_name": full_name,
            "check_in": a.check_in.isoformat() if a.check_in else None,
            "check_out": a.check_out.isoformat() if a.check_out else None,
            "status": a.status,
        })

    return result


async def _resolve_user_from_link(link) -> Optional[User]:
    """
    Resolve various shapes of `link` to a User document:
    - already-resolved User
    - beanie Link wrapper (.ref)
    - object with .id / ._id
    - ObjectId or string (try as ObjectId, then emp_id, then email)
    Returns User or None.
    """
    if not link:
        return None

    # already a loaded User document
    if isinstance(link, User):
        return link

    # beanie Link wrapper (.ref)
    ref = getattr(link, "ref", None)
    if ref is not None and getattr(ref, "id", None) is not None:
        try:
            return await User.get(str(ref.id))
        except Exception:
            return None

    # try .id or ._id attributes
    candidate_id = getattr(link, "id", None) or getattr(link, "_id", None)
    if candidate_id:
        try:
            return await User.get(str(candidate_id))
        except Exception:
            pass

    # raw ObjectId
    if isinstance(link, ObjectId):
        try:
            return await User.get(str(link))
        except Exception:
            pass

    # string fallback: try ObjectId, then emp_id, then email
    try:
        s = str(link)
    except Exception:
        return None

    # try as ObjectId
    try:
        if ObjectId.is_valid(s):
            try:
                return await User.get(s)
            except Exception:
                pass
    except Exception:
        pass

    # search by emp_id or email
    try:
        return await User.find_one({"$or": [{"emp_id": s}, {"email": s}]})
    except Exception:
        return None


@router.get("/admin/employee/{emp_id}", response_model=EmployeeProfileOut)
async def admin_get_employee(emp_id: str = Path(...), current_user: User = Depends(get_current_user)):
    """
    Admin-only: fetch a single employee by emp_id (full profile).
    """
    ensure_admin(current_user)
    user_doc = await User.find_one(User.emp_id == emp_id)
    if not user_doc:
        raise HTTPException(status_code=404, detail="employee not found")

    return {
        "id": str(user_doc.id),
        "emp_id": getattr(user_doc, "emp_id", None),
        "full_name": getattr(user_doc, "full_name", None),
        "email": getattr(user_doc, "email", None),
        "personal_info": getattr(user_doc, "personal_info", None),
        "work_info": getattr(user_doc, "work_info", None),
        "payroll_group": getattr(user_doc, "payroll_group", None),
        "leave_balances": getattr(user_doc, "leave_balances", []),
        # "joined_at": getattr(user_doc, "joined_at", None),
    }


@router.delete("/admin/employee/{emp_id}")
async def admin_delete_employee(
    emp_id: str = Path(...),
    cascade: bool = Query(False, description="If true, delete related attendances and leave requests"),
    current_user: User = Depends(get_current_user),
):
    """
    Admin-only: delete employee by emp_id. If cascade=true, also delete attendance and leave records.
    """
    ensure_admin(current_user)
    user_doc = await User.find_one(User.emp_id == emp_id)
    if not user_doc:
        raise HTTPException(status_code=404, detail="employee not found")

    deleted_att = 0
    deleted_leaves = 0

    if cascade:
        # delete attendances for this user_id
        atts = await Attendance.find({"user_id": str(user_doc.id)}).to_list()
        for a in atts:
            await a.delete()
            deleted_att += 1

        # try to delete leave requests referencing this user (attempt Link-based query first)
        leaves = []
        try:
            leaves = await LeaveRequest.find(LeaveRequest.user.id == user_doc.id).to_list()
        except Exception:
            # fallback: try string match
            leaves = await LeaveRequest.find({"user": str(user_doc.id)}).to_list()

        for l in leaves:
            await l.delete()
            deleted_leaves += 1

    # delete user
    await user_doc.delete()

    return {"ok": True, "emp_id": emp_id, "deleted_attendances": deleted_att, "deleted_leaves": deleted_leaves}