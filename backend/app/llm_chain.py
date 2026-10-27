"""Multi-provider LLM fallback chain for query answers.

Order (configurable via LLM_PROVIDER_ORDER, comma-separated):

    opencode -> nvidia -> openrouter -> gemini

Provider notes:

* opencode — OpenCode Zen (OpenAI-compatible inference endpoint). Used
  ONLY when OPENCODE_API_KEY is configured (OpenCode Console). Without a
  key the slot is skipped quietly — the free zen tier is client-gated to
  the OpenCode app itself (external HTTP callers get 403 FreeTierError),
  so no local CLI bridge or workaround is attempted.
* nvidia — NVIDIA NIM, OpenAI-compatible (integrate.api.nvidia.com).
* openrouter — OpenRouter, OpenAI-compatible.
* gemini — existing google-generativeai SDK path (gemini_service).

Failure semantics (deliberately simple and predictable):

* exactly ONE attempt per provider per call — no inner retries, so a
  degraded provider cannot multiply request latency;
* any failure (timeout, connection error, 4xx/5xx, empty content,
  missing key/CLI) moves to the next provider with a log line;
* a provider that is simply not configured (no key / no CLI) is skipped
  quietly at debug level;
* if every provider fails, LLMUnavailableError is raised — the query
  handler maps it to 502 like the previous single-provider behaviour.

Ingestion never calls this module: the ingestion pipeline is 100%
deterministic and does not use an LLM.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import httpx

from app import config, gemini_service

log = logging.getLogger("kyro.llm")


class LLMUnavailableError(RuntimeError):
    """Every configured LLM provider failed or was unavailable."""


# --- OpenAI-compatible HTTP helper -----------------------------------------


def _post_chat(
    base_url: str, api_key: str, model: str, message: str, timeout: float
) -> str:
    resp = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": message}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content")) if choices else None
    if not content or not content.strip():
        finish = choices[0].get("finish_reason") if choices else "no-choices"
        raise RuntimeError(f"empty content (finish_reason={finish})")
    return content.strip()


# --- Providers --------------------------------------------------------------


def _opencode_chat(message: str) -> str:
    """OpenCode Zen via the Console inference endpoint (requires a key).

    The free zen tier is client-gated to the OpenCode app itself (an
    external HTTP caller gets 403 FreeTierError), so this provider is
    deliberately key-gated: without OPENCODE_API_KEY the chain skips the
    slot entirely instead of attempting a workaround.
    """
    if not config.OPENCODE_API_KEY:
        raise RuntimeError("OPENCODE_API_KEY is not configured")
    return _post_chat(
        config.OPENCODE_BASE_URL,
        config.OPENCODE_API_KEY,
        config.OPENCODE_MODEL,
        message,
        config.LLM_HTTP_TIMEOUT_S,
    )


def _nvidia_chat(message: str) -> str:
    return _post_chat(
        config.NVIDIA_BASE_URL,
        config.NVIDIA_API_KEY,
        config.NVIDIA_MODEL,
        message,
        config.LLM_HTTP_TIMEOUT_S,
    )


def _openrouter_chat(message: str) -> str:
    return _post_chat(
        config.OPENROUTER_BASE_URL,
        config.OPENROUTER_API_KEY,
        config.OPENROUTER_MODEL,
        message,
        config.LLM_HTTP_TIMEOUT_S,
    )


def _gemini_chat(message: str) -> str:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return gemini_service.chat(message)


def _opencode_available() -> bool:
    return bool(config.OPENCODE_API_KEY)


_PROVIDERS: dict[str, tuple[Callable[[str], str], Callable[[], bool]]] = {
    "opencode": (_opencode_chat, _opencode_available),
    "nvidia": (_nvidia_chat, lambda: bool(config.NVIDIA_API_KEY)),
    "openrouter": (_openrouter_chat, lambda: bool(config.OPENROUTER_API_KEY)),
    "gemini": (_gemini_chat, lambda: bool(config.GEMINI_API_KEY)),
}


def chat(message: str) -> str:
    """Ask the provider chain; return the first successful answer."""
    errors: list[str] = []
    for name in config.LLM_PROVIDER_ORDER:
        entry = _PROVIDERS.get(name)
        if entry is None:
            log.warning("llm_unknown_provider name=%s (skipped)", name)
            continue
        call, available = entry
        if not available():
            log.debug("llm_provider_skipped name=%s reason=not_configured", name)
            continue
        started = time.monotonic()
        try:
            answer = call(message)
        except Exception as exc:
            elapsed = time.monotonic() - started
            log.warning(
                "llm_provider_failed name=%s elapsed=%.1fs error=%s",
                name,
                elapsed,
                exc,
            )
            errors.append(f"{name}: {exc}")
            continue
        elapsed = time.monotonic() - started
        log.info(
            "llm_served name=%s elapsed=%.1fs order=%s",
            name,
            elapsed,
            ",".join(config.LLM_PROVIDER_ORDER),
        )
        return answer
    detail = "; ".join(errors) if errors else "no providers configured"
    raise LLMUnavailableError(f"all LLM providers failed: {detail}")
