"""Architecture invariants for the live mandate gate.

The live safety layer must remain a boundary check around live-write actions,
not a global replacement for ToolRegistry or the session runtime.
"""

from __future__ import annotations

import inspect

from src.agent.tools import ToolRegistry


FORBIDDEN_REGISTRY_WRAPPERS = (
    "GovernedToolRegistry",
    "govern_registry",
    "IRRAGLStack",
    "ToolRegistryWrapper",
)


def _assert_no_registry_wrapper(module) -> None:
    source = inspect.getsource(module)
    for forbidden in FORBIDDEN_REGISTRY_WRAPPERS:
        assert forbidden not in source, (
            f"{module.__name__} contains {forbidden!r}; mandate-gate must not "
            "replace or proxy ToolRegistry."
        )


def test_mandate_gate_modules_do_not_define_registry_replacement() -> None:
    import src.live.enforcement as enforcement
    import src.live.halt as halt
    import src.live.order_guard as order_guard
    import src.live.registry as live_registry
    import src.live.sdk_order_gate as sdk_order_gate

    for module in (enforcement, halt, order_guard, live_registry, sdk_order_gate):
        _assert_no_registry_wrapper(module)


def test_live_registry_wraps_tools_not_registry() -> None:
    import src.live.registry as live_registry

    sig = inspect.signature(live_registry.wrap_live_broker_tools)
    assert list(sig.parameters)[:2] == ["server_name", "wrappers"]
    assert sig.return_annotation == "list[MCPRemoteTool]"


def test_tool_registry_type_is_stable_after_registry_build(monkeypatch) -> None:
    import src.tools as tools_module

    monkeypatch.setattr(tools_module, "_discover_subclasses", lambda: [])

    registry = tools_module.build_registry(agent_config=None)

    assert type(registry) is ToolRegistry
    assert registry._tools == {}


def test_build_registry_live_broker_path_still_uses_live_boundary_gate() -> None:
    import src.tools as tools_module

    source = inspect.getsource(tools_module.build_registry)

    assert "is_live_broker" in source
    assert "should_register_live_channel" in source
    assert "wrap_live_broker_tools" in source
    for forbidden in FORBIDDEN_REGISTRY_WRAPPERS:
        assert forbidden not in source

