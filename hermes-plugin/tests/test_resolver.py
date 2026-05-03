"""Unit tests for cwd → project resolution."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_exact_match():
    from resolver import resolve_current_project
    name, scratch = resolve_current_project(
        "/p/A", [{"name": "A", "path": "/p/A"}]
    )
    assert (name, scratch) == ("A", False)


def test_subfolder_match():
    from resolver import resolve_current_project
    name, scratch = resolve_current_project(
        "/p/A/sub/dir", [{"name": "A", "path": "/p/A"}]
    )
    assert (name, scratch) == ("A", False)


def test_sibling_with_shared_prefix_does_not_match():
    from resolver import resolve_current_project
    name, scratch = resolve_current_project(
        "/p/Aextra", [{"name": "A", "path": "/p/A"}]
    )
    assert (name, scratch) == ("system/scratch", True)


def test_longest_prefix_wins():
    from resolver import resolve_current_project
    name, scratch = resolve_current_project(
        "/m/services/auth/code",
        [
            {"name": "monorepo", "path": "/m"},
            {"name": "monorepo/services/auth", "path": "/m/services/auth"},
        ],
    )
    assert (name, scratch) == ("monorepo/services/auth", False)


def test_empty_list_returns_scratch():
    from resolver import resolve_current_project
    name, scratch = resolve_current_project("/p/A", [])
    assert (name, scratch) == ("system/scratch", True)


def test_symlink_resolution(tmp_path):
    from resolver import resolve_current_project
    real = tmp_path / "real_proj"
    real.mkdir()
    link = tmp_path / "link_proj"
    link.symlink_to(real)
    # cwd is the symlink, project path is the realpath
    name, scratch = resolve_current_project(
        str(link), [{"name": "P", "path": str(real)}]
    )
    assert (name, scratch) == ("P", False)


def test_home_returns_scratch():
    from resolver import resolve_current_project
    name, scratch = resolve_current_project(
        "/home/user", [{"name": "X", "path": "/p/X"}]
    )
    assert (name, scratch) == ("system/scratch", True)
