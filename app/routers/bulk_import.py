from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
import os
import tempfile
from io import BytesIO

from app.routers.auth import get_current_user
from app.models.users import User
from app.utils.excel_template import generate_excel_template
from app.utils.excel_parser import ExcelParser
from app.services.bulk_import import BulkImportService

security = HTTPBearer()
router = APIRouter(prefix="/bulk-import", tags=["bulk-import"])


@router.get("/template")
async def download_template(
    current_user: User = Depends(get_current_user)
):
    """Download Excel template for bulk import"""
    
    wb = generate_excel_template()
    
    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bulk_import_template.xlsx"}
    )


@router.post("/upload")
async def upload_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload Excel file for bulk import"""
    
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are allowed")
    
    # Save uploaded file temporarily
    tmp_path = None
    try:
        # Read file content
        content = await file.read()
        
        # Create temp file and write content
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.xlsx') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        # Parse Excel file
        parser = ExcelParser(tmp_path)
        data = parser.parse()
        
        # Import data
        import_service = BulkImportService(current_user)
        result = await import_service.import_data(data)
        
        return {
            "message": "Import completed",
            "summary": result
        }
    
    finally:
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except PermissionError:
                # File might still be locked, ignore
                pass
