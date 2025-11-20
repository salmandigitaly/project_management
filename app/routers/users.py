from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from typing import List, Optional
from app.models.users import User
from app.schemas.users import UserResponse, UserUpdate
from app.routers.auth import get_current_user

class UsersRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/users", tags=["users"])
        self.security = HTTPBearer()
        self.setup_routes()
    
    def setup_routes(self):
        self.router.add_api_route("/me", self.get_current_user_info, methods=["GET"], dependencies=[Depends(self.security)])
        self.router.add_api_route("/", self.get_users, methods=["GET"], response_model=List[UserResponse], dependencies=[Depends(self.security)])
        self.router.add_api_route("/{user_id}", self.get_user, methods=["GET"], response_model=UserResponse, dependencies=[Depends(self.security)])
        self.router.add_api_route("/{user_id}", self.update_user, methods=["PUT"], response_model=UserResponse, dependencies=[Depends(self.security)])
        self.router.add_api_route("/{user_id}", self.delete_user, methods=["DELETE"], dependencies=[Depends(self.security)])
    
    async def get_current_user_info(self, current_user: User = Depends(get_current_user)):
        user_dict = current_user.dict()
        user_dict["id"] = str(current_user.id)
        return user_dict
    
    async def get_users(
        self,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        role: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        current_user: User = Depends(get_current_user)  # ADD THIS LINE
    ):
        query = {}
        if role:
            query["role"] = role
        if is_active is not None:
            query["is_active"] = is_active
            
        users = await User.find(query, skip=skip, limit=limit).to_list()
        
        # Convert ObjectId to string and return as list (FIXED)
        user_list = []
        for user in users:
            user_dict = user.dict()
            user_dict["id"] = str(user.id)
            user_list.append(user_dict)
        
        return user_list  # RETURN LIST INSTEAD OF YIELD
    
    async def get_user(self, user_id: str):
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user_dict = user.dict()
        user_dict["id"] = str(user.id)
        return user_dict
    
    async def update_user(
        self,
        user_id: str,
        user_data: UserUpdate,
        current_user: User = Depends(get_current_user)
    ):
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Only allow users to update their own profile or admins
        if str(user.id) != str(current_user.id) and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        
        update_data = user_data.dict(exclude_unset=True)
        await user.set(update_data)
        
        user_dict = user.dict()
        user_dict["id"] = str(user.id)
        return user_dict
    
    async def delete_user(
        self,
        user_id: str,
        current_user: User = Depends(get_current_user)
    ):
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete users"
            )
        
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        await user.delete()
        return {"message": "User deleted successfully"}

users_router = UsersRouter().router