#!/usr/bin/env python3
"""
Project Context MCP Server
==========================
MCP server providing AI agents with information about all projects
organized under ~/Projects/@category/project_name structure.

SECURITY PRINCIPLES:
1. Every response ALWAYS includes explicit project identification
2. Never mix data from different projects
3. Validate project existence before any operation
4. Read-only operations by default
5. Log all requests
"""

import os
import re
import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
)

# Logging setup
LOG_DIR = Path.home() / ".config" / "project-context"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "mcp-server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
PROJECTS_DIR = Path.home() / "Projects"
CACHE_FILE = LOG_DIR / "projects_cache.json"
CACHE_TTL = 300  # 5 minutes

# Knowledge base (Obsidian vault is at @memory/brain/)
MEMORY_DIR = Path.home() / "Projects" / "@memory" / "brain"
DAILY_DIR = MEMORY_DIR / "daily"
KNOWLEDGE_DIR = MEMORY_DIR / "knowledge"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"

server = Server("project-context")


class ProjectContext:
    """Safe project context management."""

    _current_project: Optional[str] = None
    _projects_cache: dict = {}
    _cache_time: float = 0

    @classmethod
    def get_project_id(cls, project_name: str) -> str:
        """Generate a unique project ID to prevent confusion."""
        return hashlib.md5(project_name.encode()).hexdigest()[:8]

    @classmethod
    def resolve_project(cls, project_name: str) -> tuple[Optional[str], Path]:
        """
        Resolve a project name to its full category/name key and path.

        Accepts either:
          - "category/project_name" (e.g. "web/mysite")
          - "project_name" alone (searches across all categories)

        Returns (resolved_key, resolved_path). resolved_key is None if not found.
        """
        if "/" in project_name:
            # Explicit category/project format
            category, name = project_name.split("/", 1)
            cat_dir = "@" + category if not category.startswith("@") else category
            project_path = PROJECTS_DIR / cat_dir / name
            if project_path.is_dir():
                display_cat = cat_dir.lstrip("@")
                return f"{display_cat}/{name}", project_path
            return None, project_path

        # Search across all categories
        matches = []
        if PROJECTS_DIR.exists():
            for cat_dir in sorted(PROJECTS_DIR.iterdir()):
                if cat_dir.is_dir() and cat_dir.name.startswith("@"):
                    candidate = cat_dir / project_name
                    if candidate.is_dir():
                        display_cat = cat_dir.name.lstrip("@")
                        matches.append((f"{display_cat}/{project_name}", candidate))

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Ambiguous -- return None so caller can report options
            return None, PROJECTS_DIR
        return None, PROJECTS_DIR / project_name

    @classmethod
    def validate_project(cls, project_name: str) -> tuple[bool, str, str, Path]:
        """
        Validate project existence.
        Returns (exists, error_message, resolved_key, resolved_path).
        """
        resolved_key, resolved_path = cls.resolve_project(project_name)

        if resolved_key and resolved_path.is_dir():
            return True, "", resolved_key, resolved_path

        # Check for ambiguous matches
        if "/" not in project_name:
            matches = []
            if PROJECTS_DIR.exists():
                for cat_dir in sorted(PROJECTS_DIR.iterdir()):
                    if cat_dir.is_dir() and cat_dir.name.startswith("@"):
                        candidate = cat_dir / project_name
                        if candidate.is_dir():
                            display_cat = cat_dir.name.lstrip("@")
                            matches.append(f"{display_cat}/{project_name}")
            if len(matches) > 1:
                options = "\n".join(f"  - {m}" for m in matches)
                return False, (
                    f"Ambiguous project name '{project_name}'. "
                    f"Found in multiple categories:\n{options}\n"
                    f"Please specify as category/project_name."
                ), "", resolved_path

        available = cls.list_projects()
        return False, (
            f"Project '{project_name}' does not exist!\n\n"
            "Available projects:\n" + "\n".join(f"  - {p}" for p in available)
        ), "", resolved_path

    @classmethod
    def list_projects(cls) -> list[str]:
        """Get list of all projects as category/project_name."""
        if not PROJECTS_DIR.exists():
            return []
        projects = []
        for cat_dir in sorted(PROJECTS_DIR.iterdir()):
            if cat_dir.is_dir() and cat_dir.name.startswith("@"):
                display_cat = cat_dir.name.lstrip("@")
                for proj_dir in sorted(cat_dir.iterdir()):
                    if proj_dir.is_dir() and not proj_dir.name.startswith("."):
                        projects.append(f"{display_cat}/{proj_dir.name}")
        return projects

    @classmethod
    def format_response(cls, project_key: str, project_path: Path, data: dict) -> str:
        """
        Format response with MANDATORY project identification.
        Prevents AI agent confusion between projects.
        """
        project_id = cls.get_project_id(project_key)
        # Build display path like ~/Projects/@category/project_name
        try:
            rel = project_path.relative_to(Path.home())
            display_path = f"~/{rel}"
        except ValueError:
            display_path = str(project_path)

        header = (
            "\n"
            "+------------------------------------------------------------------+\n"
            f"| PROJECT: {project_key:<55} |\n"
            f"| ID:      {project_id:<55} |\n"
            f"| Path:    {display_path:<55} |\n"
            "+------------------------------------------------------------------+\n"
        )
        return header + json.dumps(data, ensure_ascii=False, indent=2)


