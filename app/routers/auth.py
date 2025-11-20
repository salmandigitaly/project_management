from fastapi.security import HTTPBearer
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from app.core.security import (
    verify_password, get_password_hash, 
    create_access_token, create_refresh_token, verify_token
)
from app.models.users import User
from app.schemas.users import Token, UserCreate, UserResponse, TokenRefresh
from typing import Annotated, Optional
from datetime import timedelta
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()
# Request models
class LoginRequest(BaseModel):
    email: str
    password: str

# FIXED Dependency for JWT token - ONLY CHANGE THIS PART
async def get_current_user_dependency(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    
    try:
        # Extract token from "Bearer <token>"
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Use: Bearer <token>",
        )
    
    # Now verify the token
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - Invalid token",
        )
    
    email = payload.get("sub")
    token_type = payload.get("type")
    
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - No email in token",
        )
    
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type - Use access token",
        )
    
    user = await User.find_one(User.email == email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user

# KEEP EVERYTHING ELSE EXACTLY THE SAME - DON'T CHANGE YOUR ROUTES
class AuthRouter:
    def __init__(self):
        self.router = APIRouter()
        self.setup_routes()
    
    def setup_routes(self):
        self.router.add_api_route("/register", self.register, methods=["POST"], response_model=UserResponse)
        self.router.add_api_route("/login", self.login, methods=["POST"], response_model=Token)
        self.router.add_api_route("/refresh", self.refresh_token, methods=["POST"], response_model=Token)
        self.router.add_api_route("/me", self.get_current_user, methods=["GET"], response_model=UserResponse, dependencies=[Depends(security)])
    
    async def register(self, user_data: UserCreate):
        # Check if user exists
        existing_user = await User.find_one(User.email == user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        hashed_password = get_password_hash(user_data.password)
        user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
            role=user_data.role,
            is_active=user_data.is_active
        )
        
        await user.insert()
        
        # Convert to response
        user_dict = user.dict()
        user_dict["id"] = str(user.id)
        return UserResponse(**user_dict)


    
    async def login(self, login_data: LoginRequest):
        user = await User.find_one(User.email == login_data.email)
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Create both access and refresh tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id" :str(user.id),
            "role": user.role
        }
    
    async def refresh_token(self, refresh_data: TokenRefresh):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
        
        payload = verify_token(refresh_data.refresh_token)
        if payload is None:
            raise credentials_exception
        
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if email is None or token_type != "refresh":
            raise credentials_exception
        
        user = await User.find_one(User.email == email)
        if user is None:
            raise credentials_exception
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Create new access token
        access_token = create_access_token(data={"sub": user.email})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_data.refresh_token,  # Return same refresh token
            "token_type": "bearer"
        }
    
    async def get_current_user(self, current_user: User = Depends(get_current_user_dependency)):
        user_dict = current_user.dict()
        user_dict["id"] = str(current_user.id)
        return UserResponse(**user_dict)

# Create router instance
auth_router = AuthRouter().router

# Export the dependency for use in other routers
get_current_user = get_current_user_dependency

@router.post("/register")
async def register(*args, **kwargs):
    # registration disabled — admins must create users
    raise HTTPException(status_code=403, detail="Registration disabled. Admins only.")