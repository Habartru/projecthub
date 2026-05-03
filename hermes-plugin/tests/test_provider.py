"""Tests for ProjectHubProvider lifecycle and dispatch."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TERMINAL_CWD", raising=False)
    # Direct import path-style — see explanation below
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_hp_init", str(Path(__file__).parent.parent / "__init__.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ProjectHubProvider()


def test_name(provider):
    assert provider.name == "projecthub"


def test_is_available_true_when_backend_pings(provider):
    with patch.object(provider, "_client_factory") as cf:
        cli = MagicMock()
        cli.ping.return_value = True
        cf.return_value = cli
        assert provider.is_available() is True


def test_is_available_false_when_backend_down(provider):
    with patch.object(provider, "_client_factory") as cf:
        cli = MagicMock()
        cli.ping.return_value = False
        cf.return_value = cli
        assert provider.is_available() is False


def test_initialize_resolves_project_to_scratch(provider, tmp_path):
    with patch.object(provider, "_client_factory") as cf:
        cli = MagicMock()
        cli.list_projects.return_value = []
        cf.return_value = cli
        provider.initialize("sess123", hermes_home=str(tmp_path), platform="cli")
    assert provider._current_project == "system/scratch"
    assert provider._is_scratch is True


def test_initialize_resolves_project_match(provider, tmp_path, monkeypatch):
    proj_dir = tmp_path / "myproj"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)
    with patch.object(provider, "_client_factory") as cf:
        cli = MagicMock()
        cli.list_projects.return_value = [{"name": "x/myproj", "path": str(proj_dir)}]
        cf.return_value = cli
        provider.initialize("sess123", hermes_home=str(tmp_path), platform="cli")
    assert provider._current_project == "x/myproj"
    assert provider._is_scratch is False


def test_system_prompt_block_bound_variant(provider):
    provider._current_project = "x/y"
    provider._is_scratch = False
    text = provider.system_prompt_block()
    assert "x/y" in text
    assert "projecthub_remember" in text
    assert len(text) <= 300


def test_system_prompt_block_scratch_variant(provider):
    provider._current_project = "system/scratch"
    provider._is_scratch = True
    text = provider.system_prompt_block()
    assert "scratch" in text.lower() or "no project" in text.lower()
    assert len(text) <= 320  # scratch variant slightly longer is OK


def test_get_tool_schemas_returns_three(provider):
    schemas = provider.get_tool_schemas()
    names = [s["name"] for s in schemas]
    assert names == ["projecthub_remember", "projecthub_recall", "projecthub_history"]


def test_handle_remember_dispatches_with_current_project(provider):
    provider._current_project = "x/y"
    provider._session_id = "s"
    cli = MagicMock()
    cli.remember.return_value = {"status": "saved"}
    provider._client = cli

    result = provider.handle_tool_call(
        "projecthub_remember",
        {"insight_type": "decision", "content": "Pick X."},
    )
    parsed = json.loads(result)
    assert parsed["status"] == "saved"
    cli.remember.assert_called_once()
    kwargs = cli.remember.call_args.kwargs
    args = cli.remember.call_args.args
    # Provider must pass current_project — accept either positional or keyword
    project_arg = args[0] if args else kwargs.get("project")
    assert project_arg == "x/y"


def test_handle_remember_respects_explicit_project(provider):
    provider._current_project = "x/y"
    cli = MagicMock()
    cli.remember.return_value = {"status": "saved"}
    provider._client = cli

    provider.handle_tool_call(
        "projecthub_remember",
        {"insight_type": "decision", "content": "z", "project": "other/proj"},
    )
    kwargs = cli.remember.call_args.kwargs
    args = cli.remember.call_args.args
    project_arg = args[0] if args else kwargs.get("project")
    assert project_arg == "other/proj"


def test_on_session_switch_reset_re_resolves(provider, tmp_path, monkeypatch):
    """When reset=True, plugin must clear cache and re-resolve cwd."""
    monkeypatch.chdir(tmp_path)
    cli = MagicMock()
    cli.list_projects.return_value = []
    provider._client = cli
    provider._current_project = "old/project"
    provider._is_scratch = False
    provider._cached_recall = "old cached"

    provider.on_session_switch("new_sess", reset=True)
    assert provider._session_id == "new_sess"
    assert provider._current_project == "system/scratch"
    assert provider._is_scratch is True
    assert provider._cached_recall is None


def test_on_session_switch_no_reset_keeps_state(provider):
    """reset=False: only session_id rotates; project + cache stay."""
    provider._current_project = "kept/project"
    provider._is_scratch = False
    provider._cached_recall = "still here"
    provider._session_id = "old"

    provider.on_session_switch("new", reset=False)
    assert provider._session_id == "new"
    assert provider._current_project == "kept/project"
    assert provider._is_scratch is False
    assert provider._cached_recall == "still here"
