"""Thin Anthropic SDK wrapper. Pinned model versions, simple retry, logging.

We deliberately do not abstract the SDK behind anything fancy — the entire
pipeline calls this same `complete()` for every stage, with different
system/user prompts.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import anthropic


@dataclass
class CompletionResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    latency_s: float
    stop_reason: Optional[str]


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def complete(
    *,
    model: str,
    system: str,
    user,
    max_tokens: int = 8192,
    temperature: float = 0.9,
    max_retries: int = 3,
) -> CompletionResult:
    """One-shot text completion. Retries on transient errors with exponential
    backoff (2s, 4s, 8s).

    `user` may be either:
      - a plain string (single text block, no caching), or
      - a list of content blocks (e.g., for prompt caching: mark a block
        with `cache_control={"type": "ephemeral"}` to cache it for the
        next 5 minutes of identical-prefix calls).
    """
    client = get_client()
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            # Use streaming for all calls. The SDK refuses non-streaming
            # requests with `max_tokens` large enough that the expected
            # duration would exceed 10 minutes (true at our 32K/64K caps).
            # Streaming has no such limit; the context manager accumulates
            # the final message just like create() would have returned.
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            # opus-4-7 rejects `temperature` (only the default is accepted).
            # Earlier sonnet models took it; pass it through only for non-opus.
            if not model.startswith("claude-opus-4-7"):
                kwargs["temperature"] = temperature
            with client.messages.stream(**kwargs) as stream:
                final = stream.get_final_message()
            latency = time.time() - t0
            text = "".join(
                block.text for block in final.content if hasattr(block, "text")
            )
            usage = final.usage
            return CompletionResult(
                text=text,
                model=final.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                latency_s=latency,
                stop_reason=final.stop_reason,
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as e:
            last_exc = e
            backoff = 2 ** (attempt + 1)
            print(f"  anthropic error (attempt {attempt + 1}/{max_retries}): {e}; sleep {backoff}s")
            time.sleep(backoff)
    assert last_exc is not None
    raise last_exc
