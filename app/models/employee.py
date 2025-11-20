from datetime import datetime
from typing import Optional
from beanie import Document 
import beanie
from pydantic import Field
from app.models.users import User

class Attendance(Document):
    # store plain user info to simplify queries and avoid Link/class-attribute issues
    user_id: str
    user_name: Optional[str] = None
    check_in: datetime = Field(default_factory=datetime.utcnow)
    check_out: Optional[datetime] = None
    note: Optional[str] = None
    meta: Optional[dict] = None  # e.g. geolocation, ip
    status: str = "present"  # "present" | "checked_out"

    class Settings:
        name = "attendances"


class LeaveRequest(Document):
    user: "beanie.Link['User']"
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None
    status: str = "pending"  # pending / approved / rejected
    reviewed_by: Optional["beanie.Link['User']"] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "leaves"