"""
Repository layer: the ONLY place that talks to the database.
Tools and agent logic never touch SQLAlchemy sessions directly -- this keeps
data storage cleanly separated from agent logic (see Code Quality Requirements).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.database.models import (
    Base, Task, Note, PendingApproval, ExecutionLog,
    Priority, Status, ApprovalStatus,
)

_engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(_engine)


@contextmanager
def get_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class DatabaseError(Exception):
    """Raised when a persistence operation fails."""


# ---------------------------------------------------------------------------
# Task repository functions
# ---------------------------------------------------------------------------

def create_task(title, description="", priority="Medium", due_date=None,
                 tags=None, source="user", notes="", estimated_effort_minutes=None) -> dict:
    try:
        with get_session() as db:
            task = Task(
                title=title,
                description=description or "",
                priority=Priority(priority),
                status=Status.PENDING,
                due_date=due_date,
                tags=",".join(tags) if isinstance(tags, list) else (tags or ""),
                source=source,
                notes=notes or "",
                estimated_effort_minutes=estimated_effort_minutes,
            )
            db.add(task)
            db.flush()
            return task.to_dict()
    except Exception as e:
        raise DatabaseError(f"Failed to create task: {e}") from e


def list_tasks(status=None, priority=None, due_before=None, due_after=None, tag=None) -> List[dict]:
    try:
        with get_session() as db:
            q = db.query(Task)
            if status:
                q = q.filter(Task.status == Status(status))
            if priority:
                q = q.filter(Task.priority == Priority(priority))
            if due_before:
                q = q.filter(Task.due_date != None, Task.due_date <= due_before)  # noqa: E711
            if due_after:
                q = q.filter(Task.due_date != None, Task.due_date >= due_after)  # noqa: E711
            results = q.order_by(Task.due_date.is_(None), Task.due_date.asc()).all()
            out = [t.to_dict() for t in results]
            if tag:
                out = [t for t in out if tag.lower() in [x.lower() for x in t["tags"]]]
            return out
    except Exception as e:
        raise DatabaseError(f"Failed to list tasks: {e}") from e


def get_task(task_id: str) -> Optional[dict]:
    with get_session() as db:
        task = db.query(Task).filter(Task.id == task_id).first()
        return task.to_dict() if task else None


def update_task(task_id: str, **changes) -> dict:
    try:
        with get_session() as db:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise DatabaseError(f"Unknown task ID: {task_id}")
            if "title" in changes and changes["title"] is not None:
                task.title = changes["title"]
            if "description" in changes and changes["description"] is not None:
                task.description = changes["description"]
            if "priority" in changes and changes["priority"] is not None:
                task.priority = Priority(changes["priority"])
            if "due_date" in changes and changes["due_date"] is not None:
                task.due_date = changes["due_date"]
            if "status" in changes and changes["status"] is not None:
                task.status = Status(changes["status"])
            if "tags" in changes and changes["tags"] is not None:
                tags = changes["tags"]
                task.tags = ",".join(tags) if isinstance(tags, list) else tags
            task.updated_date = datetime.utcnow()
            db.flush()
            return task.to_dict()
    except DatabaseError:
        raise
    except Exception as e:
        raise DatabaseError(f"Failed to update task: {e}") from e


def complete_task(task_id: str) -> dict:
    try:
        with get_session() as db:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise DatabaseError(f"Unknown task ID: {task_id}")
            task.status = Status.COMPLETED
            task.updated_date = datetime.utcnow()
            db.flush()
            return task.to_dict()
    except DatabaseError:
        raise
    except Exception as e:
        raise DatabaseError(f"Failed to complete task: {e}") from e


def delete_task(task_id: str) -> bool:
    with get_session() as db:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise DatabaseError(f"Unknown task ID: {task_id}")
        db.delete(task)
        return True


def overdue_tasks(reference_time: Optional[datetime] = None) -> List[dict]:
    reference_time = reference_time or datetime.utcnow()
    with get_session() as db:
        q = db.query(Task).filter(
            Task.due_date != None,  # noqa: E711
            Task.due_date < reference_time,
            Task.status.notin_([Status.COMPLETED, Status.CANCELLED]),
        )
        return [t.to_dict() for t in q.all()]


# ---------------------------------------------------------------------------
# Note repository functions
# ---------------------------------------------------------------------------

def create_note(title, content, category="general", tags=None) -> dict:
    try:
        with get_session() as db:
            note = Note(
                title=title,
                content=content,
                category=category or "general",
                tags=",".join(tags) if isinstance(tags, list) else (tags or ""),
            )
            db.add(note)
            db.flush()
            return note.to_dict()
    except Exception as e:
        raise DatabaseError(f"Failed to save note: {e}") from e


def list_notes() -> List[dict]:
    with get_session() as db:
        return [n.to_dict() for n in db.query(Note).order_by(Note.created_date.desc()).all()]


def delete_note(note_id: str) -> bool:
    with get_session() as db:
        note = db.query(Note).filter(Note.id == note_id).first()
        if not note:
            raise DatabaseError(f"Unknown note ID: {note_id}")
        db.delete(note)
        return True


def search_notes(query: str, category: Optional[str] = None,
                  date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> List[dict]:
    """Keyword search with a simple relevance score (token overlap).
    Semantic search can be swapped in later without changing the tool interface."""
    try:
        with get_session() as db:
            q = db.query(Note)
            if category:
                q = q.filter(Note.category == category)
            if date_from:
                q = q.filter(Note.created_date >= date_from)
            if date_to:
                q = q.filter(Note.created_date <= date_to)
            all_notes = q.all()
    except Exception as e:
        raise DatabaseError(f"Failed to search notes: {e}") from e

    query_tokens = set(query.lower().split())
    scored = []
    for n in all_notes:
        haystack = f"{n.title} {n.content} {n.tags}".lower()
        score = sum(1 for tok in query_tokens if tok in haystack)
        if query.lower() in haystack:
            score += 3
        if score > 0:
            d = n.to_dict()
            d["match_score"] = score
            scored.append(d)
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Approval repository functions
# ---------------------------------------------------------------------------

def create_pending_approval(session_id, tool_name, tool_args, proposed_action, expected_effect, run_id=None) -> dict:
    with get_session() as db:
        appr = PendingApproval(
            session_id=session_id,
            run_id=run_id,
            tool_name=tool_name,
            tool_args_json=json.dumps(tool_args),
            proposed_action=proposed_action,
            expected_effect=expected_effect,
            status=ApprovalStatus.PENDING,
        )
        db.add(appr)
        db.flush()
        return appr.to_dict()


def get_pending_approval(approval_id: str) -> Optional[dict]:
    with get_session() as db:
        appr = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
        if not appr:
            return None
        d = appr.to_dict()
        d["tool_args"] = json.loads(appr.tool_args_json)
        return d


def resolve_approval(approval_id: str, approved: bool) -> Optional[dict]:
    with get_session() as db:
        appr = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
        if not appr:
            return None
        appr.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        appr.resolved_date = datetime.utcnow()
        db.flush()
        d = appr.to_dict()
        d["tool_args"] = json.loads(appr.tool_args_json)
        return d


def list_pending_approvals(session_id: str) -> List[dict]:
    with get_session() as db:
        q = db.query(PendingApproval).filter(
            PendingApproval.session_id == session_id,
            PendingApproval.status == ApprovalStatus.PENDING,
        )
        return [a.to_dict() for a in q.all()]


# ---------------------------------------------------------------------------
# Execution log repository functions
# ---------------------------------------------------------------------------

def create_execution_log(session_id, user_request, selected_model="") -> dict:
    with get_session() as db:
        log = ExecutionLog(
            session_id=session_id,
            user_request=user_request,
            selected_model=selected_model,
            start_time=datetime.utcnow(),
        )
        db.add(log)
        db.flush()
        return log.to_dict()


def update_execution_log(run_id: str, **fields) -> Optional[dict]:
    with get_session() as db:
        log = db.query(ExecutionLog).filter(ExecutionLog.id == run_id).first()
        if not log:
            return None
        for key in ("tools_called", "tool_arguments", "tool_results", "errors"):
            if key in fields:
                setattr(log, f"{key}_json", json.dumps(fields.pop(key)))
        for key, val in fields.items():
            if hasattr(log, key):
                setattr(log, key, val)
        db.flush()
        return log.to_dict()


def list_execution_logs(session_id: Optional[str] = None, limit: int = 50) -> List[dict]:
    with get_session() as db:
        q = db.query(ExecutionLog)
        if session_id:
            q = q.filter(ExecutionLog.session_id == session_id)
        q = q.order_by(ExecutionLog.start_time.desc()).limit(limit)
        return [l.to_dict() for l in q.all()]


def get_execution_log(run_id: str) -> Optional[dict]:
    with get_session() as db:
        log = db.query(ExecutionLog).filter(ExecutionLog.id == run_id).first()
        return log.to_dict() if log else None