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

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return cached project knowledge as context for the upcoming turn.

        Cached after the first call per session — knowledge base is static
        within a session.
        """
        if self._is_scratch:
            return ""
        if self._cached_recall is not None:
            return self._cached_recall
        try:
            data = self._client.recall(self._current_project)
            text = data.get("context", "") if isinstance(data, dict) else ""
            if text:
                self._cached_recall = (
                    f"<projecthub_recall project='{self._current_project}'>\n"
                    f"{text}\n"
                    f"</projecthub_recall>"
                )
            else:
                self._cached_recall = ""
            return self._cached_recall
        except Exception as e:
            logger.warning("prefetch failed: %s", e)
            self._cached_recall = ""
            return ""

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror built-in MEMORY.md writes to ProjectHub if they look project-scoped."""
        if self._is_scratch or not self._client:
            return
        meta = metadata or {}
        if meta.get("write_origin") == "projecthub_plugin":
            return  # avoid loops — our own writes coming back in
        if action != "add" or target != "memory":
            return
        if self._looks_project_scoped(content):
            try:
                self._client.remember(
                    project=self._current_project,
                    insight_type="other",
                    content=content[:4000],
                    tags=["mirrored-from-builtin"],
                    session_id=self._session_id,
                    metadata={"write_origin": "mirror_from_builtin"},
                )
            except Exception as e:
                logger.warning("mirror failed: %s", e)

    def _looks_project_scoped(self, content: str) -> bool:
        """Heuristic: does this content reference the current project or cwd?"""
        if not content:
            return False
        cwd = os.environ.get("TERMINAL_CWD") or os.getcwd()
        signals = [self._current_project.split("/")[-1], self._current_project, cwd]
        return any(s and s in content for s in signals)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Run the auxiliary curator over the session and POST 1-3 insights.

        Failures are swallowed — this is post-hoc; we never break Hermes shutdown.
        """
        if self._is_scratch or not self._client or not messages:
            return
        try:
            insights = self._run_curator(messages)
        except Exception as e:
            logger.warning("curator failed: %s", e)
            return
        for ins in insights[:3]:
            try:
                tags = list(ins.get("tags", [])) + ["auto-curated"]
                self._client.remember(
                    project=self._current_project,
                    insight_type=ins.get("insight_type", "session_summary"),
                    content=ins["content"][:4000],
                    tags=tags,
                    session_id=self._session_id,
                    metadata={"write_origin": "curator", "auto_curated": True},
                )
            except Exception as e:
                logger.warning("curator post failed: %s", e)

    def _run_curator(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Call Hermes' auxiliary.curator LLM client to extract insights.

        This is the ONE place the plugin reaches into Hermes internals.
        Hermes config field: auxiliary.curator (already configured).

        NOTE: the exact import path may need adjustment when integrated with
        the running Hermes — this is flagged as an open question in the spec.
        Tests mock this method directly so the import is only attempted at
        runtime inside Hermes.
        """
        try:
            from agent.auxiliary import get_curator_client  # type: ignore
        except ImportError as e:
            logger.warning("curator client import failed: %s", e)
            return []
        client = get_curator_client()
        prompt = (
            "Review the conversation below and extract 1-3 reusable technical "
            "insights for project=" + self._current_project + ". For each, "
            "return JSON with fields: insight_type (decision|bug|pattern|gotcha|"
            "stack|qa|other), content (1-2 sentences, specific and actionable), "
            "tags (list of strings). Skip persona/preference items. If nothing "
            "is worth saving, return an empty list.\n\n"
            "Output strict JSON: {\"insights\": [...]}.\n\n"
            "Conversation:\n"
            + json.dumps(messages, ensure_ascii=False)[:24000]
        )
        raw = client.complete(prompt, response_format="json")
        try:
            data = json.loads(raw)
            return data.get("insights", []) if isinstance(data, dict) else []
        except Exception:
            return []

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
