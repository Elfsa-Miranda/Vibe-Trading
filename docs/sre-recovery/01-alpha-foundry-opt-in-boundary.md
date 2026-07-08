# Alpha Foundry Opt-In Boundary

## Incident Class

Risk: a large research governance surface is mounted onto hot legacy runtime
paths before maintainers can review the package boundary.

Failure mode to prevent:

- default API spec gains Alpha Foundry routes;
- legacy backtest/session/Alpha Zoo payloads gain report sections, warnings, or
  artifacts;
- importing the API server imports Research Card, scorecard, or reliability
  policy modules;
- `warn` behaves like an active default mode.

## Required Default

Alpha Foundry is off by default.

```text
VIBE_TRADING_ALPHA_FOUNDRY_MODE=off
```

Unset, blank, or invalid values are treated as `off`.

`observe`, `warn`, and `enforce` are explicit operator modes, but they are not
runtime hooks by themselves. They must not attach Alpha Foundry to legacy
backtest, session, registry, Research Card, scorecard, API, or UI paths.

The fixture-backed API also requires a second opt-in:

```text
VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API=1
```

The API is mounted only when both conditions are true:

```text
VIBE_TRADING_ALPHA_FOUNDRY_MODE != off
VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API=1
```

## Safe Language

Use:

- explicit opt-in local adapter;
- pure alpha_foundry package;
- local JSON or Markdown artifact;
- deterministic fixture;
- no runtime hook.

Avoid for early upstream PRs:

- wrapping core runtime objects;
- governing the registry;
- evidence governance base;
- default Research Card integration;
- default scorecard policy integration.

## Upstream PR Slices

```text
PR 1: A-share alpha_foundry docs and inventory only.
PR 2: pure schema plus deterministic fixtures.
PR 3: tradability masks.
PR 4: one factor family with tests.
PR 5: diagnostics only.
```

Defer portfolio, forward tracking, Research Card, scorecard, API/UI,
performance, demos, and migration until maintainers accept the pure package
boundary.

## Verification

Run these commands after touching API registration or Alpha Foundry docs:

```text
pytest agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py -q
pytest agent/tests/security/test_alpha_foundry_api_security.py -q
pytest agent/tests/smoke/test_session_runtime_critical_path.py agent/tests/security/test_mandate_gate_architecture.py -q
```

Default-path invariants:

- `/openapi.json` contains no `/research/alpha-foundry/` paths by default.
- Default API import does not load:
  - `src.reliability.quant.methodology_facts`
  - `src.reliability.quant.scorecard_policy`
  - `src.research_card.builder`
  - `src.research_card.render_markdown`
- Opt-in API routes remain GET-only.
- Write method attempts and path traversal attempts do not mutate state.
- Legacy session/runtime/tool-registry smoke tests remain green.
