"""Tests for MCP server's subdir-aware project detection.

Stubs out `mcp.*` imports so the server module can be loaded in the backend
venv (which doesn't have the `mcp` package). Only pure-Python helpers are
exercised — no MCP protocol interaction.
"""
import json
import sys
import types
from pathlib import Path


def _import_server_module():
    """Load mcp-server/server.py with stubbed mcp.* imports."""
    for name in ("mcp", "mcp.server", "mcp.server.stdio", "mcp.types"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    mcp_server_mod = sys.modules["mcp.server"]
    mcp_stdio_mod = sys.modules["mcp.server.stdio"]
    mcp_types_mod = sys.modules["mcp.types"]

    class _Server:
        """Generic MCP server stub: every attribute is a decorator factory."""
        def __init__(self, *_a, **_kw):
            pass
        def __getattr__(self, _name):
            # .list_tools(), .call_tool(), .list_resources(), .read_resource(), ...
            return lambda: (lambda f: f)

    def _stdio_server(): pass

    class _Stub: pass

    mcp_server_mod.Server = _Server
    mcp_stdio_mod.stdio_server = _stdio_server
    for attr in ("Tool", "TextContent", "Resource", "ResourceTemplate"):
        setattr(mcp_types_mod, attr, _Stub)

    root = Path(__file__).resolve().parents[2]
    mcp_server_dir = root / "mcp-server"
    sys.path.insert(0, str(mcp_server_dir))

    if "server" in sys.modules:
        del sys.modules["server"]
    import importlib.util
    spec = importlib.util.spec_from_file_location("server", mcp_server_dir / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── _walk_markers ────────────────────────────────────────────────────────────

def test_walk_markers_empty_dir(tmp_path):
    server = _import_server_module()
    result = server._walk_markers(tmp_path)
    assert result["git_dirs"] == []
    assert result["venv_dirs"] == []
    assert result["docker_files"] == []
    assert result["marker_paths"] == {}
    assert result["readme_paths"] == []
    assert result["env_files"] == []


def test_walk_markers_root_only(tmp_path):
    server = _import_server_module()
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "Dockerfile").write_text("FROM scratch")
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / ".env.example").write_text("API_KEY=")
    (tmp_path / ".git").mkdir()
    result = server._walk_markers(tmp_path)
    assert "package.json" in result["marker_paths"]
    assert len(result["docker_files"]) == 1
    assert len(result["readme_paths"]) == 1
    assert len(result["env_files"]) == 1
    assert len(result["git_dirs"]) == 1


def test_walk_markers_subdir_git(tmp_path):
    server = _import_server_module()
    sub = tmp_path / "secscan"
    sub.mkdir()
    (sub / ".git").mkdir()
    (sub / "README.md").write_text("sec")
    result = server._walk_markers(tmp_path)
    assert len(result["git_dirs"]) == 1
    assert result["git_dirs"][0].parent == sub


def test_walk_markers_deep_dockerfile(tmp_path):
    """Dockerfile at depth 2 should be found with default max_depth=3."""
    server = _import_server_module()
    sub = tmp_path / "secscan" / "backend"
    sub.mkdir(parents=True)
    (sub / "Dockerfile").write_text("FROM python:3.12")
    (sub / "requirements.txt").write_text("fastapi")
    result = server._walk_markers(tmp_path)
    assert len(result["docker_files"]) == 1
    assert "requirements.txt" in result["marker_paths"]


def test_walk_markers_skips_node_modules(tmp_path):
    server = _import_server_module()
    nm = tmp_path / "node_modules" / "axios"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text('{"name":"axios"}')
    (tmp_path / "package.json").write_text('{"name":"root"}')
    result = server._walk_markers(tmp_path)
    assert result["marker_paths"]["package.json"].parent == tmp_path


def test_walk_markers_depth_limit(tmp_path):
    server = _import_server_module()
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "package.json").write_text("{}")
    result = server._walk_markers(tmp_path, max_depth=3)
    assert "package.json" not in result["marker_paths"]


def test_walk_markers_venv_detection(tmp_path):
    server = _import_server_module()
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("version = 3.12.0\n")
    (venv / "lib").mkdir()
    (venv / "lib" / "site.py").write_text("# should NOT be descended into")
    result = server._walk_markers(tmp_path)
    assert len(result["venv_dirs"]) == 1


# ── get_project_info ────────────────────────────────────────────────────────

def test_get_project_info_secscan_like(tmp_path):
    """Integration test: mimics SecScan structure — no markers at root,
    full stack in secscan/{backend,frontend,docker}."""
    server = _import_server_module()
    root = tmp_path / "uyaz"
    root.mkdir()
    (root / "README.md").write_text("master project")
    (root / "PRD_PRODUCTION.md").write_text("spec")

    backend = root / "secscan" / "backend"
    frontend = root / "secscan" / "frontend"
    docker = root / "secscan" / "docker"
    backend.mkdir(parents=True)
    frontend.mkdir(parents=True)
    docker.mkdir(parents=True)

    (backend / "requirements.txt").write_text("fastapi==0.115.0\npydantic\n")
    (backend / "Dockerfile").write_text("FROM python:3.12")
    (frontend / "package.json").write_text(json.dumps({
        "dependencies": {"nuxt": "^3.0.0", "vue": "^3.0.0"}
    }))
    (docker / "docker-compose.yml").write_text("version: '3'")

    info = server.get_project_info("надо_доделать/uyaz", root)

    assert info["exists"] is True
    assert "python" in info["type"]
    assert "javascript" in info["type"]
    assert info["has_docker"] is True
    assert info["readme_exists"] is True
    assert "python" in info["dependencies"]
    assert any("fastapi" in d for d in info["dependencies"]["python"])
    assert "npm" in info["dependencies"]
    assert "nuxt" in info["dependencies"]["npm"]


def test_get_project_info_preserves_empty_for_missing(tmp_path):
    server = _import_server_module()
    missing = tmp_path / "nope"
    info = server.get_project_info("fake/nope", missing)
    assert info["exists"] is False
    assert info["has_git"] is False
    assert info["type"] == []


def test_get_project_info_root_markers_still_work(tmp_path):
    """Regression: root-only layout must still be detected as before."""
    server = _import_server_module()
    (tmp_path / "requirements.txt").write_text("django\n")
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
    (tmp_path / "README.md").write_text("hi")
    info = server.get_project_info("test/root", tmp_path)
    assert "python" in info["type"]
    assert "javascript" in info["type"]
    assert info["readme_exists"] is True
    assert info["dependencies"]["python"] == ["django"]
    assert info["dependencies"]["npm"] == ["react"]


def test_get_project_info_git_subdir(tmp_path):
    """.git inside a subdir should still set has_git=True."""
    server = _import_server_module()
    sub = tmp_path / "myproject"
    sub.mkdir()
    (sub / ".git").mkdir()
    (sub / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    info = server.get_project_info("test/gitsub", tmp_path)
    assert info["has_git"] is True
