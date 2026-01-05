from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, UploadFile, File
from fastapi.responses import FileResponse
from beanie import PydanticObjectId
from app.routers.auth import get_current_user
from app.models.users import User
from app.models.workitems import Project, WikiPage, WikiAsset
from app.schemas.project_management import WikiPageCreate, WikiPageUpdate, WikiPageOut, WikiAssetOut

class WikiRouter:
    def __init__(self):
        self.router = APIRouter(prefix="/projects", tags=["wiki"])
        self.setup_routes()

    def setup_routes(self):
        self.router.add_api_route("/{project_id}/wiki", self.create_page, methods=["POST"], response_model=WikiPageOut)
        self.router.add_api_route("/{project_id}/wiki", self.list_pages, methods=["GET"], response_model=List[Dict[str, Any]])
        self.router.add_api_route("/{project_id}/wiki/{page_id}", self.get_page, methods=["GET"], response_model=WikiPageOut)
        self.router.add_api_route("/{project_id}/wiki/{page_id}", self.update_page, methods=["PUT"], response_model=WikiPageOut)
        self.router.add_api_route("/{project_id}/wiki/{page_id}", self.delete_page, methods=["DELETE"])
        self.router.add_api_route("/{project_id}/wiki/assets/upload", self.upload_asset, methods=["POST"], response_model=WikiAssetOut)
        self.router.add_api_route("/{project_id}/wiki/assets/{asset_id}", self.get_asset, methods=["GET"])

    async def create_page(
        self,
        project_id: str,
        page_data: WikiPageCreate,
        current_user: User = Depends(get_current_user)
    ):
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Basic permission check
        if str(current_user.id) not in project.members and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to create wiki pages in this project")

        page = WikiPage(
            project=project,
            title=page_data.title,
            content=page_data.content,
            parent_id=page_data.parent_id,
            created_by=current_user,
            updated_by=current_user
        )
        await page.insert()
        return await self._doc_to_out(page)

    async def list_pages(
        self,
        project_id: str,
        current_user: User = Depends(get_current_user)
    ):
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        pages = await WikiPage.find(WikiPage.project.id == project.id, WikiPage.is_deleted == False).to_list()
        
        # Build hierarchy tree
        return self._build_tree(pages)

    async def get_page(
        self,
        project_id: str,
        page_id: str,
        current_user: User = Depends(get_current_user)
    ):
        page = await WikiPage.get(page_id)
        if not page or self._link_id(page.project) != project_id or page.is_deleted:
            raise HTTPException(status_code=404, detail="Wiki page not found")
        
        return await self._doc_to_out(page)

    async def update_page(
        self,
        project_id: str,
        page_id: str,
        page_data: WikiPageUpdate,
        current_user: User = Depends(get_current_user)
    ):
        page = await WikiPage.get(page_id)
        if not page or self._link_id(page.project) != project_id or page.is_deleted:
            raise HTTPException(status_code=404, detail="Wiki page not found")

        if page_data.title is not None:
            page.title = page_data.title
        if page_data.content is not None:
            page.content = page_data.content
        if page_data.parent_id is not None:
            page.parent_id = page_data.parent_id

        page.updated_at = datetime.utcnow()
        page.updated_by = current_user
        await page.save()
        return await self._doc_to_out(page)

    async def delete_page(
        self,
        project_id: str,
        page_id: str,
        current_user: User = Depends(get_current_user)
    ):
        page = await WikiPage.get(page_id)
        if not page or self._link_id(page.project) != project_id:
            raise HTTPException(status_code=404, detail="Wiki page not found")

        # Soft delete
        page.is_deleted = True
        await page.save()
        return {"id": page_id, "status": "deleted"}

    async def upload_asset(
        self,
        project_id: str,
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user)
    ):
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Ensure directory exists
        upload_dir = os.path.join("uploads", "wiki_assets", project_id)
        os.makedirs(upload_dir, exist_ok=True)

        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        asset = WikiAsset(
            project=project,
            filename=filename,
            original_name=file.filename,
            file_path=file_path,
            content_type=file.content_type,
            uploaded_by=current_user
        )
        await asset.insert()
        
        return WikiAssetOut(
            id=str(asset.id),
            project_id=str(project.id),
            filename=asset.filename,
            original_name=asset.original_name,
            content_type=asset.content_type,
            uploaded_by=str(current_user.id),
            created_at=asset.created_at
        )

    async def get_asset(
        self,
        project_id: str,
        asset_id: str,
        current_user: User = Depends(get_current_user)
    ):
        asset = await WikiAsset.get(asset_id)
        if not asset or self._link_id(asset.project) != project_id:
            raise HTTPException(status_code=404, detail="Asset not found")

        if not os.path.exists(asset.file_path):
            raise HTTPException(status_code=404, detail="File not found on disk")

        return FileResponse(asset.file_path, media_type=asset.content_type)

    def _build_tree(self, pages: List[WikiPage], parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        tree = []
        for p in pages:
            p_parent_id = str(p.parent_id) if p.parent_id else None
            if p_parent_id == parent_id:
                node = {
                    "id": str(p.id),
                    "title": p.title,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "children": self._build_tree(pages, str(p.id))
                }
                tree.append(node)
        return tree

    def _link_id(self, link):
        if not link: return None
        if hasattr(link, "id"): return str(link.id)
        if hasattr(link, "ref") and hasattr(link.ref, "id"): return str(link.ref.id)
        return str(link)

    async def _doc_to_out(self, page: WikiPage) -> WikiPageOut:
        return WikiPageOut(
            id=str(page.id),
            project_id=self._link_id(page.project),
            title=page.title,
            content=page.content,
            parent_id=str(page.parent_id) if page.parent_id else None,
            created_by=self._link_id(page.created_by),
            created_at=page.created_at,
            updated_at=page.updated_at,
            is_deleted=page.is_deleted
        )

wiki_router = WikiRouter().router
