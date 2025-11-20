from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import date, datetime

class EmergencyContact(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    relationship: Optional[str] = None

class PersonalInfo(BaseModel):
    date_of_birth: Optional[date] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    emergency_contact: Optional[EmergencyContact] = None
    profile_image: Optional[str] = None

class WorkInfo(BaseModel):
    department: Optional[str] = None
    designation: Optional[str] = None
    date_joined: Optional[date] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    skills: Optional[List[str]] = None

class LeaveBalanceItem(BaseModel):
    year: int
    casual_leave: int
    sick_leave: int
    last_updated: datetime

class EmployeeCreate(BaseModel):
    emp_id: Optional[str] = None
    full_name: str
    email: str
    password: str
    personal_info: Optional[PersonalInfo] = None
    work_info: Optional[WorkInfo] = None
    payroll_group: Optional[str] = None

class EmployeeProfileOut(BaseModel):
    id: str
    emp_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    personal_info: Optional[PersonalInfo] = None
    work_info: Optional[WorkInfo] = None
    payroll_group: Optional[str] = None
    leave_balances: Optional[List[LeaveBalanceItem]] = None
    # joined_at: Optional[datetime] = None

# New: update schema used by PUT /me (all fields optional)
class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    personal_info: Optional[PersonalInfo] = None
    work_info: Optional[WorkInfo] = None
    payroll_group: Optional[str] = None
    profile_image: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None

class AttendanceIn(BaseModel):
    note: Optional[str] = None

class LeaveCreate(BaseModel):
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None