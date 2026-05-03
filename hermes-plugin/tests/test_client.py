"""Tests for the ProjectHub HTTP client."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_ping_returns_true_on_200():
    from client import ProjectHubClient
    with patch("httpx.Client") as MC:
        inst = MC.return_value
        inst.get.return_value = MagicMock(status_code=200)
        c = ProjectHubClient("http://x")
        assert c.ping() is True


def test_ping_returns_false_on_exception():
    from client import ProjectHubClient
    with patch("httpx.Client") as MC:
        inst = MC.return_value
        inst.get.side_effect = OSError("connection refused")
        c = ProjectHubClient("http://x")
        assert c.ping() is False


def test_remember_posts_correct_payload():
    from client import ProjectHubClient
    with patch("httpx.Client") as MC:
        inst = MC.return_value
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"status": "saved", "compiled": True}
        inst.post.return_value = resp

        c = ProjectHubClient("http://x")
        result = c.remember("p/q", "decision", "X", ["t"], session_id="s1")
        assert result["status"] == "saved"
        call = inst.post.call_args
        body = call.kwargs["json"]
        assert body["project"] == "p/q"
        assert body["insight_type"] == "decision"
        assert body["session_id"] == "s1"


def test_recall_returns_context():
    from client import ProjectHubClient
    with patch("httpx.Client") as MC:
        inst = MC.return_value
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"context": "knowledge", "exists": True}
        inst.get.return_value = resp

        c = ProjectHubClient("http://x")
        out = c.recall("p/q")
        assert out["context"] == "knowledge"


def test_list_projects_returns_list():
    from client import ProjectHubClient
    with patch("httpx.Client") as MC:
        inst = MC.return_value
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"projects": [{"name": "x", "path": "/p/x"}], "total": 1}
        inst.get.return_value = resp

        c = ProjectHubClient("http://x")
        assert c.list_projects()[0]["name"] == "x"
