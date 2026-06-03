"""Shared utilities for all agent nodes — LLM calls, tracing, context building."""
from __future__ import annotations

import json
import logging
import time
import urllib3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import tiktoken
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 3_000   # ~750 tokens — tight but sufficient with filtered context
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
        max_tokens=500,         # gateway hard limit is 500
        request_timeout=30,     # fail fast if gateway is stuck
        # response_format omitted — not supported by all gateway proxies;
        # system prompts already enforce "Output ONLY valid JSON"
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_base_url,
        http_client=httpx.Client(verify=False),
        http_async_client=httpx.AsyncClient(verify=False),
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

    # ── Attempt 1: direct parse ───────────────────────────────────────────
    try:
        return json.loads(raw), tokens_used
    except json.JSONDecodeError:
        pass

    # ── Attempt 2: strip markdown code fences, extract JSON object ────────
    import re as _re
    cleaned  = _re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    start    = cleaned.find("{")

    if start != -1:
        end = cleaned.rfind("}") + 1
        # If truncated (no closing "}"), pass everything from "{" to json_repair
        candidate = cleaned[start:end] if end > start else cleaned[start:]

        try:
            return json.loads(candidate), tokens_used
        except json.JSONDecodeError:
            pass

        # ── Attempt 3: json-repair ─────────────────────────────────────────
        # Handles: missing commas, trailing commas, truncated responses,
        # single quotes, unescaped characters — all common gateway issues.
        try:
            from json_repair import repair_json
            repaired = repair_json(candidate, return_objects=True)
            if isinstance(repaired, dict) and repaired:
                logger.warning(
                    "json-repair recovered LLM output (truncated=%s, len=%d)",
                    end <= start, len(candidate),
                )
                return repaired, tokens_used
        except ImportError:
            logger.warning("json-repair not installed — run: pip install json-repair==0.29.0")
        except Exception as _repair_exc:
            logger.warning("json-repair failed on truncated JSON: %s", _repair_exc)

    logger.error("All JSON parse attempts failed. Raw (first 400): %s", raw[:400])
    raise ValueError(f"LLM returned unparseable JSON: {raw[:200]}")


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