SKIP_DIRS = frozenset({
    'node_modules', '.venv', 'venv', '__pycache__',
    '.idea', '.vscode', 'dist', 'build', 'target', 'out',
    '.next', '.nuxt', 'coverage', '.pytest_cache',
    '.mypy_cache', '.tox', '.ruff_cache', '.cache',
})

TYPE_MARKERS = {
    'requirements.txt': 'python',
    'pyproject.toml': 'python',
    'setup.py': 'python',
    'Pipfile': 'python',
    'package.json': 'javascript',
    'Cargo.toml': 'rust',
    'go.mod': 'go',
    'pom.xml': 'java',
    'build.gradle': 'java',
    'build.gradle.kts': 'java',
    'composer.json': 'php',
    'Gemfile': 'ruby',
}

DOCKER_FILES = frozenset({
    'docker-compose.yml', 'docker-compose.yaml',
    'docker-compose.dev.yml', 'docker-compose.prod.yml',
    'docker-compose.override.yml',
})

README_NAMES = frozenset({'README.md', 'README.rst', 'README.txt', 'README'})
ENV_EXAMPLE_NAMES = frozenset({'.env.example', '.env.sample', '.env.template'})

MAX_WALK_DEPTH = 3


def _walk_markers(root: Path, max_depth: int = MAX_WALK_DEPTH) -> dict:
    """BFS-walk the project tree, collecting marker files and dirs.

    Returns a dict with:
      - git_dirs: list[Path] of .git dirs, ordered by depth (closest first)
      - venv_dirs: list[Path] of directories containing pyvenv.cfg
      - docker_files: list[Path] of Dockerfile / docker-compose.* files
      - marker_paths: dict[basename -> Path] of first-found type markers
      - readme_paths: list[Path] of README files
      - env_files: list[Path] of .env.example / .env.sample files

    BFS guarantees that the closest-to-root file wins ties.
    """
    results = {
        'git_dirs': [],
        'venv_dirs': [],
        'docker_files': [],
        'marker_paths': {},
        'readme_paths': [],
        'env_files': [],
    }
    if not root.is_dir():
        return results

    queue = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        try:
            entries = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            name = entry.name
            if entry.is_dir():
                if name == '.git':
                    results['git_dirs'].append(entry)
                    continue
                # Venv detection runs BEFORE skip/hidden checks so .venv is found
                if (entry / 'pyvenv.cfg').exists():
                    results['venv_dirs'].append(entry)
                    continue
                if name in SKIP_DIRS:
                    continue
                if name.startswith('.'):
                    continue
                if depth < max_depth:
                    queue.append((entry, depth + 1))
                continue
            # Files
            if name in TYPE_MARKERS and name not in results['marker_paths']:
                results['marker_paths'][name] = entry
            if name in DOCKER_FILES or name == 'Dockerfile' or name.startswith('Dockerfile.'):
                results['docker_files'].append(entry)
            if name in README_NAMES:
                results['readme_paths'].append(entry)
            if name in ENV_EXAMPLE_NAMES:
                results['env_files'].append(entry)
    return results


