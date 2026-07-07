# IRR-AGL v1.2.1 Delta Baseline Audit

Date: 2026-07-07
Branch: `phase/121-00-delta-baseline-audit`
Scope: Phase 0 documentation-only audit for v1.2.1 hardening.

## Startup Audit

- Read inputs: `AGENTS.md`, `ExecPlan.md`, current Phase 0 prompt, and the pasted startup prompt.
- Reference files requested by the Phase 0 prompt but not present as repo files: `AGENTS_v1.2_FINAL.md`, `ExecPlan_v1.2_FINAL.md`.
- Prior local reports read: `docs/local-baseline-audit.md`, `docs/windows-baseline-fix-report.md`.
- Current branch: `phase/121-00-delta-baseline-audit`.
- Current remotes: `origin=https://github.com/Elfsa-Miranda/Vibe-Trading.git`, `upstream=https://github.com/HKUDS/Vibe-Trading.git`.
- Current working tree before edits: clean.
- Phase branch status: `git pull --ff-only origin phase/121-00-delta-baseline-audit` returned already up to date.
- Tooling note: `rg` failed with `Access is denied` in this shell, so this audit used `git grep`, `git ls-files`, and scoped PowerShell reads.

## Section 1: v1.2 Strengths Preserved

| Area | Current strength | Evidence |
|---|---|---|
| Public tool interfaces | `BaseTool.execute(**kwargs) -> str` and `ToolRegistry.execute(name, params) -> str` remain small and stable. | `agent/src/agent/tools.py` |
| Artifact storage | Local artifact store has deterministic JSON serialization, SHA-256 object paths, SQLite index, WAL mode, path containment, and metadata redaction. | `agent/src/reliability/artifacts/store.py`, `agent/tests/reliability/test_artifact_store.py` |
| Artifact schema base | Artifact types already include `policy_decision`, `scorecard`, and `research_card`, which gives v1.2.1 a usable persistence base. | `agent/src/reliability/schema.py` |
| Trace compatibility | Trace writer tolerates old traces and preserves optional `artifact_refs`, `policy_decision_id`, warning codes, and hard failure codes. | `agent/src/agent/trace.py`, `agent/tests/reliability/test_artifact_trace_compat.py` |
| Legacy run card | Backtest run card writes strict JSON, markdown, data sources, warnings, validation, artifact checksums, and optional IRR artifact refs. | `agent/backtest/run_card.py`, `agent/tests/test_run_card.py`, `agent/tests/reliability/test_artifact_trace_compat.py` |
| Secret redaction | Reliability metadata redacts secret-like keys and values recursively. | `agent/src/reliability/redaction.py`, `agent/tests/reliability/test_artifact_models.py` |
| Shell exposure default | Default registry excludes shell tools unless explicitly opted in. Remote API request paths also default shell tools off. | `agent/src/tools/__init__.py`, `agent/api_server.py`, `agent/tests/test_tool_registry_security.py`, `agent/tests/test_security_auth_api.py` |
| Swarm MCP trust boundary | Swarm MCP config is operator-loaded, caller variables are treated as template data, and prompt-supplied MCP URLs are regression-tested not to become config. | `agent/src/config/loader.py`, `agent/src/swarm/worker.py`, `agent/tests/test_swarm_m5_trust_model.py` |
| Live broker safety | Live broker detection checks config key and URL host. Live broker wildcard allowlists are rejected except a documented read-only IBKR probe. WRITE and UNKNOWN live broker tools are wrapped by `LiveOrderGuardTool`. | `agent/src/config/schema.py`, `agent/src/live/registry.py`, `agent/tests/test_default_deny_unknown_robinhood_tool.py` |
| Live order guard | `LiveOrderGuardTool` fail-closes before broker calls on missing mandate, expired mandate, kill switch, unparseable intent, unpriceable quantity, or mandate breach. | `agent/src/live/order_guard.py`, `agent/tests/test_mandate_enforcement.py`, `agent/tests/test_killswitch_blocks_orders.py` |
| Local source no network fallback | Explicit `source="local"` is blocked from falling back to unrelated network loaders. | `agent/backtest/loaders/registry.py` |
| Generated backtest source validation | `backtest.runner` validates run root containment and rejects executable import-time statements in generated `signal_engine.py`. | `agent/backtest/runner.py` |
| Remote API security | Remote reads/writes require API auth when configured; loopback trust is narrowed by host/origin checks; path traversal inputs are rejected. | `agent/tests/test_security_auth_api.py` |

