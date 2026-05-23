"""
Pytest configuration: point FINANCE_DB at a fresh temp database before any
module that reads DB_PATH at import time gets loaded.
"""
import os
import sys
import tempfile
import pytest

# Insert project root so tests can import project modules directly.
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(scope="session", autouse=True)
def isolated_db(tmp_path_factory):
    """Redirect all DB access to a throwaway SQLite file for the test session."""
    tmp = tmp_path_factory.mktemp("db")
    db_path = str(tmp / "test_finance.db")

    import database
    original_path = database.DB_PATH
    database.DB_PATH = db_path
    database.init_db()

    yield db_path

    database.DB_PATH = original_path