def get_project_info(project_key: str, project_path: Path) -> dict:
    """Collect full information about a project.

    Walks up to MAX_WALK_DEPTH levels so monorepos and projects with code
    in subdirs (e.g. root/backend/, root/services/api/) are detected
    correctly.
    """
    info = {
        "name": project_key,
        "id": ProjectContext.get_project_id(project_key),
        "path": str(project_path),
        "exists": project_path.exists(),
        "type": [],
        "files_count": 0,
        "has_git": False,
        "git_branch": None,
        "has_venv": False,
        "venv_python": None,
        "has_docker": False,
        "dependencies": {},
        "env_vars_required": [],
        "readme_exists": False,
        "last_modified": None,
    }

    if not project_path.exists():
        return info

    markers = _walk_markers(project_path)

    # Type detection (deterministic order, dedup via union of TYPE_MARKERS)
    found_types = set()
    for name, ptype in TYPE_MARKERS.items():
        if name in markers['marker_paths']:
            found_types.add(ptype)
    for t in ['python', 'javascript', 'rust', 'go', 'java', 'php', 'ruby']:
        if t in found_types:
            info['type'].append(t)

    # Git info — use .git closest to root
    if markers['git_dirs']:
        info['has_git'] = True
        git_dir = min(markers['git_dirs'], key=lambda p: len(p.parts))
        git_root = git_dir.parent
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            info['git_branch'] = result.stdout.strip() or "detached"
        except Exception:
            pass

    # Virtual environment — closest venv wins
    if markers['venv_dirs']:
        info['has_venv'] = True
        venv_path = min(markers['venv_dirs'], key=lambda p: len(p.parts))
        pyvenv_cfg = venv_path / "pyvenv.cfg"
        if pyvenv_cfg.exists():
            try:
                for line in pyvenv_cfg.read_text().splitlines():
                    if "version" in line.lower() and "=" in line:
                        info['venv_python'] = line.split("=", 1)[1].strip()
                        break
            except Exception:
                pass

    # Docker
    info['has_docker'] = bool(markers['docker_files'])

    # Dependencies — use closest (shortest path) marker file
    req_path = markers['marker_paths'].get('requirements.txt')
    if req_path:
        try:
            deps = []
            for line in req_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps.append(line)
            info['dependencies']['python'] = deps[:20]
        except Exception:
            pass

    pkg_path = markers['marker_paths'].get('package.json')
    if pkg_path:
        try:
            pkg = json.loads(pkg_path.read_text())
            info['dependencies']['npm'] = list(pkg.get("dependencies", {}).keys())[:20]
        except Exception:
            pass

    # ENV variables (names only, never values)
    for env_path in markers['env_files']:
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var_name = line.split("=", 1)[0].strip()
                    if var_name and var_name not in info['env_vars_required']:
                        info['env_vars_required'].append(var_name)
        except Exception:
            pass

    # README
    info['readme_exists'] = bool(markers['readme_paths'])

    # Last modified (of the project root, not walked files)
    try:
        stat = project_path.stat()
        info["last_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except Exception:
        pass

    # File count
    try:
        count = 0
        for walk_root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != '.git']
            count += len(files)
            if count > 1000:
                break
        info["files_count"] = min(count, 1000)
    except Exception:
        pass

    return info


def get_docker_status() -> dict:
    """Get Docker container status."""
    result = {
        "docker_running": False,
        "containers": {
            "running": [],
            "stopped": []
        }
    }

    try:
        check = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        result["docker_running"] = check.returncode == 0

        if result["docker_running"]:
            ps = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            for line in ps.stdout.strip().splitlines():
                if line:
                    parts = line.split("|")
                    container = {
                        "name": parts[0],
                        "status": parts[1] if len(parts) > 1 else "",
                        "ports": parts[2] if len(parts) > 2 else ""
                    }
                    if "Up" in container["status"]:
                        result["containers"]["running"].append(container)
                    else:
                        result["containers"]["stopped"].append(container)
    except Exception as e:
        result["error"] = str(e)

    return result


