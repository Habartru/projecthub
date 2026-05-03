"""Thin httpx client for ProjectHub memory endpoints.

Configurable via PROJECTHUB_URL env var (default http://127.0.0.1:8765).
All errors are converted to dict returns so the caller can show a
meaningful message to the agent without crashing.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("hermes.projecthub")


class ProjectHubClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 5.0):
        self.base_url = (base_url or os.environ.get("PROJECTHUB_URL") or "http://127.0.0.1:8765").rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ── Lifecycle ────────────────────────────────────────────────────

    def ping(self) -> bool:
        try:
            r = self._http.get("/api/health")
            return r.status_code == 200
        except Exception as e:
            logger.debug("ProjectHub ping failed: %s", e)
            return False

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass

    # ── Endpoints ────────────────────────────────────────────────────

    def list_projects(self) -> List[Dict[str, Any]]:
        try:
            r = self._http.get("/api/memory/projects")
            r.raise_for_status()
            return r.json().get("projects", [])
        except Exception as e:
            logger.warning("list_projects failed: %s", e)
            return []

    def remember(
        self,
        project: str,
        insight_type: str,
        content: str,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "hermes-projecthub-plugin/0.1",
    ) -> Dict[str, Any]:
        body = {
            "project": project,
            "insight_type": insight_type,
            "content": content,
            "tags": tags or [],
            "source": source,
        }
        if session_id:
            body["session_id"] = session_id
        if metadata:
            body["metadata"] = metadata
        try:
            r = self._http.post("/api/memory/insight", json=body)
            if r.status_code != 200:
                return {"error": f"HTTP {r.status_code}", "detail": r.text}
            return r.json()
        except Exception as e:
            return {"error": "unreachable", "detail": str(e)}

    def recall(self, project: str) -> Dict[str, Any]:
        try:
            r = self._http.get("/api/memory/context", params={"project": project})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": "unreachable", "detail": str(e)}

    def history(
        self,
        project: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_commits: int = 200,
    ) -> Dict[str, Any]:
        params = {"project": project, "max_commits": max_commits}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        try:
            r = self._http.get("/api/memory/history", params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": "unreachable", "detail": str(e)}