## Section 2: v1.2.1 Hardening Gaps Table

| gap_id | severity | file/path | phase | Finding |
|---|---|---|---|---|
| G121-P0-001 | P0 | `agent/src/governance/` | 1 | Tracked source is absent. There is no tracked `PolicyEngine`, `GovernedToolRegistry`, `DecisionRecorder`, `DenyBarrier`, `EvidenceIdentity`, or `EvidenceWriteOutcome`. |
| G121-P0-002 | P0 | `agent/src/agent/tools.py` | 1, 7 | `ToolRegistry.execute` directly calls `tool.execute(**params)` and catches exceptions. There is no pre-execution policy decision or deny barrier around this public execution path. |
| G121-P0-003 | P0 | `agent/src/agent/trace.py`, `agent/src/reliability/artifacts/store.py` | 1, 2 | `policy_decision_id` can appear in trace entries, and artifact records have `artifact_id`, but there is no model that separates `decision_id`, `policy_decision_artifact_id`, `trace_event_id`, and `ledger_event_hash`. |
| G121-P0-004 | P0 | `agent/src/reliability/` | 2 | `RunEvidenceIndex`, `EvidenceClosureReport`, `EvidenceOutbox`, reconciliation, and independent verifier are absent from tracked source. |
| G121-P0-005 | P0 | `agent/mcp_server.py`, `agent/src/api/sessions_routes.py`, `agent/src/api/swarm_routes.py`, `agent/src/swarm/worker.py`, `agent/src/scheduled_research/executor.py` | 7 | Real API, MCP, swarm, and scheduler routes are not proven to use `GovernedToolRegistry` or an equivalent wrapper. Current protections are surface-specific shell/live gates, not route-level governance coverage. |
| G121-P0-006 | P0 | `agent/src/live/registry.py`, `agent/src/live/order_guard.py` | 1, 7 | Live broker WRITE/UNKNOWN tools are guarded, but those decisions are not recorded into v1.2.1 policy decision trace/artifact/ledger/index/card evidence. |
| G121-P1-001 | P1 | `agent/src/reliability/claims/` | 3 | `ClaimSet`, `ResearchClaim`, and `ClaimAudit` are absent. Strong research claims are not structurally captured before card export. |
| G121-P1-002 | P1 | `agent/src/reliability/quant/` | 3, 4, 9 | Tracked quant scorecard source is absent. There is no `MethodologyFactSet`, no claim/fact predicate input, and no no-eval scorecard policy engine. |
| G121-P1-003 | P1 | `agent/src/research_protocol/` | 5 | Tracked protocol source is absent. There is no visible `ProtocolFieldProvenance` with confirmation status or confirmation event hash. |
| G121-P1-004 | P1 | `agent/backtest/run_card.py`, `agent/src/research_card/` | 6 | Only the legacy backtest run card is tracked. The v1.2.1 Research Card model/builder/markdown renderer with evidence closure, claims, triggered rules, and exact hard failure matching is absent. |
| G121-P1-005 | P1 | `agent/src/api/*`, `frontend/src/lib/api.ts`, `frontend/src/pages/RunDetail.tsx` | 6 | No v1.2.1 read-only evidence/claims/methodology endpoints or frontend panels are present. The UI renders a generic legacy run-card tab only. |
| G121-P1-006 | P1 | `agent/examples/irr_agl_demos/`, `agent/tests/demos/` | 8 | Deterministic v1.2.1 demo harness directories and tests are absent. |
| G121-P1-007 | P1 | `agent/tests/evals/surface_matrix/` | 7 | Surface behavior matrix and route-level governance coverage tests are absent. Existing tests cover shell default-off, live wrapper classification, and swarm MCP trust boundaries, but not v1.2.1 route governance. |
| G121-P1-008 | P1 | `agent/tests/contracts/`, API OpenAPI snapshots | 6 | No OpenAPI snapshot or frontend fixture contract exists for the proposed v1.2.1 evidence/claim/methodology endpoints. |
| G121-P2-001 | P2 | `AGENTS_v1.2_FINAL.md`, `ExecPlan_v1.2_FINAL.md` | 0 | Phase 0 prompt asks to read v1.2 final references, but those exact files are not present in the current working tree. Recorded as `PATH NOT FOUND`. |
| G121-P2-002 | P2 | Local shell tooling | 0 | `rg` failed with `Access is denied`; audit used `git grep` and scoped PowerShell reads. This is a process/tooling risk only, not a repo code gap. |

