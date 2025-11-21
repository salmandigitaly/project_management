from beanie import init_beanie, Document
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import MONGO_URI, DB_NAME

# import only model classes (some may not be Document subclasses)
from app.models.users import User
from app.models.workitems import Project, Issue, Epic, Board, Backlog, Sprint  # exclude BoardColumn if it's not a Document
from app.models.employee import Attendance, LeaveRequest

async def init_db():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    # list candidate models
    candidate_models = [
        User,
        Project,
        Issue,
        Epic,
        Board,
        Backlog,
        Sprint,
        Attendance,
        LeaveRequest,
        # add additional Document classes here
    ]

    # keep only classes that are subclasses of beanie.Document
    document_models = []
    for m in candidate_models:
        try:
            if issubclass(m, Document):
                document_models.append(m)
        except Exception:
            # skip non-class / not a Document
            continue

    await init_beanie(database=db, document_models=document_models)
    print("✅ Database initialized successfully!")