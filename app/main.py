# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware  # ADD THIS IMPORT
# from app.core.config import settings
# from app.core.database import init_db

# # Import routers
# from app.routers.projects import projects_router
# from app.routers.epics import epics_router
# from app.routers.stories import stories_router
# from app.routers.tasks import tasks_router
# from app.routers.subtasks import subtasks_router
# from app.routers.sprints import sprints_router
# from app.routers.boards import boards_router
# from app.routers.comments import comments_router
# from app.routers.activity import activity_router
# from app.routers.attachments import attachments_router
# from app.routers.links import links_router
# from app.routers.search import search_router
# from app.routers.auth import auth_router
# from app.routers.users import users_router
# from app.routers.feature import features_router
# from app.routers.workflows import workflows_router  # NEW IMPORT
# from app.routers.custom_fields import custom_fields_router
# from app.routers.time_tracking import time_tracking_router
# from app.routers.voting import voting_router
# from app.routers.notifications import notifications_router
# from app.routers.reports import reports_router
# from app.routers.labels import router as labels_router
# # Add OpenAPI security configuration
# from app.routers.components import components_router
# from app.routers.components import components_router
# from app.routers.versions import versions_router
# from fastapi.openapi.utils import get_openapi
# from app.routers.bugs import bugs_router
# from app.routers.backlog import backlog_router
# app = FastAPI(
#     title=settings.PROJECT_NAME,
#     version=settings.VERSION,
#     openapi_url=f"{settings.API_V1_STR}/openapi.json"
# )

# # ADD CORS MIDDLEWARE (ONLY THIS SECTION ADDED)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # Allows all origins
#     allow_credentials=True,
#     allow_methods=["*"],  # Allows all methods
#     allow_headers=["*"],  # Allows all headers
# )

# # Custom OpenAPI schema with JWT security
# def custom_openapi():
#     if app.openapi_schema:
#         return app.openapi_schema
    
#     openapi_schema = get_openapi(
#         title=settings.PROJECT_NAME,
#         version=settings.VERSION,
#         description="JIRA Clone API with JWT Authentication",
#         routes=app.routes,
#     )
    
#     # Add JWT security scheme
#     openapi_schema["components"]["securitySchemes"] = {
#         "Bearer": {
#             "type": "http",
#             "scheme": "bearer",
#             "bearerFormat": "JWT"
#         }
#     }
    
#     # Add security to all paths (except auth endpoints)
#     for path, methods in openapi_schema["paths"].items():
#         if not path.startswith(f"{settings.API_V1_STR}/auth"):
#             for method in methods.values():
#                 method["security"] = [{"Bearer": []}]
    
#     app.openapi_schema = openapi_schema
#     return app.openapi_schema

# app.openapi = custom_openapi

# # Include routers
# app.include_router(auth_router, prefix=settings.API_V1_STR)
# app.include_router(users_router, prefix=settings.API_V1_STR)
# app.include_router(projects_router, prefix=settings.API_V1_STR)
# app.include_router(epics_router, prefix=settings.API_V1_STR)
# app.include_router(stories_router, prefix=settings.API_V1_STR)
# app.include_router(tasks_router, prefix=settings.API_V1_STR)
# app.include_router(subtasks_router, prefix=settings.API_V1_STR)
# app.include_router(sprints_router, prefix=settings.API_V1_STR)
# app.include_router(boards_router, prefix=settings.API_V1_STR)
# app.include_router(comments_router, prefix=settings.API_V1_STR)
# app.include_router(activity_router, prefix=settings.API_V1_STR)
# app.include_router(attachments_router, prefix=settings.API_V1_STR)
# app.include_router(links_router, prefix=settings.API_V1_STR)
# app.include_router(search_router, prefix=settings.API_V1_STR)
# app.include_router(features_router, prefix=settings.API_V1_STR, tags=["features"])  # NEW ROUTER INCLUDED
# app.include_router(workflows_router, prefix=settings.API_V1_STR)
# app.include_router(custom_fields_router, prefix=settings.API_V1_STR)
# app.include_router(bugs_router, prefix=settings.API_V1_STR, tags=["bugs"])
# app.include_router(time_tracking_router, prefix=settings.API_V1_STR)
# app.include_router(voting_router, prefix=settings.API_V1_STR)
# app.include_router(notifications_router, prefix=settings.API_V1_STR)
# app.include_router(reports_router, prefix=settings.API_V1_STR)
# app.include_router(labels_router)
# app.include_router(components_router, prefix=settings.API_V1_STR)
# app.include_router(components_router, prefix=settings.API_V1_STR)
# app.include_router(versions_router, prefix=settings.API_V1_STR)
# app.include_router(backlog_router, prefix=settings.API_V1_STR)
# @app.on_event("startup")
# async def startup_event():
#     await init_db()

# @app.get("/")
# async def root():
#     return {"message": "JIRA Clone API", "version": settings.VERSION}

# @app.get("/health")
# async def health_check():
#     return {"status": "healthy"}







from app.core.config import settings
print("✅ Loaded Mongo URL:", settings.MONGODB_URL)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.config import settings
from app.core.database import init_db
from app.routers.boards import *
# Routers that actually exist now
from app.routers.auth import auth_router
from app.routers.users import users_router
from app.routers.workitems import (
    epics_router,
    issues_router,
    sprints_router,
    comments_router,
    links_router,
    time_router,
)
from app.routers.projects import *
from app.routers.employees import router as employees_router
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        description="JIRA Clone API with JWT Authentication",
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
app.include_router(time_router, prefix=api_prefix)
app.include_router(projects_router,prefix=api_prefix)
app.include_router(boards_router,prefix=api_prefix)
app.include_router(employees_router, prefix="/api/v1")
@app.on_event("startup")
async def startup_event():
    await init_db()

@app.get("/")
async def root():
    return {"message": "JIRA Clone API", "version": settings.VERSION}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
