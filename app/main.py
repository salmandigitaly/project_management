from app.core.config import settings
print("✅ Loaded Mongo URL:", settings.MONGODB_URL)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.database import init_db
from app.routers.boards import *
# Routers that actually exist now
from app.routers.auth import auth_router, get_current_user
from app.routers.users import users_router
from app.routers.workitems import (
    epics_router, comments_router,
    links_router, features_router
)
# Import new dedicated time tracking router
from app.routers.time_tracking import router as time_tracking_router
# prefer explicit sprint router from dedicated module (avoid overriding it below)
from app.routers.sprint import sprints_router
from app.routers.issues import issues_router
from app.routers.projects import *
from app.routers.bulk_import import router as bulk_import_router
from app.routers.reports import router as reports_router
from app.routers.recycle_bin import router as recycle_bin_router
from app.routers.global_pm import router as global_pm_router
# add these imports
from app.services.permission import PermissionService
try:
    # prefer explicit employees_router if present
    from app.routers.employees import employees_router
except Exception:
    try:
        # fallback if module exports `router` instead
        from app.routers.employees import router as employees_router
    except Exception:
        employees_router = None

app = FastAPI(title="Project Management(HRMS)")  # or existing app

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://pmtooldev.digitaly.live",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAPI with bearer applied to all except /auth/*
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="HRMS API with JWT Authentication",
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    for path, methods in openapi_schema.get("paths", {}).items():
        if not path.startswith(f"{settings.API_V1_STR}/auth"):
            for method in methods.values():
                method["security"] = [{"Bearer": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# include only working routers
api_prefix = settings.API_V1_STR
app.include_router(auth_router, prefix=api_prefix)
app.include_router(users_router, prefix=api_prefix)
app.include_router(epics_router, prefix=api_prefix)
app.include_router(issues_router, prefix=api_prefix)
app.include_router(sprints_router, prefix=api_prefix)
app.include_router(comments_router, prefix=api_prefix)
app.include_router(links_router, prefix=api_prefix)
app.include_router(time_tracking_router, prefix=api_prefix)

# include features router so Swagger shows a separate "features" section
app.include_router(features_router, prefix=api_prefix)

app.include_router(projects_router,prefix=api_prefix)
app.include_router(boards_router,prefix=api_prefix)
app.include_router(reports_router, prefix=api_prefix)
app.include_router(bulk_import_router, prefix=api_prefix)
app.include_router(recycle_bin_router, prefix=api_prefix)
if employees_router:
    app.include_router(employees_router, prefix=api_prefix)
else:
    print("⚠️ employees router not found — /employees endpoints will not be shown in /docs")

app.include_router(global_pm_router, prefix=api_prefix)

# if employees_router is None, the app will skip including it (avoids NameError)

@app.on_event("startup")
async def startup_event():
    await init_db()

@app.get("/")
async def root():
    return {"message": "HRMS API is up and running. Ready to serve requests ⚙️", "version": settings.VERSION}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# temporary debug endpoint — remove when done
# @app.get("/debug/can_view/{project_id}")
# async def debug_can_view(project_id: str, current_user = Depends(get_current_user)):
#     return {
#         "user_id": str(getattr(current_user, "id", None)),
#         "role": getattr(current_user, "role", None),
#         "can_view": await PermissionService.can_view_project(project_id, str(getattr(current_user, "id", None)))
#     }

# NOTE: removed inline DB update that ran at import time.
# If you need to add a user to a project for testing, run a separate script or use a protected endpoint.