def get_databases() -> dict:
    """Get PostgreSQL database information (no hardcoded credentials)."""
    result = {
        "postgresql_available": False,
        "databases": []
    }

    try:
        # Check if PostgreSQL is reachable
        check = subprocess.run(
            ["pg_isready", "-h", "localhost", "-p", "5432"],
            capture_output=True,
            timeout=5
        )
        result["postgresql_available"] = check.returncode == 0

        if result["postgresql_available"]:
            # Try connecting as current OS user (peer/trust auth)
            ps = subprocess.run(
                ["psql", "-h", "localhost", "-t", "-c",
                 "SELECT datname, pg_size_pretty(pg_database_size(datname)) "
                 "FROM pg_database WHERE datistemplate = false;"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if ps.returncode == 0:
                for line in ps.stdout.strip().splitlines():
                    if line.strip():
                        parts = line.split("|")
                        if len(parts) >= 2:
                            result["databases"].append({
                                "name": parts[0].strip(),
                                "size": parts[1].strip()
                            })
            else:
                result["note"] = (
                    "PostgreSQL is running but could not list databases. "
                    "Current user may lack access. Configure pg_hba.conf or "
                    "set PGUSER/PGPASSWORD environment variables."
                )
    except Exception as e:
        result["error"] = str(e)

    return result


# ==============================================================================
# KNOWLEDGE BASE FUNCTIONS
# ==============================================================================

def ensure_knowledge_dirs():
    """Ensure all knowledge base directories exist."""
    for d in [DAILY_DIR, KNOWLEDGE_DIR / "concepts", KNOWLEDGE_DIR / "projects", KNOWLEDGE_DIR / "qa"]:
        d.mkdir(parents=True, exist_ok=True)


def get_daily_log_path() -> Path:
    """Get path to today's daily log."""
    today = datetime.now().strftime("%Y-%m-%d")
    return DAILY_DIR / f"{today}.md"


def append_to_daily_log(project: str, insight_type: str, content: str, tags: list[str]):
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


def update_index():
    """Rebuild index.md from all project and concept files."""
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

    if not projects_section:
        projects_section = "*(пока пусто — появится после первого log_session_insight)*\n"
    if not concepts_section:
        concepts_section = "*(пока пусто)*\n"

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
    INDEX_FILE.write_text(content)


# ==============================================================================
# MCP TOOLS
# ==============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_all_projects",
            description="""List ALL projects in the system.

Use this tool FIRST if you are unsure which projects exist.
Projects are returned as "category/project_name" (e.g. "web/mysite").
This prevents hallucinations about non-existent projects.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_project_details",
            description="""Get FULL information about a specific project.

IMPORTANT:
- Use EXACT project name (case-sensitive!)
- Accepts "category/project_name" or just "project_name" (will search across categories)
- Information applies ONLY to the specified project
- DO NOT MIX data with other projects""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project name: 'category/name' or just 'name'"
                    }
                },
                "required": ["project_name"]
            }
        ),
        Tool(
            name="get_project_dependencies",
            description="""Get dependencies for a SPECIFIC project.

WARNING: Dependencies from different projects may conflict!
Always verify which project the dependencies belong to.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project name: 'category/name' or just 'name'"
                    }
                },
                "required": ["project_name"]
            }
        ),
        Tool(
            name="get_docker_status",
            description="Get status of all Docker containers in the system.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_databases",
            description="Get list of PostgreSQL databases (uses current OS user auth).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_system_status",
            description="Get overall system status (Docker, DB, projects).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="compare_projects",
            description="""Compare two projects side by side.

Useful for understanding differences in dependencies and structure.
Result clearly separates information by project.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_a": {
                        "type": "string",
                        "description": "First project name"
                    },
                    "project_b": {
                        "type": "string",
                        "description": "Second project name"
                    }
                },
                "required": ["project_a", "project_b"]
            }
        ),
        Tool(
            name="read_project_file",
            description="""Read a file from a SPECIFIC project.

SECURITY:
- Read-only, no modifications
- File must exist
- Will not read .env files with secrets (only .env.example)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project name: 'category/name' or just 'name'"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file relative to project root"
                    }
                },
                "required": ["project_name", "file_path"]
            }
        ),
        Tool(
            name="log_session_insight",
            description="""Save an important insight, decision, pattern or lesson learned from the current session to the knowledge base.

Call this when you discover:
- Architecture decisions (why something was built a certain way)
- Bugs and their fixes (gotchas)
- Reusable patterns specific to this project
- Tech stack details (versions, configs)
- Anything worth remembering for next session

The insight is written to a daily log and compiled into a permanent project knowledge article.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project name: 'category/name' or just 'name'"
                    },
                    "insight_type": {
                        "type": "string",
                        "enum": ["decision", "bug", "pattern", "gotcha", "stack", "qa", "other"],
                        "description": "Type of insight"
                    },
                    "content": {
                        "type": "string",
                        "description": "The insight content. Be specific and actionable."
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for searchability, e.g. ['tailwind', 'auth', 'docker']"
                    }
                },
                "required": ["project_name", "insight_type", "content"]
            }
        ),
        Tool(
            name="get_project_context",
            description="""Retrieve accumulated knowledge for a project from the knowledge base.

Call this at the START of a session when working on a specific project.
Returns all saved decisions, patterns, bugs, and lessons learned.
This is how the AI 'remembers' previous sessions.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project name: 'category/name' or just 'name'"
                    }
                },
                "required": ["project_name"]
            }
        ),
        Tool(
            name="compile_knowledge",
            description="""Compile daily logs into structured project knowledge articles and update the index.

Run this:
- After a productive session to crystallize learnings
- When the daily log has accumulated many entries
- To rebuild the index.md for Obsidian

Reads all unprocessed daily log entries and merges them into permanent knowledge articles.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Optional: compile only for specific project. Leave empty to compile all."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_project_history",
            description="""Get full development history of a project: git commits + saved session insights.

Use this to understand:
- What changed in the project over any time period
- Why decisions were made (from logged insights)
- Bugs that were fixed and when
- The full timeline of development

Parameters allow flexible querying:
- No dates = FULL history (all time)
- date_from only = from that date to now
- date_to only = everything up to that date
- Both = specific period

Git log and memory insights are merged chronologically.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project name: 'category/name' or just 'name'"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start date ISO format: YYYY-MM-DD (optional, omit for full history)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End date ISO format: YYYY-MM-DD (optional, omit for today)"
                    },
                    "include_git": {
                        "type": "boolean",
                        "description": "Include git commit history (default: true)"
                    },
                    "include_insights": {
                        "type": "boolean",
                        "description": "Include saved session insights from memory (default: true)"
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Max number of git commits to return (default: 200, use 0 for unlimited)"
                    }
                },
                "required": ["project_name"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""

    logger.info(f"Tool call: {name}, args: {arguments}")

    try:
        if name == "list_all_projects":
            projects = ProjectContext.list_projects()
            result = {
                "total_count": len(projects),
                "projects": [],
                "hint": "Use EXACT project names (category/name) in subsequent requests."
            }
            for p in projects:
                _, proj_path = ProjectContext.resolve_project(p)
                info = get_project_info(p, proj_path)
                result["projects"].append({
                    "name": p,
                    "id": info["id"],
                    "type": info["type"],
                    "has_venv": info["has_venv"],
                    "has_docker": info["has_docker"],
                    "has_git": info["has_git"]
                })
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2)
            )]

        elif name == "get_project_details":
            project_name = arguments.get("project_name", "")
            exists, error, key, path = ProjectContext.validate_project(project_name)
            if not exists:
                return [TextContent(type="text", text=error)]

            info = get_project_info(key, path)
            return [TextContent(
                type="text",
                text=ProjectContext.format_response(key, path, info)
            )]

        elif name == "get_project_dependencies":
            project_name = arguments.get("project_name", "")
            exists, error, key, path = ProjectContext.validate_project(project_name)
            if not exists:
                return [TextContent(type="text", text=error)]

            info = get_project_info(key, path)
            deps = {
                "project_name": key,
                "project_id": info["id"],
                "warning": f"These dependencies are ONLY for project '{key}'!",
                "dependencies": info["dependencies"],
                "env_vars_required": info["env_vars_required"]
            }
            return [TextContent(
                type="text",
                text=ProjectContext.format_response(key, path, deps)
            )]

        elif name == "get_docker_status":
            status = get_docker_status()
            return [TextContent(
                type="text",
                text="DOCKER STATUS\n" + json.dumps(status, ensure_ascii=False, indent=2)
            )]

        elif name == "get_databases":
            dbs = get_databases()
            return [TextContent(
                type="text",
                text="POSTGRESQL DATABASES\n" + json.dumps(dbs, ensure_ascii=False, indent=2)
            )]

        elif name == "get_system_status":
            docker = get_docker_status()
            dbs = get_databases()
            projects = ProjectContext.list_projects()

            status = {
                "timestamp": datetime.now().isoformat(),
                "projects_count": len(projects),
                "docker": {
                    "running": docker["docker_running"],
                    "containers_up": len(docker["containers"]["running"]),
                    "containers_stopped": len(docker["containers"]["stopped"])
                },
                "postgresql": {
                    "available": dbs["postgresql_available"],
                    "databases_count": len(dbs["databases"])
                }
            }
            return [TextContent(
                type="text",
                text="SYSTEM STATUS\n" + json.dumps(status, ensure_ascii=False, indent=2)
            )]

        elif name == "compare_projects":
            project_a = arguments.get("project_a", "")
            project_b = arguments.get("project_b", "")

            exists_a, error_a, key_a, path_a = ProjectContext.validate_project(project_a)
            exists_b, error_b, key_b, path_b = ProjectContext.validate_project(project_b)

            if not exists_a:
                return [TextContent(type="text", text=error_a)]
            if not exists_b:
                return [TextContent(type="text", text=error_b)]

            info_a = get_project_info(key_a, path_a)
            info_b = get_project_info(key_b, path_b)

            comparison = (
                "\n"
                "+------------------------------------------------------------------+\n"
                "|                    PROJECT COMPARISON                            |\n"
                "+------------------------------------------------------------------+\n"
                f"| PROJECT A: {key_a:<54}|\n"
                f"| ID:        {info_a['id']:<54}|\n"
                "+------------------------------------------------------------------+\n"
                f"| PROJECT B: {key_b:<54}|\n"
                f"| ID:        {info_b['id']:<54}|\n"
                "+------------------------------------------------------------------+\n"
                "\n"
                "WARNING: These are DIFFERENT projects! Do not mix their dependencies and code!\n"
                "\n"
                f"PROJECT A ({key_a}):\n"
                f"{json.dumps(info_a, ensure_ascii=False, indent=2)}\n"
                "\n"
                f"{'=' * 70}\n"
                "\n"
                f"PROJECT B ({key_b}):\n"
                f"{json.dumps(info_b, ensure_ascii=False, indent=2)}\n"
            )
            return [TextContent(type="text", text=comparison)]

        elif name == "read_project_file":
            project_name = arguments.get("project_name", "")
            file_path = arguments.get("file_path", "")

            exists, error, key, proj_path = ProjectContext.validate_project(project_name)
            if not exists:
                return [TextContent(type="text", text=error)]

            # Security: do not read .env files with secrets
            if file_path == ".env" or file_path.endswith("/.env"):
                return [TextContent(
                    type="text",
                    text="SECURITY: Reading .env is forbidden! Use .env.example to view structure."
                )]

            full_path = proj_path / file_path

            # Path traversal protection
            try:
                full_path = full_path.resolve()
                if not str(full_path).startswith(str(PROJECTS_DIR.resolve())):
                    return [TextContent(
                        type="text",
                        text="SECURITY: Attempt to access outside projects directory!"
                    )]
            except Exception:
                return [TextContent(type="text", text="Invalid path")]

            if not full_path.exists():
                return [TextContent(
                    type="text",
                    text=f"File not found: {file_path} in project {key}"
                )]

            if not full_path.is_file():
                return [TextContent(type="text", text="Not a file")]

            # Size limit
            if full_path.stat().st_size > 100_000:
                return [TextContent(
                    type="text",
                    text="File too large (>100KB)"
                )]

            try:
                content = full_path.read_text(errors='replace')
                project_id = ProjectContext.get_project_id(key)
                return [TextContent(
                    type="text",
                    text=(
                        "\n"
                        "+------------------------------------------------------------------+\n"
                        f"| FILE:    {file_path:<55} |\n"
                        f"| PROJECT: {key:<55} |\n"
                        f"| ID:      {project_id:<55} |\n"
                        "+------------------------------------------------------------------+\n"
                        "\n"
                        f"{content}\n"
                    )
                )]
            except Exception as e:
                return [TextContent(type="text", text=f"Read error: {e}")]

        elif name == "log_session_insight":
            project_name = arguments.get("project_name", "")
            insight_type = arguments.get("insight_type", "other")
            content = arguments.get("content", "").strip()
            tags = arguments.get("tags", [])

            if not content:
                return [TextContent(type="text", text="Error: content is required")]

            exists, error, key, path = ProjectContext.validate_project(project_name)
            if not exists:
                return [TextContent(type="text", text=error)]

            append_to_daily_log(key, insight_type, content, tags)

            compile_daily_to_project(key, [{
                "type": insight_type,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "content": content,
                "tags": tags,
            }])
            update_index()

            daily_path = get_daily_log_path()
            proj_path_kb = get_project_knowledge_path(key)
            return [TextContent(
                type="text",
                text=(
                    f"✓ Insight saved for project '{key}'\n"
                    f"  Type: {insight_type}\n"
                    f"  Tags: {', '.join(tags) if tags else 'none'}\n"
                    f"  Daily log: {daily_path}\n"
                    f"  Knowledge article: {proj_path_kb}\n"
                    f"  Obsidian vault: ~/Projects/@memory/\n"
                )
            )]

        elif name == "get_project_context":
            project_name = arguments.get("project_name", "")
            exists, error, key, path = ProjectContext.validate_project(project_name)
            if not exists:
                return [TextContent(type="text", text=error)]

            knowledge = load_project_knowledge(key)
            if not knowledge:
                return [TextContent(
                    type="text",
                    text=(
                        f"No knowledge base entry found for project '{key}'.\n"
                        f"Use log_session_insight to start building the knowledge base."
                    )
                )]

            proj_info = get_project_info(key, path)
            header = (
                f"\n╔══════════════════════════════════════════════════════════════════╗\n"
                f"║ KNOWLEDGE BASE: {key:<49}║\n"
                f"║ Stack: {', '.join(proj_info['type']) or 'unknown':<59}║\n"
                f"╚══════════════════════════════════════════════════════════════════╝\n\n"
            )
            return [TextContent(type="text", text=header + knowledge)]

        elif name == "compile_knowledge":
            project_filter = arguments.get("project_name", "").strip()

            daily_path = get_daily_log_path()
            if not daily_path.exists():
                return [TextContent(
                    type="text",
                    text=f"No daily log for today ({daily_path.name}). Nothing to compile."
                )]

            content_raw = daily_path.read_text()
            entry_pattern = re.compile(
                r"## \[(\d{2}:\d{2})\] (.+?)\n\*\*Type:\*\* (.+?)  \n\*\*Tags:\*\* (.*?)  \n\n(.*?)\n\n---",
                re.DOTALL
            )

            by_project: dict[str, list] = {}
            for m in entry_pattern.finditer(content_raw):
                time_str, proj, itype, tags_raw, body = m.groups()
                if project_filter and proj != project_filter:
                    continue
                tags = [t.lstrip("#") for t in tags_raw.split() if t.startswith("#")]
                by_project.setdefault(proj, []).append({
                    "timestamp": f"{datetime.now().strftime('%Y-%m-%d')} {time_str}",
                    "type": itype,
                    "content": body.strip(),
                    "tags": tags,
                })

            if not by_project:
                msg = f"No entries found in today's log"
                if project_filter:
                    msg += f" for project '{project_filter}'"
                return [TextContent(type="text", text=msg)]

            compiled = []
            for proj, entries in by_project.items():
                file_path = compile_daily_to_project(proj, entries)
                compiled.append(f"  ✓ {proj} → {file_path} ({len(entries)} entries)")

            update_index()

            return [TextContent(
                type="text",
                text=(
                    f"Knowledge compiled successfully:\n"
                    + "\n".join(compiled)
                    + f"\n\nIndex updated: {INDEX_FILE}"
                )
            )]

        elif name == "get_project_history":
            project_name = arguments.get("project_name", "")
            date_from = arguments.get("date_from", "")
            date_to = arguments.get("date_to", "")
            include_git = arguments.get("include_git", True)
            include_insights = arguments.get("include_insights", True)
            max_commits = arguments.get("max_commits", 200)

            exists, error, key, path = ProjectContext.validate_project(project_name)
            if not exists:
                return [TextContent(type="text", text=error)]

            result = {
                "project": key,
                "date_from": date_from or "beginning",
                "date_to": date_to or "now",
                "git_commits": [],
                "memory_insights": [],
                "summary": {}
            }

            # ── Git history ────────────────────────────────────────
            if include_git and (path / ".git").exists():
                git_cmd = [
                    "git", "log",
                    "--pretty=format:%H|%ai|%an|%s",
                    "--no-merges"
                ]
                if date_from:
                    git_cmd += [f"--after={date_from}"]
                if date_to:
                    git_cmd += [f"--before={date_to} 23:59:59"]
                if max_commits and max_commits > 0:
                    git_cmd += [f"-{max_commits}"]

                try:
                    r = subprocess.run(
                        git_cmd, cwd=path,
                        capture_output=True, text=True, timeout=15
                    )
                    for line in r.stdout.strip().splitlines():
                        if not line:
                            continue
                        parts = line.split("|", 3)
                        if len(parts) == 4:
                            sha, date, author, msg = parts
                            result["git_commits"].append({
                                "sha": sha[:8],
                                "date": date[:10],
                                "time": date[11:16],
                                "author": author,
                                "message": msg
                            })
                except Exception as e:
                    result["git_error"] = str(e)

            # ── Memory insights from daily logs ────────────────────
            if include_insights and DAILY_DIR.exists():
                entry_pattern = re.compile(
                    r"## \[(\d{2}:\d{2})\] (.+?)\n\*\*Type:\*\* (.+?)  \n\*\*Tags:\*\* (.*?)  \n\n(.*?)\n\n---",
                    re.DOTALL
                )
                for log_file in sorted(DAILY_DIR.glob("*.md")):
                    log_date = log_file.stem  # YYYY-MM-DD
                    if date_from and log_date < date_from:
                        continue
                    if date_to and log_date > date_to:
                        continue
                    try:
                        content = log_file.read_text()
                        for m in entry_pattern.finditer(content):
                            time_str, proj, itype, tags_raw, body = m.groups()
                            if key not in proj and project_name not in proj:
                                continue
                            tags = [t.lstrip("#") for t in tags_raw.split() if t.startswith("#")]
                            result["memory_insights"].append({
                                "date": log_date,
                                "time": time_str,
                                "type": itype,
                                "tags": tags,
                                "content": body.strip()
                            })
                    except Exception:
                        continue

                # Also check compiled knowledge article
                knowledge_path = get_project_knowledge_path(key)
                if knowledge_path.exists():
                    result["compiled_knowledge"] = knowledge_path.read_text()

            result["summary"] = {
                "total_commits": len(result["git_commits"]),
                "total_insights": len(result["memory_insights"]),
                "has_compiled_knowledge": "compiled_knowledge" in result,
                "earliest_commit": result["git_commits"][-1]["date"] if result["git_commits"] else None,
                "latest_commit": result["git_commits"][0]["date"] if result["git_commits"] else None,
            }

            return [TextContent(
                type="text",
                text=ProjectContext.format_response(key, path, result)
            )]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error in tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {e}")]


# ==============================================================================
# MCP RESOURCES
# ==============================================================================

@server.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources (static only to avoid IDE reconnect loops)."""
    return [
        Resource(
            uri="system://status",
            name="System Status",
            description="Current system status",
            mimeType="application/json"
        ),
        Resource(
            uri="projects://list",
            name="Projects List",
            description="List of all projects",
            mimeType="application/json"
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource."""
    logger.info(f"Resource read: {uri}")

    if uri == "system://status":
        docker = get_docker_status()
        dbs = get_databases()
        return json.dumps({
            "docker": docker,
            "databases": dbs,
            "projects_count": len(ProjectContext.list_projects())
        }, ensure_ascii=False, indent=2)

    elif uri == "projects://list":
        projects = []
        for p in ProjectContext.list_projects():
            _, proj_path = ProjectContext.resolve_project(p)
            info = get_project_info(p, proj_path)
            projects.append({
                "name": p,
                "id": info["id"],
                "type": info["type"]
            })
        return json.dumps(projects, ensure_ascii=False, indent=2)

    elif uri.startswith("project://"):
        parts = uri.replace("project://", "").split("/")
        if len(parts) >= 2:
            # Restore category/name from URI-safe format
            project_key = parts[0].replace("--", "/")
            exists, error, key, path = ProjectContext.validate_project(project_key)
            if not exists:
                return json.dumps({"error": error})

            if parts[1] == "info":
                return json.dumps(get_project_info(key, path), ensure_ascii=False, indent=2)

    return json.dumps({"error": "Resource not found"})


# ==============================================================================
# MAIN
# ==============================================================================

async def main():
    """Start MCP server."""
    logger.info("Starting Project Context MCP Server")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
