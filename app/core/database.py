from beanie import init_beanie, Document
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import MONGO_URI, DB_NAME, settings

# import only model classes (some may not be Document subclasses)
from app.models.users import User
from app.models.workitems import Project, Epic, Issue, Sprint, Feature, Board, Backlog, Comment, TimeEntry, LinkedWorkItem  # adjust to your model list
from app.models.employee import Attendance, LeaveRequest

async def init_db():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client.get_default_database()

    # list candidate models
    candidate_models = [
        User,
        Project,
        Issue,
        Epic,
        Board,
        Backlog,
        Sprint,
        Feature,
        TimeEntry,
        Comment,
        Attendance,
        LeaveRequest,
        LinkedWorkItem,
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