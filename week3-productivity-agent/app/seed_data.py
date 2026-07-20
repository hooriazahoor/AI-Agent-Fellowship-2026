"""
Sample data seeding so the deployed app is usable immediately during
onsite evaluation without manual setup (Deployment Requirements).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from app.database import repository as repo


def seed_sample_data() -> dict:
    existing = repo.list_tasks()
    if existing:
        return {"tasks": 0, "notes": 0, "note": "Data already present - seed skipped."}

    now = datetime.utcnow()
    tasks = [
        dict(title="Prepare Week 3 internship submission", description="Consolidate assignments and demo script.",
             priority="High", due_date=now + timedelta(days=1), tags=["internship"]),
        dict(title="Fix ChromaDB indexing bug", description="RAG pipeline returns stale embeddings on Windows.",
             priority="Critical", due_date=now - timedelta(hours=5), tags=["bug", "rag"]),
        dict(title="Write FYP literature review section", description="Roman Urdu mental health datasets.",
             priority="Medium", due_date=now + timedelta(days=5), tags=["fyp"]),
        dict(title="Review Maryam's PHQ-9 integration PR", description="", priority="Medium",
             due_date=now + timedelta(days=2), tags=["fyp", "review"]),
        dict(title="Update portfolio with Week 2 project", description="Add screenshots + repo link.",
             priority="Low", due_date=now + timedelta(days=7), tags=["portfolio"]),
        dict(title="Book review call with Sir Arham", description="", priority="High",
             due_date=now + timedelta(hours=20), tags=["meeting"]),
    ]
    for t in tasks:
        repo.create_task(**t)

    notes = [
        dict(title="Marketing campaign kickoff", content="Discussed Q3 marketing campaign timeline, "
             "budget approval pending, and social media content calendar.", category="meetings",
             tags=["marketing", "campaign"]),
        dict(title="RAG debugging notes", content="sentence-transformers embeddings mismatch traced to "
             "encoding differences between Windows path separators.", category="technical", tags=["rag", "bug"]),
        dict(title="Weekly standup - internship", content="Team discussed crisis detection module accuracy "
             "and LIME/SHAP explainability integration for Week 3.", category="internship", tags=["standup"]),
    ]
    for n in notes:
        repo.create_note(**n)

    return {"tasks": len(tasks), "notes": len(notes)}
