"""Optional web search through the SpecStream Search API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from src.security.scanner import with_security_warnings

_SEARCH_URL = "https://api.specstream.ai/v1/web-search"
_TIMEOUT_SECONDS = 15
_MAX_SNIPPET_CHARS = 300


def search_specstream(query: str, max_results: int, api_key: str) -> dict[str, Any]:
    """Search with SpecStream and return the existing web_search result envelope.

    Args:
        query: Validated search query.
        max_results: Validated result count, between one and ten.
        api_key: SpecStream API key, sent as a Bearer token.

    Returns:
        A success envelope, including security warnings on external content.

    Raises:
        ValueError: The response does not match the search result contract.
    """
    url = _SEARCH_URL + "?" + urllib.parse.urlencode({"q": query, "num": max_results})
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read().decode("utf-8"))

    data = body.get("data") if isinstance(body, dict) else None
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list):
        raise ValueError("SpecStream response has no data.sources list")

    results: list[dict[str, str]] = []
    for item in sources:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str) or not item["url"]:
            continue
        results.append({
            "title": str(item.get("title") or ""),
            "url": item["url"],
            "snippet": str(item.get("snippet") or "")[:_MAX_SNIPPET_CHARS],
        })
        if len(results) >= max_results:
            break

    payload = {"status": "ok", "query": query, "backends": "specstream", "results": results}
    return with_security_warnings(payload, fields=("results.*.title", "results.*.snippet"))
