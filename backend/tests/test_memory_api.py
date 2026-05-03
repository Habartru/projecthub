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
