from beanie import Document
from pydantic import EmailStr, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

class User(Document):
    email: EmailStr = Field(unique=True)
    hashed_password: str
    full_name: Optional[str] = None
    role: str = "employee"  # ← THIS LINE MUST BE CHANGED
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # --- new employee fields ---
    emp_id: Optional[str] = None
    personal_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    work_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    payroll_group: Optional[str] = None

    # leave balances: list of { year, casual_leave, sick_leave, last_updated }
    leave_balances: List[Dict[str, Any]] = Field(default_factory=list)

    class Settings:
        name = "users"