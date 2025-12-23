from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from app.services.report_service import ReportService
from app.routers.auth import get_current_user
from app.models.users import User

router = APIRouter(
    prefix="/projects",
    tags=["Reports"]
)

@router.get("/{project_id}/report", response_model=Dict[str, Any])
async def get_project_completion_report(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the Project Completion Report with comprehensive metrics.
    """
    result = await ReportService.generate_project_report(project_id)
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
    return result
