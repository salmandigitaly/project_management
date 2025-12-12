import pandas as pd
from typing import Dict, List, Any
from datetime import datetime
from fastapi import HTTPException


class ExcelParser:
    """Parse and validate Excel file for bulk import"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = {
            "projects": [],
            "epics": [],
            "sprints": [],
            "features": [],
            "issues": [],
            "subtasks": []
        }
        self.errors = []
    
    def parse(self) -> Dict[str, Any]:
        """Parse all sheets from Excel file"""
        try:
            # Read all sheets
            excel_file = pd.ExcelFile(self.file_path)
            
            # Parse each sheet
            if "Projects" in excel_file.sheet_names:
                self.data["projects"] = self._parse_projects(
                    pd.read_excel(excel_file, "Projects")
                )
            
            if "Epics" in excel_file.sheet_names:
                self.data["epics"] = self._parse_epics(
                    pd.read_excel(excel_file, "Epics")
                )
            
            if "Sprints" in excel_file.sheet_names:
                self.data["sprints"] = self._parse_sprints(
                    pd.read_excel(excel_file, "Sprints")
                )
            
            if "Features" in excel_file.sheet_names:
                self.data["features"] = self._parse_features(
                    pd.read_excel(excel_file, "Features")
                )
            
            if "Issues" in excel_file.sheet_names:
                self.data["issues"] = self._parse_issues(
                    pd.read_excel(excel_file, "Issues")
                )
            
            if "Subtasks" in excel_file.sheet_names:
                self.data["subtasks"] = self._parse_subtasks(
                    pd.read_excel(excel_file, "Subtasks")
                )
            
            if self.errors:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Validation errors found", "errors": self.errors}
                )
            
            return self.data
        
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=400, detail=f"Error parsing Excel: {str(e)}")
    
    def _parse_projects(self, df: pd.DataFrame) -> List[Dict]:
        """Parse Projects sheet"""
        projects = []
        
        for idx, row in df.iterrows():
            # Skip header and empty rows
            if pd.isna(row.get("key")):
                continue
            
            # Validate required fields
            if pd.isna(row.get("name")):
                self.errors.append(f"Row {idx + 2}: Project name is required")
                continue
            
            project = {
                "key": str(row["key"]).strip().upper(),
                "name": str(row["name"]).strip(),
                "description": str(row.get("description", "")).strip() if not pd.isna(row.get("description")) else None,
                "platform": str(row.get("platform", "")).strip() if not pd.isna(row.get("platform")) else None,
                "start_date": self._parse_date(row.get("start_date")),
                "end_date": self._parse_date(row.get("end_date")),
                "project_lead_email": str(row.get("project_lead_email", "")).strip() if not pd.isna(row.get("project_lead_email")) else None,
            }
            
            projects.append(project)
        
        return projects
    
    def _parse_epics(self, df: pd.DataFrame) -> List[Dict]:
        """Parse Epics sheet"""
        epics = []
        
        for idx, row in df.iterrows():
            if pd.isna(row.get("project_key")):
                continue
            
            if pd.isna(row.get("name")):
                self.errors.append(f"Row {idx + 2}: Epic name is required")
                continue
            
            epic = {
                "project_key": str(row["project_key"]).strip().upper(),
                "name": str(row["name"]).strip(),
                "description": str(row.get("description", "")).strip() if not pd.isna(row.get("description")) else None,
                "start_date": self._parse_date(row.get("start_date")),
                "end_date": self._parse_date(row.get("end_date")),
            }
            
            epics.append(epic)
        
        return epics
    
    def _parse_sprints(self, df: pd.DataFrame) -> List[Dict]:
        """Parse Sprints sheet"""
        sprints = []
        
        for idx, row in df.iterrows():
            if pd.isna(row.get("project_key")):
                continue
            
            if pd.isna(row.get("name")) or pd.isna(row.get("start_date")) or pd.isna(row.get("end_date")):
                self.errors.append(f"Row {idx + 2}: Sprint name, start_date, and end_date are required")
                continue
            
            sprint = {
                "project_key": str(row["project_key"]).strip().upper(),
                "name": str(row["name"]).strip(),
                "goal": str(row.get("goal", "")).strip() if not pd.isna(row.get("goal")) else None,
                "start_date": self._parse_date(row["start_date"]),
                "end_date": self._parse_date(row["end_date"]),
            }
            
            sprints.append(sprint)
        
        return sprints
    
    def _parse_features(self, df: pd.DataFrame) -> List[Dict]:
        """Parse Features sheet"""
        features = []
        
        for idx, row in df.iterrows():
            if pd.isna(row.get("project_key")):
                continue
            
            if pd.isna(row.get("name")):
                self.errors.append(f"Row {idx + 2}: Feature name is required")
                continue
            
            feature = {
                "project_key": str(row["project_key"]).strip().upper(),
                "epic_name": str(row.get("epic_name", "")).strip() if not pd.isna(row.get("epic_name")) else None,
                "name": str(row["name"]).strip(),
                "description": str(row.get("description", "")).strip() if not pd.isna(row.get("description")) else None,
                "priority": str(row.get("priority", "medium")).strip().lower(),
                "status": str(row.get("status", "todo")).strip().lower(),
            }
            
            features.append(feature)
        
        return features
    
    def _parse_issues(self, df: pd.DataFrame) -> List[Dict]:
        """Parse Issues sheet"""
        issues = []
        
        for idx, row in df.iterrows():
            if pd.isna(row.get("project_key")):
                continue
            
            if pd.isna(row.get("name")) or pd.isna(row.get("type")):
                self.errors.append(f"Row {idx + 2}: Issue name and type are required")
                continue
            
            issue = {
                "project_key": str(row["project_key"]).strip().upper(),
                "epic_name": str(row.get("epic_name", "")).strip() if not pd.isna(row.get("epic_name")) else None,
                "feature_name": str(row.get("feature_name", "")).strip() if not pd.isna(row.get("feature_name")) else None,
                "sprint_name": str(row.get("sprint_name", "")).strip() if not pd.isna(row.get("sprint_name")) else None,
                "type": str(row["type"]).strip().lower(),
                "name": str(row["name"]).strip(),
                "description": str(row.get("description", "")).strip() if not pd.isna(row.get("description")) else None,
                "priority": str(row.get("priority", "medium")).strip().lower(),
                "status": str(row.get("status", "todo")).strip().lower(),
                "assignee_email": str(row.get("assignee_email", "")).strip() if not pd.isna(row.get("assignee_email")) else None,
                "story_points": int(row.get("story_points")) if not pd.isna(row.get("story_points")) else None,
                "estimated_hours": float(row.get("estimated_hours")) if not pd.isna(row.get("estimated_hours")) else None,
            }
            
            issues.append(issue)
        
        return issues
    
    def _parse_subtasks(self, df: pd.DataFrame) -> List[Dict]:
        """Parse Subtasks sheet"""
        subtasks = []
        
        for idx, row in df.iterrows():
            if pd.isna(row.get("project_key")):
                continue
            
            if pd.isna(row.get("name")) or pd.isna(row.get("parent_issue_name")):
                self.errors.append(f"Row {idx + 2}: Subtask name and parent_issue_name are required")
                continue
            
            subtask = {
                "project_key": str(row["project_key"]).strip().upper(),
                "parent_issue_name": str(row["parent_issue_name"]).strip(),
                "name": str(row["name"]).strip(),
                "description": str(row.get("description", "")).strip() if not pd.isna(row.get("description")) else None,
                "priority": str(row.get("priority", "medium")).strip().lower(),
                "status": str(row.get("status", "todo")).strip().lower(),
                "assignee_email": str(row.get("assignee_email", "")).strip() if not pd.isna(row.get("assignee_email")) else None,
                "estimated_hours": float(row.get("estimated_hours")) if not pd.isna(row.get("estimated_hours")) else None,
            }
            
            subtasks.append(subtask)
        
        return subtasks
    
    def _parse_date(self, value) -> datetime:
        """Parse date from various formats"""
        if pd.isna(value):
            return None
        
        if isinstance(value, datetime):
            return value
        
        try:
            return pd.to_datetime(value)
        except:
            return None