## Section 3: Evidence Identity Map

| Identity | Current state | Gap |
|---|---|---|
| `decision_id` | Optional `policy_decision_id` may be stored in trace entries. No tracked semantic decision model exists. | Needs v1.2.1 `RecordedPolicyDecision` and `EvidenceIdentity`. |
| `policy_decision_artifact_id` | Artifact records have `artifact_id`, and `policy_decision` is an allowed artifact type. | No enforced separation from semantic `decision_id`; no idempotent policy decision artifact writer. |
| `trace_event_id` | Trace events are JSONL records with timestamps; no stable trace event identity field is present. | Needs stable trace event ref and cross-check logic. |
| `ledger_event_hash` | Live audit and backtest run cards exist, but no v1.2.1 `TrialLedger` hash-chain event identity is visible in tracked source. | Needs ledger hash event recording and verifier cross-checks. |
| `run_id` | Runs are represented through `/runs` APIs and run directories. Trace lookup can search runs/sessions by id. | Needs evidence index keyed by run id and independent verifier. |
| `session_id` | Session APIs and events exist. | Needs policy/evidence records to carry session id consistently. |
| `trial_id` | Existing run card/backtest tests do not expose a v1.2.1 trial ledger identity. | Needs trial ledger integration and best-trial disclosure. |
| `protocol_hash` | No tracked research protocol model is present in this branch. | Needs protocol model/hash plus provenance metadata exclusion. |
| `idempotency_key` | Artifact store accepts optional `artifact_id` but has no decision idempotency envelope. | Needs canonical decision idempotency key and upsert/no-duplicate semantics. |

## Section 4: Route Coverage Map

| Surface | Current route/build path | Current governance signal | v1.2.1 readiness |
|---|---|---|---|
| Remote API session tool execution | `agent/src/api/sessions_routes.py` calls session service `send_message(... include_shell_tools=...)`. | Shell tools default off for API requests; DNS-rebound host checks prevent unsafe local trust. | Partial. No `GovernedToolRegistry` proof. |
| Remote API swarm execution | `agent/src/api/swarm_routes.py` calls `SwarmRuntime.start_run(... include_shell_tools=...)`. | Shell tools default off; swarm config is operator-loaded. | Partial. No governed registry proof. |
| MCP stdio | `agent/mcp_server.py` sets `_include_shell_tools=True` for stdio. | Stdio is treated as local/trusted for shell availability. | Not ready for v1.2.1: R5 shell governance evidence is absent. |
| MCP SSE / HTTP | `agent/mcp_server.py` sets `_include_shell_tools` from env for network transports. | Shell tools default off unless `VIBE_TRADING_ENABLE_SHELL_TOOLS=1`. | Partial. Needs R5 deny barrier and route coverage tests. |
| Swarm worker registry | `agent/src/swarm/worker.py` uses `build_swarm_registry`. | Strong trust-model tests prevent caller-supplied MCP config injection. | Partial. Needs governed wrapper around final worker registry. |
| Scheduled research executor | `agent/src/scheduled_research/executor.py` dispatches due jobs via session runtime. | Scheduler disabled by default and only enqueues a session message. | Not ready. Needs scheduler `RuntimeContext` and R4/R5 deny defaults. |
| Live connector adapter | `agent/src/tools/__init__.py` detects live broker servers and avoids exposing broker MCP wrappers directly; `agent/src/live/registry.py` gates live WRITE/UNKNOWN tools. | Strong live-specific fail-closed guard exists. | Partial. Needs policy decision evidence closure and route tests for unknown broker/live write. |
| Backtest generated source | `agent/backtest/runner.py` validates run root and import-time AST safety. | Good source containment and import-time execution guard. | Partial. Needs subprocess/env allowlist tests if future generated subprocess path is used. |
| CLI local registry | `src.tools.build_registry` default excludes shell tools unless caller opts in. | Existing unit tests cover default shell absence and explicit opt-in. | Partial. Needs governance wrapper in execution path, not only registry composition. |

