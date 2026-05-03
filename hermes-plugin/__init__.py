"""ProjectHub memory provider for Hermes-agent.

Bridges Hermes' MemoryProvider lifecycle to ProjectHub's HTTP memory API.
The plugin is HTTP-only — it does NOT import any ProjectHub Python modules.

Activation: set `memory.provider: projecthub` in ~/.hermes/config.yaml
after this plugin is symlinked into ~/.hermes/plugins/projecthub/.

Configuration:
  PROJECTHUB_URL  default http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.projecthub")

# Hermes injects MemoryProvider at runtime when the plugin is loaded by
# Hermes' loader. For standalone testing (no Hermes installed) we provide
# a minimal stand-in so the class still subclasses something importable.
try:
    from agent.memory_provider import MemoryProvider
except ImportError:  # pragma: no cover — only when running plugin tests
    class MemoryProvider:  # type: ignore[no-redef]
        pass


class ProjectHubProvider(MemoryProvider):
    """Memory provider that routes project facts to ProjectHub vault."""

    def __init__(self) -> None:
        self._client = None
        self._client_factory = self._default_client_factory
        self._session_id: str = ""
        self._hermes_home: str = ""
        self._current_project: str = "system/scratch"
        self._is_scratch: bool = True
        self._cached_recall: Optional[str] = None

    # ── Helpers ─────────────────────────────────────────────────────

    def _default_client_factory(self):
        from client import ProjectHubClient
        return ProjectHubClient()

    def _resolve_cwd_project(self) -> tuple[str, bool]:
        from resolver import resolve_current_project
        cwd = os.environ.get("TERMINAL_CWD") or os.getcwd()
        projects = self._client.list_projects() if self._client else []
        return resolve_current_project(cwd, projects)

    # ── Required ABC ────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "projecthub"

    def is_available(self) -> bool:
        try:
            cli = self._client_factory()
            ok = cli.ping()
            if ok:
                self._client = cli  # reuse on initialize
            else:
                cli.close()
            return ok
        except Exception as e:
            logger.warning("ProjectHub plugin disabled: %s", e)
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._hermes_home = kwargs.get("hermes_home", "")
        if self._client is None:
            self._client = self._client_factory()
        try:
            self._current_project, self._is_scratch = self._resolve_cwd_project()
            cwd = os.environ.get("TERMINAL_CWD") or os.getcwd()
            logger.info(
                "ProjectHub bound to project=%s cwd=%s scratch=%s",
                self._current_project, cwd, self._is_scratch,
            )
        except Exception as e:
            logger.warning("ProjectHub cwd resolution failed: %s", e)
            self._current_project = "system/scratch"
            self._is_scratch = True

    def system_prompt_block(self) -> str:
        if self._is_scratch:
            return (
                "ProjectHub active, no project bound to cwd. Use list_all_projects "
                "via MCP if you know which project this is about, then "
                "projecthub_remember(project=<name>, ...). Otherwise insights go "
                "to system/scratch."
            )
        return (
            f"ProjectHub memory active. Project: {self._current_project}. ROUTING: "
            "project facts (decisions/bugs/patterns/stack) → projecthub_remember. "
            "User persona/preferences → built-in memory. Unsure → projecthub_remember."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        from tools import ALL_SCHEMAS
        return ALL_SCHEMAS

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if self._client is None:
            return json.dumps({"error": "ProjectHub client not initialized"})

        try:
            if tool_name == "projecthub_remember":
                project = args.get("project") or self._current_project
                result = self._client.remember(
                    project=project,
                    insight_type=args["insight_type"],
                    content=args["content"],
                    tags=args.get("tags", []),
                    session_id=self._session_id,
                    metadata={"write_origin": "projecthub_plugin"},
                )
                return json.dumps(result)

            if tool_name == "projecthub_recall":
                project = args.get("project") or self._current_project
                return json.dumps(self._client.recall(project))

            if tool_name == "projecthub_history":
                project = args.get("project") or self._current_project
                return json.dumps(self._client.history(
                    project,
                    date_from=args.get("date_from"),
                    date_to=args.get("date_to"),
                    max_commits=args.get("max_commits", 200),
                ))

            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.exception("handle_tool_call error: %s", e)
            return json.dumps({"error": "exception", "detail": str(e)})

    def shutdown(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs,
    ) -> None:
        """Update session_id; on reset, clear cache and re-resolve cwd→project."""
        self._session_id = new_session_id
        if reset:
            self._cached_recall = None
            try:
                self._current_project, self._is_scratch = self._resolve_cwd_project()
            except Exception as e:
                logger.warning("on_session_switch reset failed: %s", e)
                self._current_project = "system/scratch"
                self._is_scratch = True


def register(ctx) -> None:
    """Hermes plugin entry-point."""
    ctx.register_memory_provider(ProjectHubProvider())
