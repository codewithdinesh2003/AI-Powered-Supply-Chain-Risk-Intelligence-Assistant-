from __future__ import annotations

import logging
from typing import List

import tiktoken

logger = logging.getLogger(__name__)

_ENC = None


def _get_enc() -> tiktoken.Encoding:
    global _ENC
    if _ENC is None:
        _ENC = tiktoken.get_encoding("cl100k_base")
    return _ENC


def count_tokens(text: str) -> int:
    return len(_get_enc().encode(text))


def count_messages_tokens(messages: List[dict]) -> int:
    total = 0
    for m in messages:
        total += count_tokens(m.get("content", ""))
        total += 4  # per-message overhead
    return total + 2  # reply priming


def compress_to_token_budget(
    texts: List[str],
    budget: int,
    separator: str = "\n\n---\n\n",
) -> str:
    """Concatenate texts until we hit the token budget, then truncate the last."""
    enc = _get_enc()
    parts: List[str] = []
    used = 0

    for text in texts:
        tokens = enc.encode(text)
        remaining = budget - used
        if remaining <= 0:
            break
        if len(tokens) <= remaining:
            parts.append(text)
            used += len(tokens)
        else:
            # Truncate this text to fit
            truncated = enc.decode(tokens[:remaining])
            parts.append(truncated + "\n[...truncated to fit context budget]")
            used += remaining
            break

    return separator.join(parts)


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o") -> float:
    """Rough cost estimate. Prices as of mid-2024."""
    pricing = {
        "gpt-4o":            (0.005, 0.015),    # per 1k tokens (input, output)
        "gpt-4o-mini":       (0.00015, 0.0006),
        "text-embedding-3-small": (0.00002, 0.0),
    }
    input_price, output_price = pricing.get(model, (0.005, 0.015))
    return (prompt_tokens / 1000) * input_price + (completion_tokens / 1000) * output_price
