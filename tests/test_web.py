"""Web retrieval mode — no network, the provider call is stubbed:

    backend/.venv/bin/python tests/test_web.py

Covers the contract: OFF -> a readable status (never a provider call), ON -> the
same event shapes as the expert loop (delta, web-origin sources, usage), and an
unsupported endpoint degrades to a message instead of an exception. The bench
can never reach this path — only the chat route maps retrieval="web" to it.
"""

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key-never-called")

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import llm_client, pipeline  # noqa: E402
from app.config import settings  # noqa: E402


def _collect(**kw):
    async def main():
        return [ev async for ev in pipeline.web_answer_stream(
            [{"role": "user", "content": "what is CET1?"}], **kw)]
    return asyncio.run(main())


def _set_web(value):
    object.__setattr__(settings, "web_search", value)


def test_off_by_default_is_a_message_not_a_call():
    _set_web(False)
    called = []
    orig = llm_client.web_chat
    llm_client.web_chat = lambda *a, **k: called.append(1)
    try:
        events = _collect()
    finally:
        llm_client.web_chat = orig
    assert len(events) == 1 and events[0]["stage"] == "error"
    assert "WEB_SEARCH=on" in events[0]["detail"]
    assert not called, "disabled web mode must never reach the provider"
    print("  off: disabled mode -> readable status, zero provider calls ✓")


def test_on_streams_answer_sources_usage():
    _set_web(True)
    orig = llm_client.web_chat
    llm_client.web_chat = lambda msgs, model=None: (
        "CET1 is core capital.",
        [{"title": "BIS — CET1", "url": "https://bis.org/cet1"}],
        {"prompt_tokens": 10, "completion_tokens": 5, "cached_tokens": 0})
    try:
        events = _collect()
    finally:
        llm_client.web_chat = orig
    kinds = [e["type"] for e in events]
    assert kinds == ["status", "delta", "sources", "usage"], kinds
    src = events[2]["sources"][0]
    assert src["origin"] == "web" and src["citation"] == "BIS — CET1" \
        and src["text"] == "https://bis.org/cet1"
    assert events[1]["text"] == "CET1 is core capital."
    print("  on: delta + web-origin sources + usage, expert-loop event shapes ✓")


def test_unsupported_endpoint_degrades_readably():
    _set_web(True)

    def boom(msgs, model=None):
        raise RuntimeError("Web search is not available on this endpoint (404).")
    orig = llm_client.web_chat
    llm_client.web_chat = boom
    try:
        events = _collect()
    finally:
        llm_client.web_chat = orig
    assert events[-1]["stage"] == "error" and "not available" in events[-1]["detail"]
    print("  gateway: unsupported tool -> message, never an exception ✓")


TESTS = [test_off_by_default_is_a_message_not_a_call,
         test_on_streams_answer_sources_usage,
         test_unsupported_endpoint_degrades_readably]

if __name__ == "__main__":
    failed = 0
    print("running web-mode tests…")
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
