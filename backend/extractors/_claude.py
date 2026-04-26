"""Shared helpers for talking to Claude and parsing JSON outputs."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from anthropic import Anthropic

from backend.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

log = logging.getLogger(__name__)

_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    """Lazy singleton for the Anthropic client."""
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Configure it in .env before calling Claude."
            )
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` fencing or stray prose around a JSON blob."""
    text = text.strip()
    if text.startswith("```"):
        # remove first fence line and trailing fence
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()

    # Some responses still wrap JSON in narration. Find the first [ or { and last ] or }.
    if not (text.startswith("[") or text.startswith("{")):
        match = re.search(r"[\[{]", text)
        if match:
            text = text[match.start() :]
    if text and not (text.endswith("]") or text.endswith("}")):
        for closer in ("]", "}"):
            idx = text.rfind(closer)
            if idx != -1:
                text = text[: idx + 1]
                break
    return text


def call_claude_json(
    prompt: str,
    *,
    system: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    model: Optional[str] = None,
) -> Any:
    """Call Claude and parse the response as JSON.

    Returns the parsed list/dict. Raises on unparseable output.
    """
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": model or CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    raw = response.content[0].text  # type: ignore[attr-defined]
    cleaned = _strip_fences(raw)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("Could not parse Claude JSON output: %s", exc)
        log.debug("Raw output: %s", raw)
        # Attempt a salvage by trimming trailing commas
        salvaged = re.sub(r",\s*([\]}])", r"\1", cleaned)
        return json.loads(salvaged)
