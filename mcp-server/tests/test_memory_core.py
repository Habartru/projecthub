"""Unit tests for the extracted memory-core primitives."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_append_to_daily_log_creates_file_with_header(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTHUB_BRAIN_HOME", str(tmp_path))
    import projecthub_memory_core as core
    core.reload_paths_from_env()  # see Step 3

    core.append_to_daily_log(
        project="x/y",
        insight_type="decision",
        content="Use SQLite WAL mode for concurrent reads.",
        tags=["sqlite", "wal"],
    )

    log = tmp_path / "daily" / f"{__import__('datetime').date.today().isoformat()}.md"
    assert log.exists()
    text = log.read_text()
    assert "Daily Log" in text
    assert "[" in text  # timestamp marker
    assert "x/y" in text
    assert "decision" in text
    assert "Use SQLite WAL mode" in text
    assert "#sqlite" in text and "#wal" in text


def test_append_to_daily_log_appends_to_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTHUB_BRAIN_HOME", str(tmp_path))
    import projecthub_memory_core as core
    core.reload_paths_from_env()

    core.append_to_daily_log("a/b", "decision", "First.", [])
    core.append_to_daily_log("a/b", "bug", "Second.", ["x"])

    log = tmp_path / "daily" / f"{__import__('datetime').date.today().isoformat()}.md"
    text = log.read_text()
    assert text.count("---\n") >= 2
    assert "First." in text
    assert "Second." in text


def test_compile_daily_to_project_creates_knowledge_article(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTHUB_BRAIN_HOME", str(tmp_path))
    import projecthub_memory_core as core
    core.reload_paths_from_env()

    path = core.compile_daily_to_project(
        "x/y",
        [{"type": "decision", "timestamp": "12:00", "content": "Pick X.", "tags": ["a"]}],
    )
    p = Path(path)
    assert p.exists()
    text = p.read_text()
    assert "x / y" in text
    assert "Pick X." in text
    assert "#a" in text


def test_get_project_knowledge_path_safe_naming(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTHUB_BRAIN_HOME", str(tmp_path))
    import projecthub_memory_core as core
    core.reload_paths_from_env()

    p = core.get_project_knowledge_path("infra/@projecthub")
    assert p.name == "infra--@projecthub.md"
