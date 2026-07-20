import os
import sys
import tempfile
import pytest

# Point the app at an isolated SQLite file BEFORE any app module is imported,
# since app.database.repository creates its engine at import time.
_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test_productivity_agent.db"
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.repository import init_db, get_session  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.database import repository as repo  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Reset all tables before every test so tests are independent."""
    Base.metadata.drop_all(repo._engine)
    Base.metadata.create_all(repo._engine)
    yield
