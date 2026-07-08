# IRR-AGL Retirement Postmortem

Date: 2026-07-08

Status: retirement closure, not revival.

## Executive Summary

The IRR-AGL runtime governance model is retired as an upstream integration
direction. Its primary failure mode was not a missing check in isolation; it was
placing a governance layer on the hottest runtime path and breaking the factual
interface of `ToolRegistry`.

The closure objective is narrow:

- preserve the current main-based runtime behavior;
- prove default session/runtime paths are not replaced by IRR-AGL registry
  machinery;
- archive the known failure modes, regression coverage, and residual risks;
- make future accidental revival reviewable and reversible.

This branch is not recommended for upstream revival.

## Root Cause

The retired design treated governance architecture correctness as more
important than runtime compatibility and rollback safety. The specific incident
class was:

- `GovernedToolRegistry` or equivalent registry replacement entering the
  default session path;
- `mode=off` still changing runtime object identity;
- code assuming the public `ToolRegistry.execute(...)` method was the full
  contract while existing runtime code also consumed factual surfaces such as
  `registry._tools`;
- safety behavior coupled to a broad registry replacement instead of being kept
  at narrow live-write and API boundaries.

## Blast Radius

Potentially affected surfaces:

- default session prompt construction;
- `AgentLoop` registry access;
- `ContextBuilder` prompt construction through `registry._tools`;
- live broker tool registration if governance code wrapped the entire registry;
- API and report surfaces if Alpha Foundry or Research Card integrations mounted
  by default;
- maintainability, because upstream reviewers could mistake local governance
  artifacts for a proposed mainline architecture.

No live trading expansion is claimed by this closure.

## Fixed Or Contained

- The current hot path uses plain `src.agent.tools.ToolRegistry`.
- Runtime scans found no `GovernedToolRegistry`, `govern_registry`,
  `IRRAGLStack`, or equivalent registry replacement in production session
  runtime paths.
- Regression tests lock bare `ToolRegistry` compatibility for prompt/session
  construction.
- Mandate-gate tests lock the rule that live safety remains a tool-boundary
  control, not a registry replacement.
- Alpha Foundry API exposure is opt-in and absent by default.
- Alpha Foundry-sensitive Research Card, scorecard, and reliability imports are
  lazy and not loaded by default API import.
- Documentation now frames Alpha Foundry and IRR-AGL work as local archive /
  opt-in surfaces, not an upstream full-stack landing.

## External Security Context

The closure threat model includes public Vibe-Trading security classes reported
for versions before `0.1.10`:

- proposal identifier path traversal allowing forged live trading mandates:
  `https://www.vulncheck.com/advisories/vibe-trading-path-traversal-in-proposal-identifier-allows-forging-live-trading-mandates`
- DNS rebinding / loopback trust / credentialed CORS auth bypass:
  `https://www.sentinelone.com/vulnerability-database/cve-2026-58169/`
- persistent memory path traversal via `memory_type`:
  `https://www.vulncheck.com/advisories/vibe-trading-path-traversal-via-persistent-memory-type`
- `v0.1.10` hardening release notes:
  `https://github.com/HKUDS/Vibe-Trading/releases/tag/v0.1.10`

## Non-Goals

- No revival of IRR-AGL as an upstream architecture.
- No new registry wrapper.
- No live trading capability expansion.
- No claim that all unknown vulnerabilities are fixed.
- No release-tag recommendation except an internal archive tag, if operators
  explicitly need one.
- No modification of `BaseTool.execute`, `ToolRegistry.execute`, or
  `DataLoaderProtocol.fetch` signatures.

## Closure Principle

This branch should be evaluated by four properties:

- closable: default modes truly do nothing to hot runtime paths;
- provable: known incident classes have regression evidence;
- revertible: closure changes are narrow and branch-local;
- auditable: fixed items, non-goals, and residual risks are written down.
