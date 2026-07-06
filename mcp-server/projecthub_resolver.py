"""Pure, dependency-free helpers for the MCP core (no `mcp` import, so they are
unit-testable in any venv):

- ``resolve_current_project`` — cwd → project (promoted from
  hermes-plugin/resolver.py so every MCP client, not just Hermes, can
  auto-resolve the project open in the current working directory).
- ``log_entry_matches_project`` — exact match of a daily-log project field to a
  project key (no substring leakage between sibling projects).

No I/O except realpath().
"""
from __future__ import annotations

import os
from typing import Optional, Tuple


def resolve_current_project(
    cwd_raw: str, projects: list[dict]
) -> Tuple[Optional[str], bool]:
    """Return (project_name, is_scratch) for a working directory.

    Algorithm:
      1. realpath(cwd) to resolve symlinks
      2. sort projects by path length descending (longest prefix wins, so the
         most specific / nested project is chosen over its container)
      3. match cwd == proj_path OR cwd starts with proj_path + os.sep
      4. fallback: (None, True)  # cwd is not inside any known project

    `projects` is a list of dicts each with at least "name" and "path".
    Malformed entries (missing/empty path, unresolvable) are skipped rather
    than raising, so one bad project can never break resolution.
    """
    try:
        cwd = os.path.realpath(cwd_raw)
    except (OSError, ValueError, TypeError):
        return None, True

    candidates = sorted(
        projects, key=lambda p: len(p.get("path", "") or ""), reverse=True
    )
    for proj in candidates:
        raw = proj.get("path", "")
        if not raw:
            continue
        try:
            proj_path = os.path.realpath(raw)
        except (OSError, ValueError, TypeError):
            continue
        if cwd == proj_path or cwd.startswith(proj_path + os.sep):
            return proj.get("name"), False

    return None, True


def log_entry_matches_project(proj_field: str, key: str) -> bool:
    """Exact match of a daily-log project field to a project key.

    Daily-log entries store the project as a wiki-link ``[[slug|category/name]]``
    where ``slug = key.replace('/', '--').replace(' ', '_')`` (older entries may
    store the bare key). Match on the exact name OR slug — never a substring — so
    that 'bringo/api' does NOT pull in insights from the sibling
    'bringo/api-server'.
    """
    field = (proj_field or "").strip()
    if field.startswith("[[") and field.endswith("]]"):
        field = field[2:-2]
    parts = [p.strip() for p in field.split("|")]
    key_slug = key.replace("/", "--").replace(" ", "_")
    return key in parts or key_slug in parts
