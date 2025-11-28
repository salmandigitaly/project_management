# app/routers/boards.py
from __future__ import annotations
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer
from beanie import PydanticObjectId

from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import Project, Sprint, Issue, Board, BoardColumn
from app.schemas.project_management import ColumnCreate, ColumnUpdate
from app.services.permission import PermissionService

security = HTTPBearer()

ColumnStatus = Literal["todo", "inprogress", "done"]


def _issue_to_minimal_dict(issue: Issue) -> Dict[str, Any]:
    # Helper function to safely get ID from Link or Document
    def _safe_get_id(link_or_doc):
        if not link_or_doc:
            return None
        # If it's a fetched document with id
        if hasattr(link_or_doc, 'id'):
            return str(link_or_doc.id)
        # If it's a Link, get the referenced id
        if hasattr(link_or_doc, 'ref') and hasattr(link_or_doc.ref, 'id'):
            return str(link_or_doc.ref.id)
        return None

    return {
        "id": str(issue.id),
        "key": issue.key,
        "name": issue.name,
        "description": issue.description,
        "type": issue.type,
        "priority": issue.priority,
        "status": issue.status,
        "location": issue.location,
        "project_id": _safe_get_id(issue.project),
        "epic_id": _safe_get_id(issue.epic),
        "sprint_id": _safe_get_id(issue.sprint),
        "assignee_id": _safe_get_id(issue.assignee),
        "parent_id": _safe_get_id(issue.parent),
        "story_points": issue.story_points,
        "estimated_hours": issue.estimated_hours,
        "time_spent_hours": issue.time_spent_hours,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }


class BoardsRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/boards", tags=["boards"])
        self._setup_routes()

    def _setup_routes(self):
        deps = [Depends(security), Depends(get_current_user)]
        self.router.add_api_route(
            "/", self.get_project_board, methods=["GET"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        self.router.add_api_route(
            "/backlog/{project_id}", self.get_backlog_board, methods=["GET"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        self.router.add_api_route(
            "/sprint/{sprint_id}", self.get_sprint_board, methods=["GET"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        # COLUMN MANAGEMENT APIs
        self.router.add_api_route(
            "/{project_id}/columns", self.get_columns, methods=["GET"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        self.router.add_api_route(
            "/{project_id}/columns", self.add_column, methods=["POST"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        self.router.add_api_route(
            "/{project_id}/columns/{column_position}", self.update_column, methods=["PUT"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        self.router.add_api_route(
            "/{project_id}/columns/{column_position}", self.delete_column, methods=["DELETE"],
            dependencies=deps, response_model=Dict[str, Any]
        )
        self.router.add_api_route(
            "/{project_id}/columns/reorder", self.reorder_columns, methods=["PATCH"],
            dependencies=deps, response_model=Dict[str, Any]
        )

    # -----------------------------------------------------
    # GET ALL COLUMNS
    # -----------------------------------------------------
    async def get_columns(
        self,
        project_id: str,
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:
        
        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to project")

        board = await Board.find_one({"project_id": project_id})
        if not board:
            raise HTTPException(status_code=404, detail="Board not found for this project")

        columns_data = []
        for col in board.columns:
            columns_data.append({
                "name": col.name,
                "status": col.status,
                "position": col.position,
                "color": col.color
            })

        return {
            "columns": columns_data,
            "total_columns": len(columns_data)
        }

    # -----------------------------------------------------
    # ADD COLUMN TO BOARD
    # -----------------------------------------------------
    async def add_column(
        self,
        project_id: str,
        column_data: ColumnCreate,
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:
        
        if not await PermissionService.can_edit_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to edit project")

        board = await Board.find_one({"project_id": project_id})
        if not board:
            raise HTTPException(status_code=404, detail="Board not found for this project")

        # Check if column with same status already exists
        existing_status = any(col.status == column_data.status for col in board.columns)
        if existing_status:
            raise HTTPException(status_code=400, detail=f"Column with status '{column_data.status}' already exists")

        # Check if position is already taken
        existing_position = any(col.position == column_data.position for col in board.columns)
        if existing_position:
            raise HTTPException(status_code=400, detail=f"Position {column_data.position} is already occupied")

        # Create new column
        new_column = BoardColumn(
            name=column_data.name,
            status=column_data.status,
            position=column_data.position,
            color=column_data.color
        )

        # Add to board columns
        board.columns.append(new_column)
        
        # Sort columns by position
        board.columns.sort(key=lambda x: x.position)
        
        await board.save()

        return {
            "message": "Column added successfully",
            "column": {
                "name": new_column.name,
                "status": new_column.status,
                "position": new_column.position,
                "color": new_column.color
            },
            "total_columns": len(board.columns)
        }

    # -----------------------------------------------------
    # UPDATE COLUMN
    # -----------------------------------------------------
    async def update_column(
        self,
        project_id: str,
        column_position: int,
        column_data: ColumnUpdate,
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:
        
        if not await PermissionService.can_edit_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to edit project")

        board = await Board.find_one({"project_id": project_id})
        if not board:
            raise HTTPException(status_code=404, detail="Board not found for this project")

        # Find column by position
        column_index = None
        for i, col in enumerate(board.columns):
            if col.position == column_position:
                column_index = i
                break

        if column_index is None:
            raise HTTPException(status_code=404, detail=f"Column with position {column_position} not found")

        # Update column fields
        column = board.columns[column_index]
        
        if column_data.name is not None:
            column.name = column_data.name
        if column_data.status is not None:
            # Check if new status conflicts with existing columns
            if column_data.status != column.status:
                existing_status = any(col.status == column_data.status for j, col in enumerate(board.columns) if j != column_index)
                if existing_status:
                    raise HTTPException(status_code=400, detail=f"Column with status '{column_data.status}' already exists")
            column.status = column_data.status
        if column_data.position is not None:
            # Check if new position conflicts with existing columns
            if column_data.position != column.position:
                existing_position = any(col.position == column_data.position for j, col in enumerate(board.columns) if j != column_index)
                if existing_position:
                    raise HTTPException(status_code=400, detail=f"Position {column_data.position} is already occupied")
            column.position = column_data.position
        if column_data.color is not None:
            column.color = column_data.color

        # Sort columns by position after update
        board.columns.sort(key=lambda x: x.position)
        
        await board.save()

        return {
            "message": "Column updated successfully",
            "column": {
                "name": column.name,
                "status": column.status,
                "position": column.position,
                "color": column.color
            }
        }

    # -----------------------------------------------------
    # DELETE COLUMN
    # -----------------------------------------------------
    async def delete_column(
        self,
        project_id: str,
        column_position: int,
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:
        
        if not await PermissionService.can_edit_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to edit project")

        board = await Board.find_one({"project_id": project_id})
        if not board:
            raise HTTPException(status_code=404, detail="Board not found for this project")

        # Find column by position
        column_index = None
        for i, col in enumerate(board.columns):
            if col.position == column_position:
                column_index = i
                break

        if column_index is None:
            raise HTTPException(status_code=404, detail=f"Column with position {column_position} not found")

        # Remove column
        removed_column = board.columns.pop(column_index)
        
        await board.save()

        return {
            "message": "Column deleted successfully",
            "deleted_column": {
                "name": removed_column.name,
                "status": removed_column.status,
                "position": removed_column.position
            },
            "remaining_columns": len(board.columns)
        }

    # -----------------------------------------------------
    # REORDER COLUMNS
    # -----------------------------------------------------
    async def reorder_columns(
        self,
        project_id: str,
        reorder_data: Dict[str, Any],
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:
        
        if not await PermissionService.can_edit_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access to edit project")

        board = await Board.find_one({"project_id": project_id})
        if not board:
            raise HTTPException(status_code=404, detail="Board not found for this project")

        new_order = reorder_data.get("new_order")
        if not new_order or not isinstance(new_order, list):
            raise HTTPException(status_code=400, detail="new_order array is required")

        if len(new_order) != len(board.columns):
            raise HTTPException(status_code=400, detail="New order must include all columns")

        # Create mapping of old position to column
        column_map = {col.position: col for col in board.columns}
        
        # Update positions
        new_columns = []
        for new_position, old_position in enumerate(new_order):
            if old_position not in column_map:
                raise HTTPException(status_code=400, detail=f"Invalid column position: {old_position}")
            
            column = column_map[old_position]
            column.position = new_position
            new_columns.append(column)

        board.columns = new_columns
        await board.save()

        return {
            "message": "Columns reordered successfully",
            "new_order": [col.position for col in board.columns]
        }

    # -----------------------------------------------------
    # PROJECT BOARD
    # -----------------------------------------------------
    async def get_project_board(
        self,
        project_id: str = Query(...),
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:

        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to project")

        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        # FIXED: Use proper Beanie query syntax
        issues = await Issue.find(
            Issue.project.id == PydanticObjectId(project_id),
            Issue.location == "board"
        ).to_list()

        return await self._build_board_payload(
            board_name=f"{project.name} — Board",
            project_id=project_id,
            sprint_meta=None,
            issues=issues
        )

    # -----------------------------------------------------
    # BACKLOG BOARD
    # -----------------------------------------------------
    async def get_backlog_board(
        self,
        project_id: str,
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:

        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to project")

        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        # FIXED: Use proper Beanie query syntax
        issues = await Issue.find(
            Issue.project.id == PydanticObjectId(project_id),
            Issue.sprint == None,
            Issue.location == "backlog"
        ).to_list()

        return await self._build_board_payload(
            board_name=f"{project.name} — Backlog",
            project_id=project_id,
            sprint_meta=None,
            issues=issues
        )

    # -----------------------------------------------------
    # SPRINT BOARD
    # -----------------------------------------------------
    async def get_sprint_board(
        self,
        sprint_id: str,
        current_user: User = Depends(get_current_user)
    ) -> Dict[str, Any]:

        sprint = await Sprint.get(sprint_id)
        if not sprint:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sprint not found")

        # FIXED: Fetch the project to get its ID properly
        project = await sprint.project.fetch()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        project_id = str(project.id)

        if not await PermissionService.can_view_project(project_id, str(current_user.id)):
            raise HTTPException(status_code=403, detail="No access")

        issues = await Issue.find(Issue.sprint.id == PydanticObjectId(sprint_id)).to_list()

        sprint_meta = {
            "id": str(sprint.id),
            "name": sprint.name,
            "goal": sprint.goal,
            "start_date": sprint.start_date,
            "end_date": sprint.end_date,
        }

        return await self._build_board_payload(
            board_name=f"Sprint — {sprint.name}",
            project_id=project_id,
            sprint_meta=sprint_meta,
            issues=issues
        )

    # -----------------------------------------------------
    # BOARD BUILDER USING DB COLUMNS
    # -----------------------------------------------------
    async def _build_board_payload(
        self,
        board_name: str,
        project_id: str,
        sprint_meta: Optional[Dict[str, Any]],
        issues: List[Issue]
    ) -> Dict[str, Any]:

        # ✅ Load board from DB
        board = await Board.find_one({"project_id": project_id})
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        # ✅ Build columns from DB rows
        columns: Dict[str, Dict[str, Any]] = {}

        for col in board.columns:
            col_id = f"col_{col.position}"
            columns[col_id] = {
                "column_info": {
                    "id": col_id,
                    "name": col.name,
                    "status": col.status,
                    "position": col.position,
                    "color": col.color,
                },
                "issues": []
            }

        # ✅ Sort issues into correct DB column by status
        for issue in issues:
            status = issue.status

            target_col = next(
                (cid for cid, c in columns.items() if c["column_info"]["status"] == status),
                None
            )

            if target_col:
                columns[target_col]["issues"].append(_issue_to_minimal_dict(issue))

        # ✅ Sort issues newest first
        for col in columns.values():
            col["issues"].sort(
                key=lambda x: (x.get("updated_at") or datetime.min),
                reverse=True
            )

        # ✅ Sort columns by position
        sorted_columns = [
            c for _, c in sorted(
                columns.items(),
                key=lambda kv: kv[1]["column_info"]["position"]
            )
        ]

        return {
            "board": {
                "name": board_name,
                "project_id": project_id,
                "columns": sorted_columns
            },
            "sprint": sprint_meta
        }


boards_router = BoardsRouter().router



