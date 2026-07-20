"""
Note-management tools: Search Notes, Save Note (required),
plus bonus tool: Summarize Notes.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
from dateutil import parser as dateparser

from app.database import repository as repo
from app.tools.base import BaseTool, ToolResult
from app.services.llm_service import llm_service


# ---------------------------------------------------------------------------
# Tool 5: Search Notes
# ---------------------------------------------------------------------------

class SearchNotesInput(BaseModel):
    query: str = Field(..., min_length=1)
    category: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SearchNotesTool(BaseTool):
    name = "search_notes"
    description = "Search saved notes by keyword, optionally filtered by category or date range."
    input_schema = SearchNotesInput
    requires_approval = False

    def execute(self, i: SearchNotesInput) -> ToolResult:
        results = repo.search_notes(
            query=i.query, category=i.category,
            date_from=dateparser.parse(i.date_from) if i.date_from else None,
            date_to=dateparser.parse(i.date_to) if i.date_to else None,
        )
        return ToolResult(success=True, data={"notes": results, "total_count": len(results)},
                           message=f"Found {len(results)} relevant note(s).")


# ---------------------------------------------------------------------------
# Tool 6: Save Note
# ---------------------------------------------------------------------------

class SaveNoteInput(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    category: str = "general"
    tags: list[str] = Field(default_factory=list)


class SaveNoteTool(BaseTool):
    name = "save_note"
    description = "Save a new note with title, content, category and tags."
    input_schema = SaveNoteInput
    requires_approval = False
    is_write_action = True

    def execute(self, i: SaveNoteInput) -> ToolResult:
        note = repo.create_note(title=i.title, content=i.content, category=i.category, tags=i.tags)
        return ToolResult(success=True, data=note, message=f"Saved note '{note['title']}' ({note['id']}).")


class DeleteNoteInput(BaseModel):
    note_id: str


class DeleteNoteTool(BaseTool):
    name = "delete_note"
    description = "Permanently delete a note record. This is irreversible and requires human approval."
    input_schema = DeleteNoteInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: DeleteNoteInput) -> ToolResult:
        all_notes = repo.list_notes()
        existing = next((n for n in all_notes if n["id"] == i.note_id), None)
        if not existing:
            return ToolResult(success=False, error=f"Unknown note ID: {i.note_id}")
        repo.delete_note(i.note_id)
        return ToolResult(success=True, data={"deleted_note_id": i.note_id},
                           message=f"Deleted note '{existing['title']}' ({i.note_id}).")


# ---------------------------------------------------------------------------
# Bonus Tool: Summarize Notes
# ---------------------------------------------------------------------------

class SummarizeNotesInput(BaseModel):
    query: Optional[str] = Field(None, description="Optional keyword to select which notes to summarize")
    note_ids: Optional[list[str]] = None


class SummarizeNotesTool(BaseTool):
    name = "summarize_notes"
    description = "Summarize a set of notes (selected by query or explicit IDs) into key points."
    input_schema = SummarizeNotesInput
    requires_approval = False

    def execute(self, i: SummarizeNotesInput) -> ToolResult:
        if i.note_ids:
            all_notes = repo.list_notes()
            notes = [n for n in all_notes if n["id"] in i.note_ids]
        elif i.query:
            notes = repo.search_notes(i.query)
        else:
            notes = repo.list_notes()[:10]

        if not notes:
            return ToolResult(success=True, data={"summary": "", "notes_considered": 0},
                               message="No matching notes found to summarize.")

        combined = "\n\n".join(f"- {n['title']}: {n['content']}" for n in notes)
        summary = llm_service.summarize_text(
            combined,
            instruction="Summarize the following notes into concise bullet points covering the "
                        "key ideas across all of them. Keep it under 150 words."
        )
        return ToolResult(success=True, data={"summary": summary, "notes_considered": len(notes)},
                           message=f"Summarized {len(notes)} note(s).")