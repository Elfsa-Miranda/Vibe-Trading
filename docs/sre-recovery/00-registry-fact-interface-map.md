# Registry Fact Interface Map

Date: 2026-07-08

Scope: current post-IRR runtime on `D:\Vibe-Trading`, without reverting current
main progress and without reviving any IRR-AGL registry wrapper.

## Executive Finding

The current session hot path uses the plain `src.agent.tools.ToolRegistry`.
No `GovernedToolRegistry`, `govern_registry`, `IRRAGLStack`, or equivalent
registry replacement was found in the runtime scans performed for this audit.

The important operational lesson is that `ToolRegistry` has a fact interface,
not just a public method interface. `ContextBuilder` directly reads
`registry._tools`, so any future replacement must either be forbidden in the hot
path or proven by conformance tests to expose the same surface.

## Fact Interface

`agent/src/agent/tools.py`

- `ToolRegistry._tools`: dict-like mapping of tool name to `BaseTool`.
- `ToolRegistry.register(tool) -> None`: adds a tool immediately to `_tools`.
- `ToolRegistry.get(name) -> BaseTool | None`: returns a registered tool.
- `ToolRegistry.get_definitions() -> list[dict]`: OpenAI tool schema list.
- `ToolRegistry.execute(name, params) -> str`: executes a tool and returns a JSON string or tool result string.
- `ToolRegistry.tool_names -> list[str]`: names present in `_tools`.
- `len(registry)` and `name in registry`: convenience surfaces used by callers/tests.

`agent/src/agent/context.py`

- `ContextBuilder.build_system_prompt()` calls `len(self.registry._tools)`.
- `ContextBuilder._format_tool_descriptions()` iterates `self.registry._tools.values()`.

`agent/src/agent/loop.py`

- Uses `registry.get(...)` for metadata and readonly classification.
- Uses `registry.execute(name, args)` as the execution boundary.
- Does not wrap or replace the registry.

`agent/src/session/service.py`

- Builds a registry through `src.tools.build_registry(...)`.
- Passes the resulting registry directly to `AgentLoop`.
- Does not import or call any registry wrapper.

`agent/src/tools/__init__.py`

- `build_registry(...)` constructs a plain `ToolRegistry`.
- Live broker safety is applied at the live tool boundary, not by replacing the registry.

`agent/src/live/registry.py`

- `wrap_live_broker_tools(...)` wraps only live broker WRITE/UNKNOWN remote tools with `LiveOrderGuardTool`.
- READ tools remain plain read-only remote tools.
- Registration-time halt omits live order tools but preserves read tools.

## Evidence Commands

These commands were run during the audit:

```powershell
git status --short
git log --oneline -n 8
git grep -n "GovernedToolRegistry\|govern_registry\|IRR\.AGL\|IRRAGLStack" -- src tests agent
git grep -n "registry\._tools\|registry\._registry\|registry\.__dict__\|registry\._map" -- src tests agent
python -c "from src.agent.context import ContextBuilder; from src.agent.memory import WorkspaceMemory; from src.agent.tools import ToolRegistry; r=ToolRegistry(); ctx=ContextBuilder(r, WorkspaceMemory()); print('ContextBuilder smoke: PASS', len(ctx.registry._tools), isinstance(ctx.build_system_prompt(''), str))"
python -c "import inspect; from src.session import service as s; from src.agent import loop as l; source=inspect.getsource(s)+inspect.getsource(l); assert 'GovernedToolRegistry' not in source; assert 'govern_registry' not in source; print('No registry wrapper in hot path: PASS')"
pytest agent/tests/test_mandate_enforcement.py -q
pytest agent/tests/test_readonly_default.py -q
```

## New Regression Tests

- `agent/tests/smoke/test_session_runtime_critical_path.py`
- `agent/tests/security/test_mandate_gate_architecture.py`

These tests lock the current repair strategy:

- session chat must work with a bare `ToolRegistry`;
- `mode="off"` for future wrapper-style features must be exact object identity;
- `SessionService` and `AgentLoop` must not import or call registry wrappers;
- mandate-gate remains a live-write boundary check, not a registry replacement.

## Alpha Foundry Follow-Up

Alpha Foundry uses a separate opt-in boundary documented in
`docs/sre-recovery/01-alpha-foundry-opt-in-boundary.md`. Its default mode is
`off`, and it must not attach reports, warnings, API routes, Research Card
sections, scorecard policy, or reliability bridges to legacy runtime paths
without an explicit reviewed adapter.
