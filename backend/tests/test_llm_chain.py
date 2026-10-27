"""LLM provider fallback chain (app/llm_chain.py).

Pure-logic tests with fake providers — no network, no subprocesses:
  * order is honoured (first success wins)
  * a failing provider falls through to the next one
  * all providers failing raises LLMUnavailableError
  * unconfigured providers are skipped, not attempted
  * unknown provider names are skipped
"""

from __future__ import annotations

import pytest

from app import config, llm_chain


class _Recorder:
    def __init__(self, *, answer: str | None = None, fail: str | None = None):
        self.answer = answer
        self.fail = fail
        self.calls = 0

    def __call__(self, message: str) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.fail)
        return self.answer or ""


@pytest.fixture
def chain(monkeypatch):
    """Install fake providers + capture the configured order."""

    class _Chain:
        def __init__(self) -> None:
            self.recorders: dict[str, _Recorder] = {}

        def install(
            self,
            name: str,
            *,
            answer: str | None = None,
            fail: str | None = None,
            configured: bool = True,
        ) -> _Recorder:
            rec = _Recorder(answer=answer, fail=fail)
            llm_chain._PROVIDERS[name] = (rec, lambda c=configured: c)
            self.recorders[name] = rec
            return rec

        def set_order(self, *names: str) -> None:
            monkeypatch.setattr(config, "LLM_PROVIDER_ORDER", list(names))

    return _Chain()


def test_first_provider_wins(chain):
    a = chain.install("opencode", answer="from-opencode")
    b = chain.install("nvidia", answer="from-nvidia")
    chain.set_order("opencode", "nvidia")

    assert llm_chain.chat("q") == "from-opencode"
    assert a.calls == 1
    assert b.calls == 0


def test_falls_through_on_failure(chain):
    chain.install("opencode", fail="403 free tier")
    b = chain.install("nvidia", answer="from-nvidia")
    chain.set_order("opencode", "nvidia", "gemini")

    assert llm_chain.chat("q") == "from-nvidia"
    assert b.calls == 1


def test_all_failing_raises(chain):
    chain.install("opencode", fail="boom-1")
    chain.install("nvidia", fail="boom-2")
    chain.set_order("opencode", "nvidia")

    with pytest.raises(llm_chain.LLMUnavailableError) as excinfo:
        llm_chain.chat("q")
    assert "boom-1" in str(excinfo.value)
    assert "boom-2" in str(excinfo.value)


def test_unconfigured_provider_is_skipped(chain):
    chain.install("opencode", answer="unused", configured=False)
    b = chain.install("openrouter", answer="from-router")
    chain.set_order("opencode", "openrouter")

    assert llm_chain.chat("q") == "from-router"
    # skipped provider never invoked
    assert chain.recorders["opencode"].calls == 0
    assert b.calls == 1


def test_unknown_provider_name_skipped(chain):
    b = chain.install("gemini", answer="from-gemini")
    chain.set_order("does-not-exist", "gemini")

    assert llm_chain.chat("q") == "from-gemini"
    assert b.calls == 1


def test_empty_configured_order_raises(chain):
    chain.install("gemini", answer="unused")
    chain.set_order()

    with pytest.raises(llm_chain.LLMUnavailableError):
        llm_chain.chat("q")
