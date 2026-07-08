from __future__ import annotations

from pathlib import Path


ROOTS = [
    Path("agent/src/alpha_foundry"),
    Path("agent/examples/alpha_foundry_demos"),
]

FORBIDDEN_SNIPPETS = [
    "requests.",
    "httpx.",
    "urllib.request",
    "openai",
    "anthropic",
    "place_order",
    "cancel_order",
    "shell=True",
    "os.system",
    "eval(",
    "exec(",
]


def test_alpha_foundry_code_and_demos_do_not_use_live_network_llm_broker_or_shell() -> None:
    offenders: list[str] = []
    for root in ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    offenders.append(f"{path}:{snippet}")

    assert offenders == []
