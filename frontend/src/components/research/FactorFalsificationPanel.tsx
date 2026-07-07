import { AlertTriangle } from "lucide-react";
import type { AlphaFoundryRule } from "@/lib/api";

export function FactorFalsificationPanel({
  hardFailures,
  rules,
}: {
  hardFailures: string[];
  rules: AlphaFoundryRule[];
}) {
  return (
    <div className="space-y-2 border-t pt-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        Falsification gates
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        {hardFailures.length ? (
          hardFailures.map((failure) => (
            <span key={failure} className="rounded-sm bg-danger/10 px-2 py-1 font-mono text-danger">
              {failure}
            </span>
          ))
        ) : (
          <span className="text-muted-foreground">No hard failure error_codes</span>
        )}
      </div>
      {rules.length > 0 && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {rules.map((rule) => (
            <li key={`${rule.rule_id}-${rule.error_code}`}>
              <span className="font-mono text-foreground">{rule.rule_id}</span>: {rule.explanation}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
