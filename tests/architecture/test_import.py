import json
import runpy
from pathlib import Path

import pytest

from module1_puzzles.puzzles import DEMO_PUZZLES
from module3_host.storage import Repository

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/import_puzzles.py"


def test_import_is_idempotent(tmp_path, monkeypatch):
    library = tmp_path / "legacy.json"
    library.write_text(json.dumps([DEMO_PUZZLES[0]]), encoding="utf-8")
    database = tmp_path / "import.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(library)])
    for _ in range(2):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert len(Repository(database).puzzles()) == 1


def test_bad_library_is_rejected_before_any_write(tmp_path, monkeypatch):
    library = tmp_path / "invalid.json"
    library.write_text(json.dumps([DEMO_PUZZLES[0], {"id": "broken"}]), encoding="utf-8")
    database = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), str(library)])
    with pytest.raises(SystemExit):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert not database.exists()
