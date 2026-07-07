import { render, screen } from "@testing-library/react";
import { AlphaFoundryPanel } from "../AlphaFoundryPanel";
import type { AlphaFoundryReportSurface } from "@/lib/api";

const surface: AlphaFoundryReportSurface = {
  status: "ok",
  report: {
    report_id: "aaf-report",
    conclusion_level: "invalid",
    hard_failures: ["EOD_PROXY_OVERCLAIM"],
  },
  scorecard: {
    conclusion_level: "invalid",
    hard_failures: ["EOD_PROXY_OVERCLAIM"],
    triggered_rules: [
      {
        rule_id: "eod_proxy_overclaim",
        error_code: "EOD_PROXY_OVERCLAIM",
        explanation: "Proxy-only EOD evidence cannot support unqualified claims.",
      },
    ],
  },
  research_card: {
    conclusion_level: "invalid",
    hard_failures: ["EOD_PROXY_OVERCLAIM"],
    trial_count: 8,
    factor_definition_hashes: ["hash-limit_queue_pressure_proxy"],
    proxy_notes: ["EOD proxy only; no Level-2 queue alpha claim."],
    uses_execution_return: true,
    has_close_return_diagnostics: true,
  },
  factor: {
    factor_id: "limit_queue_pressure_proxy",
    factor_definition_hash: "hash-limit_queue_pressure_proxy",
    proxy_note: "EOD proxy only; no Level-2 queue alpha claim.",
    return_validation: {
      execution_return: "used_for_tradable_validation",
      close_return: "diagnostics_only",
    },
  },
  forward: {
    plan_id: "plan-limit-queue-pressure",
    status: "paper_tracking",
    frozen_config_hash: "frozen-hash",
    min_observations_required: 12,
  },
  trials: {
    family_id: "limit_liquidity",
    trial_count: 8,
    source: "TrialLedger",
  },
  portfolio_constraints: {
    single_name_cap: "5%",
    sector_cap: "25%",
    turnover_cap: "20%",
    adv_cap: "10%",
  },
};

describe("AlphaFoundryPanel", () => {
  it("renders exact evidence codes and quant readiness fields from fixture data", () => {
    render(<AlphaFoundryPanel surface={surface} />);

    expect(screen.getByText("EOD_PROXY_OVERCLAIM")).toBeInTheDocument();
    expect(screen.getByText("hash-limit_queue_pressure_proxy")).toBeInTheDocument();
    expect(screen.getByText("EOD proxy only; no Level-2 queue alpha claim.")).toBeInTheDocument();
    expect(screen.getByText("TrialLedger trial_count")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("execution_return used for tradable validation")).toBeInTheDocument();
    expect(screen.getByText("close_return diagnostics only")).toBeInTheDocument();
    expect(screen.getByText("single-name cap 5%")).toBeInTheDocument();
    expect(screen.getByText("paper_tracking")).toBeInTheDocument();
  });
});
