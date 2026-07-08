# Protected Core Files

Modifying any of these files should require explicit maintainer review before a
PR is submitted. The purpose is not to freeze development; it is to force a
small, evidence-backed change whenever a runtime hot path or live safety boundary
is touched.

## Tier 1: Runtime Hot Path

Requires an RFC-style issue and two maintainer approvals:

- `agent/src/agent/loop.py`
- `agent/src/session/service.py`
- `agent/src/agent/tools.py`
- `agent/src/agent/context.py`

Required evidence for any Tier 1 change:

- session runtime smoke tests pass;
- registry drop-in/conformance tests pass;
- README-style local construction path works with a bare `ToolRegistry`;
- no wrapper/proxy/subclass replaces `ToolRegistry` in session runtime;
- if a feature flag has `mode="off"`, it returns the exact original object.

## Tier 2: Live Safety Boundaries

Requires one maintainer approval and focused live-gate tests:

- `agent/src/live/enforcement.py`
- `agent/src/live/order_guard.py`
- `agent/src/live/sdk_order_gate.py`
- `agent/src/live/registry.py`
- `agent/src/live/halt.py`
- any file defining or constructing `LiveOrderGuardTool`

Required evidence for any Tier 2 change:

- no-mandate path fails closed;
- expired mandate path fails closed;
- kill switch blocks before any remote order call;
- UNKNOWN/WRITE broker tools are gated or omitted;
- READ tools remain read-only;
- no mandate-gate code replaces `ToolRegistry`.

## Non-Negotiable Invariants

- Do not revive `GovernedToolRegistry` or an equivalent ToolRegistry wrapper.
- Do not modify `agent/src/agent/loop.py` or `agent/src/session/service.py` for governance logic.
- Do not add a global governance mode to the session runtime.
- Do not expand live trading capability as part of an IRR remediation.
- Do not let safety changes break default chat/session availability.

## Rollback

The SRE remediation added only tests and documentation. Rollback is deleting:

- `agent/tests/smoke/test_session_runtime_critical_path.py`
- `agent/tests/security/test_mandate_gate_architecture.py`
- `docs/sre-recovery/00-registry-fact-interface-map.md`
- `docs/sre-recovery/protected-core-files.md`

