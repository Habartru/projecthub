"""Unit tests for the core cwd → project resolver (projecthub_resolver)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from projecthub_resolver import resolve_current_project, log_entry_matches_project


def _proj(name, path):
    return {"name": name, "path": str(path)}


def test_exact_match(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    name, scratch = resolve_current_project(str(p), [_proj("cat/proj", p)])
    assert (name, scratch) == ("cat/proj", False)


def test_subdirectory_match(tmp_path):
    p = tmp_path / "proj"
    (p / "src" / "deep").mkdir(parents=True)
    name, scratch = resolve_current_project(str(p / "src" / "deep"), [_proj("cat/proj", p)])
    assert (name, scratch) == ("cat/proj", False)


def test_no_match_is_scratch(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    name, scratch = resolve_current_project(str(other), [_proj("cat/proj", p)])
    assert (name, scratch) == (None, True)


def test_longest_prefix_wins(tmp_path):
    """A nested project must beat its container project."""
    container = tmp_path / "container"
    nested = container / "sub"
    nested.mkdir(parents=True)
    projects = [_proj("cat/container", container), _proj("cat/container/sub", nested)]
    # order should not matter; try both
    for ordered in (projects, list(reversed(projects))):
        name, scratch = resolve_current_project(str(nested / "x"), ordered)
        assert (name, scratch) == ("cat/container/sub", False)


def test_sibling_prefix_is_not_a_match(tmp_path):
    """cwd '/root/proj-two' must NOT match project '/root/proj' (os.sep guard)."""
    proj = tmp_path / "proj"
    sibling = tmp_path / "proj-two"
    proj.mkdir()
    sibling.mkdir()
    name, scratch = resolve_current_project(str(sibling), [_proj("cat/proj", proj)])
    assert (name, scratch) == (None, True)


def test_symlinked_cwd_resolves(tmp_path):
    real = tmp_path / "real_proj"
    real.mkdir()
    link = tmp_path / "link_to_proj"
    os.symlink(real, link)
    name, scratch = resolve_current_project(str(link), [_proj("cat/real_proj", real)])
    assert (name, scratch) == ("cat/real_proj", False)


def test_malformed_project_is_skipped(tmp_path):
    """A project with no path must not crash resolution of a valid one."""
    p = tmp_path / "proj"
    p.mkdir()
    projects = [{"name": "broken"}, {"name": "empty", "path": ""}, _proj("cat/proj", p)]
    name, scratch = resolve_current_project(str(p), projects)
    assert (name, scratch) == ("cat/proj", False)


def test_empty_projects_list_is_scratch(tmp_path):
    name, scratch = resolve_current_project(str(tmp_path), [])
    assert (name, scratch) == (None, True)


# --- log_entry_matches_project -------------------------------------------------

def test_log_match_wikilink_exact():
    assert log_entry_matches_project("[[bringo--api|bringo/api]]", "bringo/api") is True


def test_log_match_no_sibling_leak():
    """The bug the review caught: 'bringo/api' must NOT match 'bringo/api-server'."""
    assert log_entry_matches_project("[[bringo--api-server|bringo/api-server]]", "bringo/api") is False
    assert log_entry_matches_project("[[bringo--api|bringo/api]]", "bringo/api-server") is False


def test_log_match_bare_key():
    assert log_entry_matches_project("bringo/api", "bringo/api") is True
    assert log_entry_matches_project("bringo/api-server", "bringo/api") is False


def test_log_match_by_slug_and_spaces():
    assert log_entry_matches_project("[[bringo--api|bringo/api]]", "bringo/api") is True
    assert log_entry_matches_project(
        "[[bringo--Landings_Bringo|bringo/Landings Bringo]]", "bringo/Landings Bringo"
    ) is True


def test_log_match_empty_field():
    assert log_entry_matches_project("", "bringo/api") is False
