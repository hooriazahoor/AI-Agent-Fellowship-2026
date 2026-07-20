from app.database import repository as repo
from app.tools.note_tools import SearchNotesTool, SaveNoteTool


def test_save_note():
    tool = SaveNoteTool()
    result = tool.run({"title": "Marketing plan", "content": "Q3 campaign budget details.",
                        "category": "meetings", "tags": ["marketing"]})
    assert result.success is True
    assert result.data["title"] == "Marketing plan"


def test_notes_search_by_keyword():
    repo.create_note(title="Marketing campaign kickoff", content="Discussed the Q3 marketing campaign budget.",
                      category="meetings")
    repo.create_note(title="Unrelated note", content="Grocery list for the week.", category="personal")
    tool = SearchNotesTool()
    result = tool.run({"query": "marketing campaign"})
    assert result.success is True
    assert result.data["total_count"] == 1
    assert "Marketing" in result.data["notes"][0]["title"]


def test_notes_search_no_match_returns_empty():
    repo.create_note(title="Random", content="Nothing relevant here.", category="general")
    tool = SearchNotesTool()
    result = tool.run({"query": "quantum physics"})
    assert result.success is True
    assert result.data["total_count"] == 0
