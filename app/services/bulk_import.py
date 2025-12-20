from typing import Dict, List
from app.models.workitems import Project, Epic, Sprint, Issue, Feature, Board, BoardColumn, Backlog
from app.models.users import User
from beanie import PydanticObjectId


class BulkImportService:
    """Service to handle bulk import of data"""
    
    def __init__(self, current_user: User):
        self.current_user = current_user
        self.created_projects = {}  # key -> Project
        self.created_epics = {}     # (project_key, epic_name) -> Epic
        self.created_features = {}  # (project_key, feature_name) -> Feature
        self.created_sprints = {}   # (project_key, sprint_name) -> Sprint
        self.created_issues = {}    # (project_key, issue_name) -> Issue
        self.created_subtasks = []
        self.errors = []
    
    async def import_data(self, data: Dict) -> Dict:
        """Import all data from parsed Excel"""
        
        # Step 1: Create Projects
        for project_data in data.get("projects", []):
            await self._create_project(project_data)
        
        # Step 2: Create Epics
        for epic_data in data.get("epics", []):
            await self._create_epic(epic_data)
        
        # Step 3: Create Features
        for feature_data in data.get("features", []):
            await self._create_feature(feature_data)
        
        # Step 4: Create Sprints
        for sprint_data in data.get("sprints", []):
            await self._create_sprint(sprint_data)
        
        # Step 5: Create Issues
        for issue_data in data.get("issues", []):
            await self._create_issue(issue_data)
        
        # Step 6: Create Subtasks
        for subtask_data in data.get("subtasks", []):
            await self._create_subtask(subtask_data)
        
        return {
            "projects_created": len(self.created_projects),
            "epics_created": len(self.created_epics),
            "features_created": len(self.created_features),
            "sprints_created": len(self.created_sprints),
            "issues_created": len(self.created_issues),
            "subtasks_created": len(self.created_subtasks),
            "errors": self.errors
        }
    
    async def _create_project(self, data: Dict):
        """Create a single project"""
        try:
            # Check if project already exists
            project = await Project.find_one(Project.key == data["key"])
            
            if not project:
                # Create new project
                # Get project lead
                project_lead = self.current_user
                if data.get("project_lead_email"):
                    lead = await User.find_one(User.email == data["project_lead_email"])
                    if lead:
                        project_lead = lead
                
                project = Project(
                    key=data["key"],
                    name=data["name"],
                    description=data.get("description"),
                    platform=data.get("platform", "").lower() if data.get("platform") else None,
                    start_date=data.get("start_date"),
                    end_date=data.get("end_date"),
                    project_lead=project_lead,
                    created_by=self.current_user,
                    members={}
                )
                await project.insert()
            
            # Create default Board and Backlog for the project (Check even if project exists)
            pid = str(project.id)
            
            # Create backlog
            try:
                existing_backlog = await Backlog.find_one({"project_id": pid})
                if not existing_backlog:
                    await Backlog(project_id=pid, items=[]).insert()
            except Exception as e:
                self.errors.append(f"Error creating backlog for project {data['key']}: {str(e)}")
            
            # Create board with default columns
            try:
                existing_board = await Board.find_one({"project_id": pid})
                if not existing_board:
                    board = Board(
                        name="Project Board",
                        project_id=pid,
                        columns=[
                            BoardColumn(name="To Do", status="todo", position=1, color="#FF6B6B"),
                            BoardColumn(name="In Progress", status="in_progress", position=2, color="#4ECDC4"),
                            BoardColumn(name="In Review", status="in_review", position=3, color="#45B7D1"),
                            BoardColumn(name="Done", status="done", position=4, color="#96CEB4"),
                        ],
                        visible_to_roles=[],
                    )
                    await board.insert()
            except Exception as e:
                self.errors.append(f"Error creating board for project {data['key']}: {str(e)}")
            
            self.created_projects[data["key"]] = project
            
        except Exception as e:
            self.errors.append(f"Error creating project {data['key']}: {str(e)}")
    
    async def _create_epic(self, data: Dict):
        """Create a single epic"""
        try:
            project = self.created_projects.get(data["project_key"])
            if not project:
                self.errors.append(f"Project {data['project_key']} not found for epic {data['name']}")
                return
            
            epic = Epic(
                name=data["name"],
                description=data.get("description"),
                project=project,
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                created_by=self.current_user
            )
            
            await epic.insert()
            self.created_epics[(data["project_key"], data["name"])] = epic
            
        except Exception as e:
            self.errors.append(f"Error creating epic {data['name']}: {str(e)}")
    
    async def _create_feature(self, data: Dict):
        """Create a single feature"""
        try:
            project = self.created_projects.get(data["project_key"])
            if not project:
                self.errors.append(f"Project {data['project_key']} not found for feature {data['name']}")
                return
            
            # Get epic if specified
            epic_id = None
            if data.get("epic_name"):
                epic = self.created_epics.get((data["project_key"], data["epic_name"]))
                if epic:
                    epic_id = epic.id
            
            feature = Feature(
                name=data["name"],
                description=data.get("description"),
                project_id=project.id,
                epic_id=epic_id,
                priority=data.get("priority", "medium"),
                status=data.get("status", "todo"),
                created_by=self.current_user.id
            )
            
            await feature.insert()
            self.created_features[(data["project_key"], data["name"])] = feature
            
        except Exception as e:
            self.errors.append(f"Error creating feature {data['name']}: {str(e)}")

    
    async def _create_sprint(self, data: Dict):
        """Create a single sprint"""
        try:
            project = self.created_projects.get(data["project_key"])
            if not project:
                self.errors.append(f"Project {data['project_key']} not found for sprint {data['name']}")
                return
            
            sprint = Sprint(
                name=data["name"],
                project=project,
                goal=data.get("goal"),
                start_date=data["start_date"],
                end_date=data["end_date"],
                created_by=self.current_user
            )
            
            await sprint.insert()
            self.created_sprints[(data["project_key"], data["name"])] = sprint
            
        except Exception as e:
            self.errors.append(f"Error creating sprint {data['name']}: {str(e)}")
    
    async def _create_issue(self, data: Dict):
        """Create a single issue"""
        try:
            project = self.created_projects.get(data["project_key"])
            if not project:
                self.errors.append(f"Project {data['project_key']} not found for issue {data['name']}")
                return
            
            # Get epic if specified
            epic = None
            if data.get("epic_name"):
                epic = self.created_epics.get((data["project_key"], data["epic_name"]))
            
            # Get feature if specified
            feature = None
            if data.get("feature_name"):
                feature = self.created_features.get((data["project_key"], data["feature_name"]))
            
            # Get sprint if specified
            sprint = None
            if data.get("sprint_name"):
                sprint = self.created_sprints.get((data["project_key"], data["sprint_name"]))
            
            # Get assignee if specified
            assignee = None
            if data.get("assignee_email"):
                assignee = await User.find_one(User.email == data["assignee_email"])
            
            issue = Issue(
                project=project,
                epic=epic,
                sprint=sprint,
                feature_id=feature.id if feature else None,
                type=data["type"],
                name=data["name"],
                description=data.get("description"),
                priority=data.get("priority", "medium"),
                status=data.get("status", "todo"),
                assignee=assignee,
                story_points=data.get("story_points"),
                estimated_hours=data.get("estimated_hours"),
                created_by=self.current_user,
                location="backlog" if not sprint else "sprint"
            )
            
            await issue.insert()
            self.created_issues[(data["project_key"], data["name"])] = issue
            
        except Exception as e:
            self.errors.append(f"Error creating issue {data['name']}: {str(e)}")
    
    async def _create_subtask(self, data: Dict):
        """Create a single subtask"""
        try:
            project = self.created_projects.get(data["project_key"])
            if not project:
                self.errors.append(f"Project {data['project_key']} not found for subtask {data['name']}")
                return
            
            # Find parent issue
            parent_issue = self.created_issues.get((data["project_key"], data["parent_issue_name"]))
            if not parent_issue:
                self.errors.append(f"Parent issue {data['parent_issue_name']} not found for subtask {data['name']}")
                return
            
            # Get assignee if specified
            assignee = None
            if data.get("assignee_email"):
                assignee = await User.find_one(User.email == data["assignee_email"])
            
            subtask = Issue(
                project=project,
                type="subtask",
                name=data["name"],
                description=data.get("description"),
                priority=data.get("priority", "medium"),
                status=data.get("status", "todo"),
                assignee=assignee,
                estimated_hours=data.get("estimated_hours"),
                created_by=self.current_user,
                parent=parent_issue,
                location="backlog"
            )
            
            await subtask.insert()
            self.created_subtasks.append(subtask)
            
        except Exception as e:
            self.errors.append(f"Error creating subtask {data['name']}: {str(e)}")
