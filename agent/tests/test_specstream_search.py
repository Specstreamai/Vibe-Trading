"""Offline contracts for the optional SpecStream web_search provider."""

from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.tools import web_search_tool
from src.tools._specstream_search import search_specstream


def _reply(sources):
    return io.BytesIO(json.dumps({"data": {"sources": sources}}).encode("utf-8"))


@pytest.fixture(autouse=True)
def _offline_sources(monkeypatch):
    for name in (
        "SPECSTREAM_API_KEY",
        "ALIYUN_IQS_API_KEY",
        "VIBE_TRADING_SEARCH_PARALLEL",
        "VIBE_TRADING_SEARCH_BACKENDS",
        "VIBE_TRADING_SEARCH_BING_FALLBACK",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(web_search_tool, "_sogou_search", MagicMock(return_value=[]))
    monkeypatch.setattr(web_search_tool, "_bing_cn_search", MagicMock(return_value=[]))
    monkeypatch.setattr(web_search_tool.time, "sleep", lambda *_: None)

    class DDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        text = MagicMock(return_value=[{"title": "DDGS", "href": "https://example.test/ddgs", "body": "x"}])

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=DDGS))
    return DDGS.text


def test_search_specstream_sends_bearer_get_and_maps_sources(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return _reply([
            {"title": "A", "url": "https://example.test/a", "snippet": "s" * 500},
            {"title": "no url"},
        ])

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    payload = search_specstream("nvidia revenue", 3, "sk_test")

    assert seen["url"] == "https://api.specstream.ai/v1/web-search?q=nvidia+revenue&num=3"
    assert seen["auth"] == "Bearer sk_test"
    assert payload["backends"] == "specstream"
    assert [r["url"] for r in payload["results"]] == ["https://example.test/a"]
    assert len(payload["results"][0]["snippet"]) == 300


def test_search_specstream_rejects_unexpected_shape(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: io.BytesIO(b'{"data": {}}'))
    with pytest.raises(ValueError):
        search_specstream("q", 3, "sk_test")


def test_web_search_uses_specstream_when_key_set(monkeypatch, _offline_sources):
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _reply([{"title": "A", "url": "https://example.test/a", "snippet": "hi"}]),
    )
    out = json.loads(web_search_tool.WebSearchTool().execute(query="q"))
    assert out["status"] == "ok"
    assert out["backends"] == "specstream"
    _offline_sources.assert_not_called()


def test_web_search_falls_through_when_specstream_fails(monkeypatch, _offline_sources):
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")

    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    out = json.loads(web_search_tool.WebSearchTool().execute(query="q"))
    assert out["status"] == "ok"
    assert out["results"][0]["title"] == "DDGS"


def test_web_search_ignores_specstream_without_key(monkeypatch, _offline_sources):
    forbidden = MagicMock()
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    web_search_tool.WebSearchTool().execute(query="q")
    forbidden.assert_not_called()
