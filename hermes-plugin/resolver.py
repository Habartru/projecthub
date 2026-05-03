"""Pure cwd → project resolution. No I/O except realpath()."""
from __future__ import annotations

import os
from typing import Tuple


def resolve_current_project(cwd_raw: str, projects: list[dict]) -> Tuple[str, bool]:
    """Return (project_name, is_scratch).

    Algorithm:
      1. realpath(cwd) to resolve symlinks
      2. sort projects by path length descending (longest-prefix wins)
      3. match cwd == proj_path OR cwd starts with proj_path + os.sep
      4. fallback: ("system/scratch", True)
    """
    cwd = os.path.realpath(cwd_raw)
    candidates = sorted(projects, key=lambda p: len(p.get("path", "")), reverse=True)

    for proj in candidates:
        proj_path = os.path.realpath(proj["path"])
        if cwd == proj_path or cwd.startswith(proj_path + os.sep):
            return (proj["name"], False)

    return ("system/scratch", True)