## Section 5: Claim Gate Readiness Map

| Claim/gate area | Current state | Required phase |
|---|---|---|
| Structured `ResearchClaim` model | Missing. | Phase 3 |
| `ClaimSet` artifact type and index refs | Missing from `ArtifactType` and index source is absent. | Phase 3 |
| Deterministic claim extraction | Missing. Existing goal evidence has `claim_id`, but that is not the v1.2.1 research claim gate. | Phase 3 |
| `MethodologyFactSet` | Missing. | Phase 3 |
| Scorecard policy over claims/facts | Missing. No tracked quant scorecard policy source exists. | Phase 4 |
| Triggered rules with `rule_id`, `reason_code`, `explanation`, `evidence_refs` | Missing. | Phase 4 |
| LLM/prose override prevention | No v1.2.1 scorecard policy path exists yet. | Phase 4 |
| Research Card export gate for strong claims | Missing. Legacy run card only renders warnings/artifacts/metrics. | Phase 6 |
| UI Claim Audit panel | Missing. | Phase 6 |

## Section 6: Tests Currently Present vs Tests Required

| Test area | Present now | Required for v1.2.1 |
|---|---|---|
| Artifact store unit tests | Present: atomic write, WAL, path containment, metadata redaction, reliability off. | Extend with policy decision idempotency, artifact ref semantics, v1.2.1 schema migration. |
| Trace/run-card compatibility | Present: old traces, optional artifact refs, old/new legacy run-card shape. | Add trace event refs, decision identity, ledger hash refs, exact card/API/UI hard failure matching. |
| Shell default-off | Present for registry and API request defaults. | Add R4/R5 deny barrier tests proving `inner_tool_executed=False` under observe/warn/enforce. |
| Live safety | Present for mandate, kill switch, default-deny unknown Robinhood tool, live runner auth boundaries. | Add v1.2.1 policy decision recording and route-level live connector coverage. |
| Swarm MCP trust model | Present for schema, variables-as-data, missing MCP server drop warnings. | Add route-level proof that worker registries are governed. |
| Local source no network fallback | Present in loader registry logic and tests from prior fixes. | Add explicit v1.2.1 regression if governance matrix includes CLI/local fallback scenario. |
| Evidence index/outbox/verifier | Missing. | Phase 2 tests for index separation, missing-index rebuild, dangling refs, outbox pending, reconciliation. |
| ClaimSet/methodology facts | Missing. | Phase 3 tests for explicit/implicit claims, secret-free claims, methodology facts from audit/ledger/card. |
| Scorecard policy security | Missing. | Phase 4 no-eval/no-exec tests, malicious YAML tests, built-in hard gate non-weakenability. |
| Protocol confirmation | Missing. | Phase 5 tests for registered protocol blocking missing/unconfirmed inferred core fields and hash stability. |
| API/UI contract | Missing. | Phase 6 OpenAPI snapshots, API fixture parse tests, frontend fixture and no-secret tests. |
| Surface matrix | Missing. | Phase 7 behavior and route coverage tests for remote API, MCP SSE/HTTP/stdio, scheduler, swarm, live connector, subprocess. |
| Demos | Missing. | Phase 8 deterministic demo tests that call builders/verifiers instead of manually fabricating final artifacts. |
| Migration/security/performance | Partial baseline exists from prior reports. | Phase 10 v1.1/v1.2 fixture migration, secret scan, perf smoke, final acceptance. |

