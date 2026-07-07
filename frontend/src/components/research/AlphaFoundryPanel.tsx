import { FileCheck2, Fingerprint, ShieldCheck } from "lucide-react";
import type { AlphaFoundryReportSurface } from "@/lib/api";
import { FactorFalsificationPanel } from "./FactorFalsificationPanel";
import { ForwardTrackingPanel } from "./ForwardTrackingPanel";

export function AlphaFoundryPanel({ surface }: { surface: AlphaFoundryReportSurface }) {
  const constraints = surface.portfolio_constraints || {};
  return (
    <section className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        <FileCheck2 className="h-4 w-4 text-muted-foreground" />
        Alpha Foundry
      </div>
      <div className="grid gap-3 text-sm md:grid-cols-3">
        <div>
          <div className="text-xs text-muted-foreground">conclusion_level</div>
          <div className="font-mono">{surface.research_card.conclusion_level}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">TrialLedger trial_count</div>
          <div className="font-mono">{surface.trials.trial_count}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">factor_id</div>
          <div className="break-all font-mono">{surface.factor.factor_id}</div>
        </div>
      </div>

      <div className="mt-3 space-y-2 border-t pt-3 text-sm">
        <div className="flex items-center gap-2 font-medium">
          <Fingerprint className="h-4 w-4 text-muted-foreground" />
          Factor evidence
        </div>
        <div className="break-all font-mono text-xs">{surface.factor.factor_definition_hash}</div>
        {surface.factor.proxy_note && (
          <div className="text-xs text-muted-foreground">{surface.factor.proxy_note}</div>
        )}
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-sm bg-muted px-2 py-1">execution_return used for tradable validation</span>
          <span className="rounded-sm bg-muted px-2 py-1">close_return diagnostics only</span>
        </div>
      </div>

      <FactorFalsificationPanel
        hardFailures={surface.research_card.hard_failures}
        rules={surface.scorecard.triggered_rules || []}
      />

      <div className="space-y-2 border-t pt-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          Portfolio constraints
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span>single-name cap {constraints.single_name_cap || "not recorded"}</span>
          <span>sector cap {constraints.sector_cap || "not recorded"}</span>
          <span>turnover cap {constraints.turnover_cap || "not recorded"}</span>
          <span>ADV cap {constraints.adv_cap || "not recorded"}</span>
        </div>
      </div>

      <ForwardTrackingPanel forward={surface.forward} />
    </section>
  );
}
