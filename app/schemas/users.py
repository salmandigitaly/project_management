from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime
from bson import ObjectId
from typing import Literal
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Literal["admin", "employee"] = "employee"
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    id: str
    created_at: datetime
    
    @validator('id', pre=True)
    def validate_id(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v
    
    class Config:
        from_attributes = True
        json_encoders = {ObjectId: str}

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    role: str
    user_id:str

class TokenRefresh(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    email: Optional[str] = None