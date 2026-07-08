"""Critical path smoke tests for session runtime.

These tests pin the fact interface used by the chat/session hot path. They are
regression coverage for the IRR-AGL incident class where a registry replacement
did not behave like the plain ToolRegistry and broke prompt construction.

Rules:
- No real broker, real LLM, or market data is required.
- Do not skip or xfail these tests.
- mode="off" for any future wrapper-style feature must be object identity.
"""

from __future__ import annotations

import inspect

from src.agent.memory import WorkspaceMemory
from src.agent.tools import BaseTool, ToolRegistry


class _MinimalTool(BaseTool):
    name = "smoke_test_tool"
    description = "Smoke test only"
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> str:
        return "ok"


class TestToolRegistrySurface:
    """Document the ToolRegistry fact interface consumed by AgentLoop/ContextBuilder."""

    def test_registry_has_tools_attribute(self) -> None:
        registry = ToolRegistry()

        assert hasattr(registry, "_tools"), (
            "ToolRegistry._tools is part of the current fact interface. "
            "ContextBuilder counts and iterates it while building prompts."
        )

    def test_registry_tools_is_dict_like(self) -> None:
        registry = ToolRegistry()
        tools = registry._tools

        assert isinstance(tools, dict)
        assert len(tools) == 0
        assert list(tools.values()) == []
        assert list(tools.keys()) == []
        assert list(tools.items()) == []

    def test_registry_public_methods_are_callable(self) -> None:
        registry = ToolRegistry()

        for attr in ("execute", "get", "register", "get_definitions"):
            assert callable(getattr(registry, attr, None)), f"ToolRegistry.{attr} must be callable"

    def test_registered_tool_appears_in_tools_and_definitions(self) -> None:
        registry = ToolRegistry()
        tool = _MinimalTool()

        registry.register(tool)

        assert tool.name in registry._tools
        assert registry.get(tool.name) is tool
        assert tool.name in registry.tool_names
        assert tool.name in registry
        assert len(registry) == 1
        definitions = registry.get_definitions()
        assert definitions[0]["function"]["name"] == tool.name


class TestContextBuilderConstruction:
    """Mirror the README/session path with a bare ToolRegistry."""

    def test_context_builder_builds_with_empty_registry(self) -> None:
        from src.agent.context import ContextBuilder

        context = ContextBuilder(ToolRegistry(), WorkspaceMemory())

        prompt = context.build_system_prompt("")
        assert isinstance(prompt, str)
        assert "## Tools" in prompt

    def test_context_builder_can_iterate_tools_for_prompt(self) -> None:
        from src.agent.context import ContextBuilder

        registry = ToolRegistry()
        registry.register(_MinimalTool())
        context = ContextBuilder(registry, WorkspaceMemory())

        prompt = context.build_system_prompt("")
        assert "smoke_test_tool" in prompt
        assert "Smoke test only" in prompt


class TestSessionHotPathNoWrapper:
    """Session and agent hot paths must keep receiving the plain registry."""

    def test_session_service_does_not_import_or_call_registry_wrapper(self) -> None:
        from src.session import service as session_service_module

        source = inspect.getsource(session_service_module)
        for forbidden in ("GovernedToolRegistry", "govern_registry", "IRRAGLStack", "ToolRegistryWrapper"):
            assert forbidden not in source, (
                f"SessionService contains {forbidden!r}. "
                "Session runtime must not wrap or replace ToolRegistry."
            )

    def test_agent_loop_does_not_import_or_call_registry_wrapper(self) -> None:
        from src.agent import loop as agent_loop_module

        source = inspect.getsource(agent_loop_module)
        for forbidden in ("GovernedToolRegistry", "govern_registry", "IRRAGLStack", "ToolRegistryWrapper"):
            assert forbidden not in source, (
                f"AgentLoop contains {forbidden!r}. "
                "AgentLoop must execute through the plain registry contract."
            )

    def test_build_registry_returns_plain_tool_registry_when_no_mcp_config(self, monkeypatch) -> None:
        import src.tools as tools_module

        monkeypatch.setattr(tools_module, "_discover_subclasses", lambda: [])

        registry = tools_module.build_registry(agent_config=None)

        assert type(registry) is ToolRegistry
        assert hasattr(registry, "_tools")
        assert registry._tools == {}


class TestFeatureFlagKillSwitchInvariant:
    """A disabled wrapper-style feature must be a true no-op."""

    def test_govern_registry_off_mode_returns_identity_if_reintroduced(self) -> None:
        original = ToolRegistry()

        try:
            from src.governance.registry import govern_registry
        except ImportError:
            return

        result = govern_registry(original, mode="off")
        assert result is original, (
            "mode='off' must return the exact original object, not a proxy, "
            "subclass, or wrapper."
        )

