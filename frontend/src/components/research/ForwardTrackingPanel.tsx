import { Clock3 } from "lucide-react";
import type { AlphaFoundryForwardPlanSurface } from "@/lib/api";

export function ForwardTrackingPanel({ forward }: { forward: AlphaFoundryForwardPlanSurface }) {
  return (
    <div className="space-y-2 border-t pt-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Clock3 className="h-4 w-4 text-muted-foreground" />
        Forward tracking
      </div>
      <dl className="grid gap-2 text-xs md:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">status</dt>
          <dd className="font-mono">{forward.status}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">frozen_config_hash</dt>
          <dd className="break-all font-mono">{forward.frozen_config_hash}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">min_observations_required</dt>
          <dd className="font-mono">{forward.min_observations_required}</dd>
        </div>
      </dl>
    </div>
  );
}
