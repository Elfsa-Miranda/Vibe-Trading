# Branch And Commit Evidence

## Scope

- Repository: `D:\Vibe-Trading`
- Audit branch: `audit/aaf-v21-final-acceptance-redteam`
- Source integration branch: `integration/a-share-alpha-foundry-v21`
- Source head before audit fixes: `8fc115c feat: add alpha foundry demos final package`
- Audit commit: this evidence package is contained in the current HEAD of `audit/aaf-v21-final-acceptance-redteam`; use `git rev-parse HEAD` for the non-recursive commit identity.
- Date: 2026-07-08

## Operator Files

The local execution specs were read as operator instructions only. They are intentionally not committed.

- `AGENTS.MD`: 1232 lines, sha256 `C36A30C9A015397A95654A1325658EADE5FEE1E8D905168CCF845604FDABC780`
- `execplan.md`: 1258 lines, sha256 `98BE33A8F7CFB622FA4C7B50FDE6C534C8D7B75EEBB19EDF9E5D139A9596D07B`
- `git ls-files -- AGENTS.MD execplan.md`: no tracked files
- `git check-ignore -v AGENTS.MD execplan.md`:
  - `.gitignore:86:AGENTS.md`
  - `.git/info/exclude:12:execplan.md`

## Phase Commit Chain Audited

- `69c1f6f` Phase 0 focus/data audit
- `073317a` Phase 1 hypothesis registry + TrialLedger stub
- `b9d5a8f` Phase 2 factor contracts + FactorOutputFrame
- `50e950b` Phase 3 limit liquidity factors
- `1bbb503` Phase 4 price-volume factors
- `45d9785` Phase 5 financial quality PIT gate
- `ac38573` Phase 6 falsification diagnostics
- `8fe9b70` Phase 7 multiple testing disclosure
- `15154f2` Phase 8 portfolio optimizer MVP
- `2f51b0a` Phase 9 forward tracking
- `2b15a48` Phase 10 scorecard/card integration
- `b324860` Phase 11 API/UI surface gate
- `8fc115c` Phase 12 demos final package

## Branch Hygiene

- No push performed.
- No commit includes `AGENTS.MD` or `execplan.md`.
- Audit evidence docs are under `docs/aaf-v2-final-verification/`; this directory is ignored by default and must be force-added intentionally.
