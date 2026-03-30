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


def get_project_info(project_key: str, project_path: Path) -> dict:
    """Collect full information about a project."""
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

    # Detect project type
    if (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
        info["type"].append("python")
    if (project_path / "package.json").exists():
        info["type"].append("javascript")
    if (project_path / "Cargo.toml").exists():
        info["type"].append("rust")
    if (project_path / "go.mod").exists():
        info["type"].append("go")

    # Git info
    git_dir = project_path / ".git"
    if git_dir.exists():
        info["has_git"] = True
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            info["git_branch"] = result.stdout.strip() or "detached"
        except Exception:
            pass

    # Virtual environment
    for venv_name in [".venv", "venv"]:
        venv_path = project_path / venv_name
        if venv_path.exists():
            info["has_venv"] = True
            pyvenv_cfg = venv_path / "pyvenv.cfg"
            if pyvenv_cfg.exists():
                try:
                    content = pyvenv_cfg.read_text()
                    for line in content.splitlines():
                        if "version" in line.lower():
                            info["venv_python"] = line.split("=")[1].strip()
                            break
                except Exception:
                    pass
            break

    # Docker
    info["has_docker"] = (
        (project_path / "docker-compose.yml").exists() or
        (project_path / "docker-compose.yaml").exists() or
        (project_path / "Dockerfile").exists()
    )

    # Dependencies
    req_file = project_path / "requirements.txt"
    if req_file.exists():
        try:
            deps = []
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps.append(line)
            info["dependencies"]["python"] = deps[:20]
        except Exception:
            pass

    pkg_file = project_path / "package.json"
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text())
            info["dependencies"]["npm"] = list(pkg.get("dependencies", {}).keys())[:20]
        except Exception:
            pass

    # ENV variables (names only, NOT values!)
    for env_file in [".env.example", ".env.sample", ".env"]:
        env_path = project_path / env_file
        if env_path.exists():
            try:
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        var_name = line.split("=")[0].strip()
                        if var_name not in info["env_vars_required"]:
                            info["env_vars_required"].append(var_name)
            except Exception:
                pass

    # README
    for readme in ["README.md", "README.txt", "README"]:
        if (project_path / readme).exists():
            info["readme_exists"] = True
            break

    # Last modified time
    try:
        stat = project_path.stat()
        info["last_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except Exception:
        pass

    # File count (excluding node_modules, venv, etc.)
    try:
        count = 0
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in [
                'node_modules', '.venv', 'venv', '__pycache__',
                '.git', '.idea', '.vscode', 'dist', 'build'
            ]]
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
    """List available resources."""
    resources = [
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

    for project_key in ProjectContext.list_projects():
        # URI-safe key: replace / with --
        uri_key = project_key.replace("/", "--")
        resources.append(Resource(
            uri=f"project://{uri_key}/info",
            name=f"{project_key} Info",
            description=f"Information about project {project_key}",
            mimeType="application/json"
        ))

    return resources


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