## Section 7: Recommended Execution Order

Keep the `ExecPlan.md` ordering. The current tree makes the dependencies especially important:

1. Phase 1 must come first because no tracked governance runtime exists. Implement `EvidenceIdentity`, `EvidenceWriteOutcome`, `DecisionRecorder`, and Deny Barrier before any route-level tests.
2. Phase 2 should immediately normalize evidence refs and add outbox/reconciliation/verifier, because Phase 6 cards and Phase 8 demos need a real verifier.
3. Phase 3 and Phase 4 should be kept separate. First create `ClaimSet` and `MethodologyFactSet`; then enforce scorecard policy over those structures.
4. Phase 5 can proceed after Phase 3 model work, but must not change `protocol_hash` semantics.
5. Phase 6 should wait for Phases 2-4 so Research Card/API/UI expose the same evidence, claims, triggered rules, and hard failures.
6. Phase 7 should be started after Phase 1 because route coverage needs a real governed wrapper to assert.
7. Phase 8 should wait for Phases 2, 4, 6, and 7 so demos use production builders/verifiers and real route governance.
8. Phase 9 should remain a bridge only and must not claim production diagnostics.
9. Phase 10 should remain final packaging, migration, security, and performance only.

## Phase 0 Verification

- Acceptance check `Test-Path docs/irr-agl-v1.2.1-delta-baseline.md`: `PASS doc exists`.
- Acceptance check comparing `integration/irr-agl-v1.2.1-hardening...HEAD` for `.py`, `.ts`, and `.tsx` changes: `PASS doc only`.
- Branch diff against `integration/irr-agl-v1.2.1-hardening`: `docs/irr-agl-v1.2.1-delta-baseline.md` only.
- Required global regression `pytest --tb=short -q --ignore=agent/tests/e2e_backtest`: `FAILED` with 2 failures, 4726 passed, 6 skipped, 135 warnings in 219.24s.
- Failing tests:
  - `agent/tests/test_packaging_dependencies.py::test_harmonic_backend_is_not_a_core_install_dependency`
  - `agent/tests/test_packaging_dependencies.py::test_channel_core_websocket_dependency_is_declared_for_baseline_installs`
- Failure cause: both tests call `Path.read_text()` on `agent/requirements.txt` without an explicit encoding on Windows, causing `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94 in position 186`.
- Phase 0 action: recorded the failure as required and did not modify runtime or test code.

## Process Risks And Notes

- The current branch, `origin/main`, `upstream/main`, `origin/integration/irr-agl-v1.2-closure`, and `origin/integration/irr-agl-v1.2.1-hardening` all point at the same visible commit during this audit. This is not a blocker for Phase 0, but it means Phase 0 is documenting a mostly pre-v1.2.1 implementation baseline.
- The Phase 0 prompt mentions older v1.2 files that are not present. This audit therefore treats the current `AGENTS.md`, `ExecPlan.md`, prior local baseline docs, and tracked source as the authoritative local evidence.
- Several directories expected by v1.2.1 exist only as ignored `__pycache__` directories locally (`agent/src/governance`, `agent/src/research_protocol`, `agent/src/research_card`, `agent/src/reliability/quant`). They should be treated as source-missing for tracked implementation purposes.
- This Phase 0 pass created documentation only. It did not modify Python runtime code, frontend code, API endpoints, feature flags, live safety, broker connectors, shell tools, MCP routes, scheduler routes, or swarm execution paths.
