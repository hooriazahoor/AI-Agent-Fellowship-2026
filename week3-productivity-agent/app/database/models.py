"""
SQLAlchemy ORM models for the Personal Productivity Agent.

Tables:
    - Task              : user tasks (Requirement 2)
    - Note              : user notes (Requirement 3)
    - PendingApproval   : write actions awaiting human approval (Requirement 7)
    - ExecutionLog      : full agent run logs (Requirement 10)
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Enum as SAEnum, ForeignKey, Integer, Boolean
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Priority(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Status(str, enum.Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class ApprovalStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    NOT_REQUIRED = "Not Required"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: new_id("task"))
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    priority = Column(SAEnum(Priority), default=Priority.MEDIUM, nullable=False)
    status = Column(SAEnum(Status), default=Status.PENDING, nullable=False)
    due_date = Column(DateTime, nullable=True)
    created_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_date = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    tags = Column(String(500), default="")  # comma-separated
    source = Column(String(255), default="user")  # e.g. "user", "meeting_notes", "agent"
    notes = Column(Text, default="")
    estimated_effort_minutes = Column(Integer, nullable=True)

    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value if isinstance(self.priority, Priority) else self.priority,
            "status": self.status.value if isinstance(self.status, Status) else self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_date": self.created_date.isoformat() if self.created_date else None,
            "updated_date": self.updated_date.isoformat() if self.updated_date else None,
            "tags": self.tag_list(),
            "source": self.source,
            "notes": self.notes,
            "estimated_effort_minutes": self.estimated_effort_minutes,
        }


class Note(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=lambda: new_id("note"))
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(120), default="general")
    tags = Column(String(500), default="")
    created_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_date = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "tags": self.tag_list(),
            "created_date": self.created_date.isoformat() if self.created_date else None,
            "updated_date": self.updated_date.isoformat() if self.updated_date else None,
        }


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id = Column(String, primary_key=True, default=lambda: new_id("appr"))
    run_id = Column(String, ForeignKey("execution_logs.id"), nullable=True)
    session_id = Column(String, nullable=False)
    tool_name = Column(String(120), nullable=False)
    tool_args_json = Column(Text, nullable=False)  # JSON string
    proposed_action = Column(Text, nullable=False)
    expected_effect = Column(Text, default="")
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_date = Column(DateTime, nullable=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "tool_args": json.loads(self.tool_args_json or "{}"),
            "proposed_action": self.proposed_action,
            "expected_effect": self.expected_effect,
            "status": self.status.value if isinstance(self.status, ApprovalStatus) else self.status,
            "created_date": self.created_date.isoformat() if self.created_date else None,
        }


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(String, primary_key=True, default=lambda: new_id("run"))
    session_id = Column(String, nullable=False)
    user_request = Column(Text, nullable=False)
    selected_model = Column(String(120), default="")
    tools_called_json = Column(Text, default="[]")     # JSON list of tool names
    tool_arguments_json = Column(Text, default="[]")   # JSON list of arg dicts
    tool_results_json = Column(Text, default="[]")     # JSON list of result summaries
    approval_status = Column(String(50), default="Not Required")
    errors_json = Column(Text, default="[]")
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    total_duration_ms = Column(Integer, nullable=True)
    final_outcome = Column(Text, default="")
    step_count = Column(Integer, default=0)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_request": self.user_request,
            "selected_model": self.selected_model,
            "tools_called": json.loads(self.tools_called_json or "[]"),
            "tool_arguments": json.loads(self.tool_arguments_json or "[]"),
            "tool_results": json.loads(self.tool_results_json or "[]"),
            "approval_status": self.approval_status,
            "errors": json.loads(self.errors_json or "[]"),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration_ms": self.total_duration_ms,
            "final_outcome": self.final_outcome,
            "step_count": self.step_count,
        }