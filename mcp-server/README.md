# Project Context MCP Server

MCP server that provides AI agents (Claude Code, Windsurf/Cascade) with information about all projects organized under `~/Projects/@category/project_name`.

## Project Structure

The server scans `~/Projects/` for category directories prefixed with `@`, then lists projects within each category:

```
~/Projects/
  @infrastructure/
    @projecthub/
    settingsOS/
  @web/
    mysite/
    landing/
  @ml/
    classifier/
```

Projects are identified as `category/project_name` (e.g. `infrastructure/@projecthub`, `web/mysite`).
You can also use just the project name if it is unique across categories.

## Features

### Anti-hallucination and confusion protection

1. **Unique project IDs** -- each project gets a unique 8-character ID
2. **Explicit labels** -- every response includes a header with project name and ID
3. **Validation** -- project existence is checked before any operation
4. **Available projects list** -- shown on error so the agent knows what exists
5. **Read-only** -- no modifications, only reading

### Security

- Will not read `.env` files (only `.env.example`)
- Path traversal protection
- All requests are logged
- File size limits (100KB max)

## Available Tools

| Tool | Description |
|------|-------------|
| `list_all_projects` | List all projects with basic info |
| `get_project_details` | Full information about a specific project |
| `get_project_dependencies` | Project dependencies (requirements.txt, package.json) |
| `get_docker_status` | Docker container status |
| `get_databases` | PostgreSQL databases (uses current OS user auth) |
| `get_system_status` | Overall system status |
| `compare_projects` | Compare two projects side by side |
| `read_project_file` | Read a file from a project |

## Installation

```bash
./install.sh
```

## Configuration

### Claude Code

```bash
claude mcp add project-context /path/to/mcp-server/.venv/bin/python /path/to/mcp-server/server.py
```

Or add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "project-context": {
      "command": "/home/habart/Projects/@infrastructure/@projecthub/mcp-server/.venv/bin/python",
      "args": ["/home/habart/Projects/@infrastructure/@projecthub/mcp-server/server.py"]
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "project-context": {
      "command": "/home/habart/Projects/@infrastructure/@projecthub/mcp-server/.venv/bin/python",
      "args": ["/home/habart/Projects/@infrastructure/@projecthub/mcp-server/server.py"]
    }
  }
}
```

## Logs

Logs are saved to: `~/.config/project-context/mcp-server.log`

## Usage Example

```
Agent: Using tool list_all_projects to get project list...

{
  "total_count": 12,
  "projects": [
    {"name": "infrastructure/@projecthub", "id": "a1b2c3d4", "type": ["python"], ...},
    {"name": "web/mysite", "id": "e5f6g7h8", "type": ["javascript"], ...},
    ...
  ],
  "hint": "Use EXACT project names (category/name) in subsequent requests."
}

Agent: Getting details for project web/mysite...

+------------------------------------------------------------------+
| PROJECT: web/mysite                                              |
| ID:      e5f6g7h8                                                |
| Path:    ~/Projects/@web/mysite                                  |
+------------------------------------------------------------------+
{
  "name": "web/mysite",
  "type": ["javascript"],
  "has_venv": false,
  ...
}
```

## Important Notes for AI Agents

- ALWAYS check the project ID before working with it
- DO NOT MIX dependencies and code from different projects
- USE `list_all_projects` if unsure which projects exist
- Projects can be referenced by `category/name` or just `name` (if unique)
