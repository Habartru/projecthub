"""Shared memory-core primitives for ProjectHub.

Used by both the MCP server (server.py) and the FastAPI backend
(backend/main.py) to ensure single source of truth for vault writes.

Paths are read from the `PROJECTHUB_BRAIN_HOME` env var if set,
otherwise default to `~/Projects/@memory/brain`. Use reload_paths_from_env()
in tests to switch between vaults.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

# ── Path constants (re-bindable for tests) ───────────────────────────────────

MEMORY_DIR: Path
DAILY_DIR: Path
KNOWLEDGE_DIR: Path
INDEX_FILE: Path


def reload_paths_from_env() -> None:
    """Refresh module-level path constants from PROJECTHUB_BRAIN_HOME."""
    global MEMORY_DIR, DAILY_DIR, KNOWLEDGE_DIR, INDEX_FILE
    base = os.environ.get("PROJECTHUB_BRAIN_HOME")
    MEMORY_DIR = Path(base) if base else (Path.home() / "Projects" / "@memory" / "brain")
    DAILY_DIR = MEMORY_DIR / "daily"
    KNOWLEDGE_DIR = MEMORY_DIR / "knowledge"
    INDEX_FILE = KNOWLEDGE_DIR / "index.md"


reload_paths_from_env()


def ensure_knowledge_dirs() -> None:
    """Ensure all knowledge base directories exist."""
    for d in [DAILY_DIR, KNOWLEDGE_DIR / "concepts", KNOWLEDGE_DIR / "projects", KNOWLEDGE_DIR / "qa"]:
        d.mkdir(parents=True, exist_ok=True)


def get_daily_log_path() -> Path:
    """Get path to today's daily log."""
    today = datetime.now().strftime("%Y-%m-%d")
    return DAILY_DIR / f"{today}.md"


def append_to_daily_log(project: str, insight_type: str, content: str, tags: list[str]) -> None:
    """Append an insight entry to today's daily log."""
    ensure_knowledge_dirs()
    log_path = get_daily_log_path()
    timestamp = datetime.now().strftime("%H:%M")
    tags_str = " ".join(f"#{t}" for t in tags) if tags else ""

    entry = (
        f"\n## [{timestamp}] {project}\n"
        f"**Type:** {insight_type}  \n"
        f"**Tags:** {tags_str}  \n\n"
        f"{content}\n"
        f"\n---\n"
    )

    if not log_path.exists():
        header = (
            f"# Daily Log — {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"*Автоматически записывается MCP project-context*\n\n"
        )
        log_path.write_text(header + entry)
    else:
        with log_path.open("a") as f:
            f.write(entry)


def get_project_knowledge_path(project_name: str) -> Path:
    """Get path to project knowledge file."""
    safe_name = project_name.replace("/", "--").replace(" ", "_")
    return KNOWLEDGE_DIR / "projects" / f"{safe_name}.md"


def load_project_knowledge(project_name: str) -> str:
    """Load accumulated knowledge for a project."""
    proj_file = get_project_knowledge_path(project_name)
    if not proj_file.exists():
        return ""
    return proj_file.read_text()


def compile_daily_to_project(project_name: str, entries: list[dict]) -> str:
    """Compile daily log entries into project knowledge article."""
    proj_file = get_project_knowledge_path(project_name)
    ensure_knowledge_dirs()

    existing = proj_file.read_text() if proj_file.exists() else ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entries_md = ""
    for e in entries:
        tags_str = " ".join(f"#{t}" for t in e.get("tags", []))
        new_entries_md += (
            f"\n### {e['type']} — {e['timestamp']}\n"
            f"{tags_str}  \n\n"
            f"{e['content']}\n\n"
        )

    if existing:
        # Insert new entries after the first ## section or at end
        updated = existing + f"\n## Обновление {now}\n" + new_entries_md
    else:
        safe_name = project_name.replace("/", " / ")
        updated = (
            f"# {safe_name}\n\n"
            f"*Knowledge article. Последнее обновление: {now}*\n\n"
            f"## История решений\n"
            + new_entries_md
        )

    proj_file.write_text(updated)
    return str(proj_file)


def update_index() -> None:
    """Rebuild index.md from all project, concept, and daily-log files.

    Every section is rebuilt from the actual files on disk so daily logs and
    project articles created outside of compile_knowledge (e.g. by
    log_session_insight) never end up as orphan nodes in Obsidian's graph.
    """
    ensure_knowledge_dirs()

    projects_section = ""
    proj_dir = KNOWLEDGE_DIR / "projects"
    if proj_dir.exists():
        for f in sorted(proj_dir.glob("*.md")):
            display = f.stem.replace("--", "/").replace("_", " ")
            mod_time = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
            projects_section += f"- [[projects/{f.stem}|{display}]] — обновлено {mod_time}\n"

    concepts_section = ""
    con_dir = KNOWLEDGE_DIR / "concepts"
    if con_dir.exists():
        for f in sorted(con_dir.glob("*.md")):
            display = f.stem.replace("-", " ").replace("_", " ")
            concepts_section += f"- [[concepts/{f.stem}|{display}]]\n"

    daily_section = ""
    if DAILY_DIR.exists():
        # Newest first — matches reverse-chronological reading order.
        daily_files = sorted(
            (f for f in DAILY_DIR.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem)),
            key=lambda p: p.stem,
            reverse=True,
        )
        for f in daily_files:
            daily_section += f"- [[daily/{f.stem}]]\n"

    if not projects_section:
        projects_section = "*(пока пусто — появится после первого log_session_insight)*\n"
    if not concepts_section:
        concepts_section = "*(пока пусто)*\n"
    if not daily_section:
        daily_section = "*(пока пусто)*\n"

    content = INDEX_FILE.read_text() if INDEX_FILE.exists() else ""

    content = re.sub(
        r"<!-- PROJECTS_INDEX_START -->.*?<!-- PROJECTS_INDEX_END -->",
        f"<!-- PROJECTS_INDEX_START -->\n{projects_section}<!-- PROJECTS_INDEX_END -->",
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r"<!-- CONCEPTS_INDEX_START -->.*?<!-- CONCEPTS_INDEX_END -->",
        f"<!-- CONCEPTS_INDEX_START -->\n{concepts_section}<!-- CONCEPTS_INDEX_END -->",
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r"<!-- DAILY_INDEX_START -->.*?<!-- DAILY_INDEX_END -->",
        f"<!-- DAILY_INDEX_START -->\n{daily_section}<!-- DAILY_INDEX_END -->",
        content,
        flags=re.DOTALL
    )
    INDEX_FILE.write_text(content)
