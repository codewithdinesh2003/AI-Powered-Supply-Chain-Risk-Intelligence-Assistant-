"""Shared utilities for all agent nodes — LLM calls, tracing, context building."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import tiktoken
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 10_000   # ~2500 tokens — safe per-agent context window
_TIKTOKEN_ENC = None


def _get_enc():
    global _TIKTOKEN_ENC
    if _TIKTOKEN_ENC is None:
        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")  # gpt-4o encoding
    return _TIKTOKEN_ENC


def count_tokens(text: str) -> int:
    return len(_get_enc().encode(text))


# ── LLM helpers ──────────────────────────────────────────────────────────────

def _get_llm(temperature: float = 0.0) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=temperature,
        model_kwargs={"response_format": {"type": "json_object"}},
        openai_api_key=settings.openai_api_key,
    )


async def llm_json_call(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> tuple[Dict[str, Any], int]:
    """Call gpt-4o in JSON mode. Returns (parsed_dict, tokens_used)."""
    llm = _get_llm(temperature)

    # Token compression: if user_prompt exceeds threshold, truncate
    encoded = _get_enc().encode(user_prompt)
    settings = get_settings()
    max_tokens = int(settings.max_context_tokens * settings.context_compression_threshold)
    if len(encoded) > max_tokens:
        user_prompt = _get_enc().decode(encoded[:max_tokens]) + "\n[context truncated]"
        logger.warning("User prompt truncated to %d tokens.", max_tokens)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    raw = response.content.strip()

    tokens_used = count_tokens(system_prompt) + count_tokens(user_prompt) + count_tokens(raw)

    try:
        return json.loads(raw), tokens_used
    except json.JSONDecodeError:
        # Extract JSON substring if model prepended/appended text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end]), tokens_used
        logger.error("LLM did not return valid JSON: %s", raw[:200])
        raise


# ── Context builders ─────────────────────────────────────────────────────────

def build_context(
    documents: List[Dict[str, Any]],
    max_chars: int = _MAX_CONTEXT_CHARS,
    prefer_category: Optional[str] = None,
) -> str:
    """Assemble retrieved documents into a single context string.

    Documents matching *prefer_category* are placed first; the total
    character budget is capped at *max_chars*.
    """
    if not documents:
        return "No relevant historical incidents found."

    # Sort: preferred category first, then by score descending
    def sort_key(d: Dict[str, Any]) -> tuple:
        cat_match = d.get("metadata", {}).get("incident_category", "") == prefer_category
        return (not cat_match, -d.get("score", 0))

    ordered = sorted(documents, key=sort_key) if prefer_category else documents

    parts: List[str] = []
    total = 0
    for doc in ordered:
        text = doc.get("text", "")
        if total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining > 300:
                parts.append(text[:remaining] + "\n[...truncated]")
            break
        parts.append(text)
        total += len(text)

    return "\n\n" + ("─" * 60) + "\n\n".join(parts)


# ── Agent trace events ───────────────────────────────────────────────────────

def trace_event(
    agent: str,
    status: str,          # "started" | "thinking" | "completed" | "error"
    output: Optional[Dict[str, Any]] = None,
    elapsed_ms: int = 0,
    tokens: int = 0,
) -> Dict[str, Any]:
    return {
        "type": f"agent_{status}",
        "agent": agent,
        "status": status,
        "data": output or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "tokens_used": tokens,
    }
