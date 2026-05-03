"""Tests for /api/memory/* HTTP endpoints."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Spin up a FastAPI client with isolated DB and brain vault."""
    db_path = tmp_path / "test.db"
    brain = tmp_path / "brain"
    brain.mkdir()

    monkeypatch.setenv("PROJECTHUB_DB_PATH", str(db_path))
    monkeypatch.setenv("PROJECTHUB_BRAIN_HOME", str(brain))
    monkeypatch.setenv("PROJECTHUB_SKIP_FS_SYNC", "1")

    # Force re-import so env vars take effect
    for mod in list(sys.modules):
        if mod.startswith("main") or mod.startswith("projecthub_memory_core"):
            del sys.modules[mod]

    from main import app  # noqa
    with TestClient(app) as test_client:
        yield test_client


def test_memory_projects_returns_only_existing_paths(client, tmp_path):
    """Orphaned rows (path missing on disk) must be filtered out."""
    # Seed two projects: one valid, one orphaned
    real_dir = tmp_path / "real_proj"
    real_dir.mkdir()

    import sqlite3
    conn = sqlite3.connect(os.environ["PROJECTHUB_DB_PATH"])
    conn.execute(
        "INSERT INTO projects (name, category, path, display_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("real", "test", str(real_dir), ""),
    )
    conn.execute(
        "INSERT INTO projects (name, category, path, display_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("ghost", "test", str(tmp_path / "deleted_proj"), ""),
    )
    conn.commit()
    conn.close()

    resp = client.get("/api/memory/projects")
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data["projects"]]
    assert "test/real" in names
    assert "test/ghost" not in names
    assert data["total"] == 1
    # All returned entries must have an absolute path that exists
    for p in data["projects"]:
        assert os.path.isabs(p["path"])
        assert os.path.exists(p["path"])


def test_post_insight_writes_to_daily_log(client, tmp_path):
    real_dir = tmp_path / "p"
    real_dir.mkdir()
    import sqlite3
    conn = sqlite3.connect(os.environ["PROJECTHUB_DB_PATH"])
    conn.execute(
        "INSERT INTO projects (name, category, path, display_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("a", "x", str(real_dir), ""),
    )
    conn.commit()
    conn.close()

    resp = client.post("/api/memory/insight", json={
        "project": "x/a",
        "insight_type": "decision",
        "content": "Use approach Z because of constraint Q.",
        "tags": ["arch"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert data["compiled"] is True
    assert "daily" in data["daily_log"]
    assert "Use approach Z" in Path(data["daily_log"]).read_text()


def test_post_insight_rejects_unknown_project(client):
    resp = client.post("/api/memory/insight", json={
        "project": "ghost/missing",
        "insight_type": "decision",
        "content": "ignored",
    })
    assert resp.status_code == 404


def test_post_insight_accepts_system_scratch(client):
    resp = client.post("/api/memory/insight", json={
        "project": "system/scratch",
        "insight_type": "decision",
        "content": "Anywhere thought.",
    })
    assert resp.status_code == 200


def test_post_insight_rejects_oversized_content(client):
    resp = client.post("/api/memory/insight", json={
        "project": "system/scratch",
        "insight_type": "decision",
        "content": "x" * 4001,
    })
    assert resp.status_code == 400


def test_post_insight_rejects_invalid_type(client):
    resp = client.post("/api/memory/insight", json={
        "project": "system/scratch",
        "insight_type": "garbage",
        "content": "ok",
    })
    assert resp.status_code == 400


def test_get_context_returns_existing_article(client, tmp_path):
    real_dir = tmp_path / "p"
    real_dir.mkdir()
    import sqlite3
    conn = sqlite3.connect(os.environ["PROJECTHUB_DB_PATH"])
    conn.execute(
        "INSERT INTO projects (name, category, path, display_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("a", "x", str(real_dir), ""),
    )
    conn.commit()
    conn.close()

    # Seed an insight first
    client.post("/api/memory/insight", json={
        "project": "x/a", "insight_type": "decision",
        "content": "Decided to use Y.", "tags": [],
    })

    resp = client.get("/api/memory/context", params={"project": "x/a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert "Decided to use Y." in data["context"]
    assert data["char_count"] > 0


def test_get_context_returns_empty_for_missing(client):
    resp = client.get("/api/memory/context", params={"project": "system/scratch"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False
    assert data["context"] == ""
    assert data["char_count"] == 0


def test_get_history_merges_git_and_insights(client, tmp_path):
    """history returns insights ordered by date, plus a git_commits placeholder.

    For v1 we don't fully test git merging (project may not be a real repo
    in tmp_path); we verify endpoint shape and insight inclusion.
    """
    real_dir = tmp_path / "p"
    real_dir.mkdir()
    import sqlite3
    conn = sqlite3.connect(os.environ["PROJECTHUB_DB_PATH"])
    conn.execute(
        "INSERT INTO projects (name, category, path, display_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("a", "x", str(real_dir), ""),
    )
    conn.commit()
    conn.close()

    client.post("/api/memory/insight", json={
        "project": "x/a", "insight_type": "bug",
        "content": "Found a regression in Z.", "tags": ["regression"],
    })

    resp = client.get("/api/memory/history", params={"project": "x/a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["project"] == "x/a"
    assert "period" in data
    assert "git_commits" in data and isinstance(data["git_commits"], list)
    assert "insights" in data and isinstance(data["insights"], list)
    assert any("Found a regression" in i["content"] for i in data["insights"])
    assert "merged_timeline" in data
