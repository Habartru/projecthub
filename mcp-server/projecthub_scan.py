"""Shared project-detection primitives for ProjectHub.

Single source of truth for "what counts as a project" — imported by BOTH the
FastAPI backend (backend/main.py) and the MCP server (server.py) so the
dashboard inventory and the agent-facing MCP inventory can never diverge.

Before this module the backend used a smart container-aware scan while the MCP
server used a naive 2-level scan with no filtering, so they reported different
project lists (the MCP side listed data folders like ``mp3``/``models`` and
``node_modules`` as "projects"). Both now share these predicates.
"""
from __future__ import annotations

from pathlib import Path

# Marker files that unambiguously indicate a code project.
PROJECT_MARKERS = frozenset({
    'package.json', 'requirements.txt', 'Cargo.toml', 'go.mod',
    'pom.xml', 'build.gradle', 'Makefile', 'CMakeLists.txt',
    'manage.py', 'setup.py', 'pyproject.toml',
    # extras added during the 2026-06 logic audit
    'docker-compose.yml', 'docker-compose.yaml', 'Dockerfile',
    'composer.json', 'Gemfile', 'project.godot', 'index.html',
    'tsconfig.json', 'uv.lock', 'poetry.lock', 'pnpm-lock.yaml',
    '.csproj', 'README.md', 'README.MD', 'readme.md', 'AGENTS.md', 'CLAUDE.md',
})

# Directories that are pure data / assets / build output — never projects.
DATA_DIR_NAMES = frozenset({
    'mp3', 'mp4', 'audio', 'video', 'models', 'assets', 'img', 'images',
    'scenes', 'credentials', 'backups', 'data', 'media', 'fonts', 'dumps',
    'exports', 'screenshots', 'static_data', 'tmp', 'temp',
})

# Build/cache/vendor dirs — always skipped while scanning.
SKIP_DIRS = frozenset({
    'node_modules', 'venv', '.venv', '__pycache__', 'target', 'build',
    'dist', '.git', '.idea', '.vscode', 'out', '.next', '.nuxt',
    'coverage', '.pytest_cache', '.mypy_cache', '.tox', '.ruff_cache',
    '.cache',
})

# Source-code extensions used as a fallback signal when no marker file exists.
CODE_EXTS = frozenset({
    '.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.php', '.rb',
    '.java', '.kt', '.swift', '.c', '.cpp', '.cs', '.html', '.vue',
    '.svelte', '.sh', '.lua', '.gd', '.astro', '.sql',
})


def is_project_dir(d: Path) -> bool:
    """Strong signal: directory has .git or a known marker file."""
    if (d / '.git').is_dir():
        return True
    for marker in PROJECT_MARKERS:
        if (d / marker).exists():
            return True
    return False


def looks_like_project(d: Path) -> bool:
    """Decide whether ``d`` should be listed as a project.

    A directory is a project when it has .git / a marker file, OR contains
    source files at its top level — but never when its name is a known
    data/asset/build folder.
    """
    name = d.name
    if name.startswith('.') or name in SKIP_DIRS:
        return False
    if name.lower() in DATA_DIR_NAMES:
        return False
    if is_project_dir(d):
        return True
    # Fallback: any source file directly inside → treat as project.
    try:
        for entry in d.iterdir():
            if entry.is_file() and entry.suffix.lower() in CODE_EXTS:
                return True
    except (PermissionError, OSError):
        pass
    return False


# Typical monorepo part names — a dir whose project-subdirs are mostly these is
# ONE monorepo, not a container of independent projects.
MONOREPO_PART_NAMES = frozenset({
    'frontend', 'backend', 'server', 'client', 'shared', 'app', 'api',
    'web', 'mobile', 'core', 'common', 'lib', 'libs', 'packages',
    'services', 'infra', 'deploy', 'scripts', 'tools', 'docs',
    'mcp-server', 'collector', 'animation', 'dev',
})


def is_container_dir(d: Path) -> bool:
    """Whether ``d`` is a container of independent projects (not a monorepo).

    True only when ``d`` itself is not a project but holds >=2 independent
    project subdirs whose names are neither monorepo-parts nor variants of the
    parent name.
    """
    if is_project_dir(d):
        return False
    try:
        subdirs = [s for s in d.iterdir() if s.is_dir() and not s.name.startswith('.')]
    except (PermissionError, OSError):
        return False
    if not subdirs:
        return False
    project_subdirs = [s for s in subdirs if is_project_dir(s)]
    if not project_subdirs:
        return False
    monorepo_count = sum(1 for s in project_subdirs if s.name.lower() in MONOREPO_PART_NAMES)
    if monorepo_count > len(project_subdirs) / 2:
        return False
    parent_name = d.name.lower()
    name_shared = sum(1 for s in project_subdirs
                      if parent_name in s.name.lower() or s.name.lower() in parent_name)
    if name_shared > len(project_subdirs) / 2:
        return False
    return (len(project_subdirs) - name_shared) >= 2


def read_description(d: Path, max_len: int = 200) -> str:
    """Extract a one-line description from a project's README, if any.

    Returns the first non-empty, non-heading, non-badge line. Empty string
    when no usable README is found.
    """
    for readme in ('README.md', 'README.MD', 'readme.md', 'Readme.md'):
        p = d / readme
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except (OSError, UnicodeError):
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith('#'):            # heading
                continue
            if line.startswith(('![', '[!', '<', '|', '---', '===', '```', '>')):
                continue                          # badge / html / table / rule
            line = line.lstrip('-*> ').strip()
            if len(line) < 8:
                continue
            return line[:max_len]
        return ""
    return ""
