import { CheckCircle2, CircleAlert, XCircle } from "lucide-react";
import type { PreflightCheck, PreflightResult } from "@/lib/preflight";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

function Row({ check }: { check: PreflightCheck }) {
  const Icon = check.ok ? CheckCircle2 : check.required ? XCircle : CircleAlert;
  const tone = check.ok
    ? "text-emerald-500"
    : check.required
      ? "text-red-500"
      : "text-amber-500";
  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className={cn("mt-0.5 size-4 shrink-0", tone)} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{check.label}</span>
          {!check.required && (
            <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
              optional
            </span>
          )}
        </div>
        <p className="text-muted-foreground truncate font-mono text-xs">{check.detail}</p>
        {!check.ok && check.fix && (
          <p className="text-muted-foreground mt-0.5 text-xs">
            Fix: <span className="font-mono">{check.fix}</span>
          </p>
        )}
      </div>
    </div>
  );
}

export function PreflightPanel({ preflight }: { preflight: PreflightResult }) {
  const failing = preflight.checks.filter((c) => c.required && !c.ok);
  return (
    <Card className={cn(!preflight.ready && "border-red-500/40")}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {preflight.ready ? (
            <CheckCircle2 className="size-4 text-emerald-500" />
          ) : (
            <XCircle className="size-4 text-red-500" />
          )}
          Environment
          <span className="text-muted-foreground font-normal">
            {preflight.ready
              ? "ready"
              : `${failing.length} required check${failing.length === 1 ? "" : "s"} failing`}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="divide-border/60 divide-y pt-0">
        {preflight.checks.map((c) => (
          <Row key={c.id} check={c} />
        ))}
      </CardContent>
    </Card>
  );
}
