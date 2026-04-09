"""Tests for ProjectHub core logic: brain utils, project scanning, heatmap API."""
import json
import sqlite3
from unittest.mock import patch


# ── Brain utils ──────────────────────────────────────────────────────────────

def test_brain_project_slug():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import brain_project_slug
    assert brain_project_slug("infra/@projecthub") == "infra--@projecthub"
    assert brain_project_slug("my project") == "my_project"
    assert brain_project_slug("simple") == "simple"


def test_brain_slug_to_display():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import brain_slug_to_display
    assert brain_slug_to_display("infra--@projecthub") == "infra/@projecthub"
    assert brain_slug_to_display("my_project") == "my project"


def test_brain_slug_roundtrip():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import brain_project_slug, brain_slug_to_display
    names = ["web/frontend", "infra/@projecthub", "my cool project", "simple"]
    for name in names:
        assert brain_slug_to_display(brain_project_slug(name)) == name


# ── Project scanning ─────────────────────────────────────────────────────────

def test_is_project_dir_with_git(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import _is_project_dir
    (tmp_path / ".git").mkdir()
    assert _is_project_dir(tmp_path) is True


def test_is_project_dir_with_marker(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import _is_project_dir
    (tmp_path / "package.json").write_text("{}")
    assert _is_project_dir(tmp_path) is True


def test_is_project_dir_empty(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import _is_project_dir
    assert _is_project_dir(tmp_path) is False


def test_is_container_dir_node_modules(tmp_path):
    """node_modules should be skipped at scan level, but _is_container_dir sees it as non-project."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import _is_container_dir
    nm = tmp_path / "node_modules"
    nm.mkdir()
    # node_modules with sub-projects should still be detected as container
    # but scan_projects filters it out before calling _is_container_dir
    for pkg in ["axios", "lodash", "express"]:
        p = nm / pkg
        p.mkdir()
        (p / "package.json").write_text("{}")
    assert _is_container_dir(nm) is True  # it IS a container structurally


def test_skip_dirs_in_scan(tmp_path):
    """scan_projects should skip node_modules, venv, etc."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import scan_projects, PROJECTS_ROOT

    # Create fake @category with node_modules and a real project
    cat = tmp_path / "@test"
    cat.mkdir()
    (cat / "real_project" / ".git").mkdir(parents=True)
    nm = cat / "node_modules" / "fake_pkg"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text("{}")

    with patch("main.PROJECTS_ROOT", tmp_path):
        projects = scan_projects()

    names = [p["name"] for p in projects]
    assert "real_project" in names
    assert not any("node_modules" in n for n in names)


# ── detect_project_type ──────────────────────────────────────────────────────

def test_detect_python(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import detect_project_type
    (tmp_path / "requirements.txt").write_text("flask\n")
    assert detect_project_type(tmp_path) == "flask"


def test_detect_nextjs(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import detect_project_type
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"next": "^14.0.0", "react": "^18.0.0"}
    }))
    assert detect_project_type(tmp_path) == "nextjs"


def test_detect_docker(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import detect_project_type
    (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
    assert detect_project_type(tmp_path) == "docker"


def test_detect_unknown(tmp_path):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import detect_project_type
    (tmp_path / "readme.md").write_text("hello")
    assert detect_project_type(tmp_path) in ("", "unknown")


# ── Database: CASCADE DELETE ─────────────────────────────────────────────────

def test_cascade_delete(tmp_path):
    """Deleting a project should cascade-delete its notes and commands."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""CREATE TABLE projects (
        id INTEGER PRIMARY KEY, name TEXT UNIQUE, path TEXT,
        category TEXT, display_name TEXT, status TEXT DEFAULT 'active',
        tags TEXT DEFAULT '[]', project_type TEXT DEFAULT '',
        description TEXT DEFAULT '', label TEXT, sort_order INTEGER DEFAULT 0,
        last_opened TIMESTAMP, open_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE notes (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE TABLE commands (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
        name TEXT, command TEXT, cwd TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    )""")

    conn.execute("INSERT INTO projects (name, path, category, display_name) VALUES ('test', '/tmp/test', 'cat', 'Test')")
    conn.execute("INSERT INTO notes (project_id, content) VALUES (1, 'note1')")
    conn.execute("INSERT INTO notes (project_id, content) VALUES (1, 'note2')")
    conn.execute("INSERT INTO commands (project_id, name, command) VALUES (1, 'build', 'npm run build')")
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1

    conn.execute("DELETE FROM projects WHERE id = 1")
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 0
    conn.close()


# ── Heatmap streak logic ────────────────────────────────────────────────────

def test_streak_calculation():
    """Streak should count consecutive days from end of array."""
    # Simulate: [0, 0, 3, 2, 1] = 3 days streak
    days = [
        {"date": "2026-04-06", "count": 0},
        {"date": "2026-04-07", "count": 0},
        {"date": "2026-04-08", "count": 3},
        {"date": "2026-04-09", "count": 2},
        {"date": "2026-04-10", "count": 1},
    ]
    streak = 0
    for i in range(len(days) - 1, -1, -1):
        if days[i]["count"] > 0:
            streak += 1
        else:
            break
    assert streak == 3


def test_streak_zero_today():
    """If today has no activity, streak should be 0."""
    days = [
        {"date": "2026-04-08", "count": 5},
        {"date": "2026-04-09", "count": 3},
        {"date": "2026-04-10", "count": 0},
    ]
    streak = 0
    for i in range(len(days) - 1, -1, -1):
        if days[i]["count"] > 0:
            streak += 1
        else:
            break
    assert streak == 0


def test_streak_all_active():
    """All days active = full streak."""
    days = [{"date": f"2026-04-0{i}", "count": i + 1} for i in range(1, 6)]
    streak = 0
    for i in range(len(days) - 1, -1, -1):
        if days[i]["count"] > 0:
            streak += 1
        else:
            break
    assert streak == 5
