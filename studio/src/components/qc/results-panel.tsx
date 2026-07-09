"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, Cpu, FlaskConical, Loader2, Pin, Sparkles } from "lucide-react";
import { toast } from "sonner";
import type { QcFinding, QcReport, SpecDoc } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { anchor, resolveSpecRef } from "@/lib/resolveSpecRef";
import { libGenStepForCheck } from "@/lib/checkToLibGenStep";
import { SeverityPill, VerdictPill, VERDICT_STYLES, pct } from "./verdict";

function formatValue(f: QcFinding): string {
  if (f.unit === "fraction") return pct(f.value);
  return `${f.value} ${f.unit}`;
}

function FindingRow({
  finding,
  spec,
  onNavigateSpec,
}: {
  finding: QcFinding;
  spec: SpecDoc | null;
  onNavigateSpec: (anchorId: string) => void;
}) {
  const af = finding.affected_fraction;
  const libStep = libGenStepForCheck(finding.check_id);
  return (
    <div className="border-border/60 border-b py-3 last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <VerdictPill verdict={finding.verdict} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium leading-tight">{finding.title}</p>
            <p className="text-muted-foreground mt-0.5 text-xs">{finding.detail}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-sm">{formatValue(finding)}</div>
          <div className="text-muted-foreground font-mono text-[11px]">
            want {finding.threshold}
          </div>
        </div>
      </div>

      {af != null && (
        <div className="mt-2 flex items-center gap-2">
          <Progress
            value={Math.min(100, af * 100)}
            className={cn(
              "h-1.5",
              finding.verdict === "fail" && "[&>div]:bg-red-500",
              finding.verdict === "warn" && "[&>div]:bg-amber-500",
            )}
          />
          <span className="text-muted-foreground w-16 shrink-0 text-right font-mono text-[11px]">
            {pct(af)} reads
          </span>
        </div>
      )}

      {finding.evidence?.length > 0 && (
        <div className="mt-2 space-y-1">
          {finding.evidence.map((e, i) => {
            const target = resolveSpecRef(spec, e.spec_ref);
            return (
              <div key={i} className="flex items-start gap-2 text-[11px]">
                {target.found && target.anchorId ? (
                  <button
                    onClick={() => onNavigateSpec(target.anchorId!)}
                    className="border-primary/30 bg-primary/5 text-primary hover:bg-primary/10 inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 font-mono"
                    title="Jump to the spec"
                  >
                    {e.spec_ref}
                    <ArrowUpRight className="size-2.5" />
                  </button>
                ) : (
                  <code className="bg-muted text-muted-foreground shrink-0 rounded px-1.5 py-0.5 font-mono">
                    {e.spec_ref}
                  </code>
                )}
                <span className="text-muted-foreground">{e.note}</span>
              </div>
            );
          })}
          {libStep && (
            <button
              onClick={() => onNavigateSpec(anchor.libStep(libStep.step))}
              className="border-border bg-muted/50 text-muted-foreground hover:text-foreground mt-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]"
              title="Jump to the wet-lab step"
            >
              <FlaskConical className="size-2.5" />
              wet-lab step {libStep.step}: {libStep.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ConfusionCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "good" | "bad";
}) {
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        tone === "good"
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-red-500/30 bg-red-500/5",
      )}
    >
      <div className="font-mono text-lg font-semibold">{value.toLocaleString()}</div>
      <div className="text-muted-foreground text-[11px]">{label}</div>
    </div>
  );
}

function EvalPanel({ report }: { report: QcReport }) {
  const e = report.eval;
  if (!e) return null;
  const c = e.confusion;
  const tile = (label: string, v: number | null) => (
    <div className="bg-muted/40 rounded-md p-3 text-center">
      <div className="font-mono text-xl font-semibold">{v == null ? "—" : v.toFixed(3)}</div>
      <div className="text-muted-foreground text-[11px] uppercase tracking-wide">{label}</div>
    </div>
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">
          Self-scoring vs. ground-truth labels
          <span className="text-muted-foreground ml-2 font-normal">
            did we catch the injected failures?
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          {tile("Precision", e.precision)}
          {tile("Recall", e.recall)}
          {tile("F1", e.f1)}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <ConfusionCell label="true positives (caught)" value={c.tp} tone="good" />
          <ConfusionCell label="false positives" value={c.fp} tone="bad" />
          <ConfusionCell label="false negatives (missed)" value={c.fn} tone="bad" />
          <ConfusionCell label="true negatives (clean)" value={c.tn} tone="good" />
        </div>
        <p className="text-muted-foreground text-xs">
          {e.n.toLocaleString()} read pairs · predicted{" "}
          {e.predicted_affected?.toLocaleString() ?? "—"} affected vs.{" "}
          {e.true_affected?.toLocaleString() ?? "—"} truly affected.
        </p>
      </CardContent>
    </Card>
  );
}

function DiagnosisPanel({
  report,
  projectId,
  runId,
  onPinned,
}: {
  report: QcReport;
  projectId: string;
  runId: string | null;
  onPinned?: () => void;
}) {
  const plan = report.plan;
  const [pinned, setPinned] = useState(false);
  if (!plan) return null;
  const isLlm = plan.method === "llm";

  async function pin() {
    const title = plan!.root_cause ? plan!.root_cause.slice(0, 120) : "QC diagnosis";
    const body = [
      plan!.root_cause ? `**Root cause:** ${plan!.root_cause}` : "",
      plan!.diagnosis ?? "",
    ]
      .filter(Boolean)
      .join("\n\n");
    const r = await fetch(`/api/projects/${projectId}/conclusions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title, body, runId, source: "diagnosis" }),
    });
    if (r.ok) {
      setPinned(true);
      toast.success("Pinned to Conclusions");
      onPinned?.();
    } else {
      toast.error("Could not pin");
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          Diagnosis
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium",
              isLlm
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border bg-muted text-muted-foreground",
            )}
          >
            {isLlm ? <Sparkles className="size-3" /> : <Cpu className="size-3" />}
            {isLlm ? "AI diagnosis" : "deterministic"}
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-7 text-xs"
            onClick={pin}
            disabled={pinned}
          >
            <Pin className="size-3.5" /> {pinned ? "Pinned" : "Pin as conclusion"}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {plan.llm_error && (
          <Alert variant="destructive">
            <AlertTriangle className="size-4" />
            <AlertTitle>AI ranking unavailable — using the deterministic fallback</AlertTitle>
            <AlertDescription className="font-mono text-xs">{plan.llm_error}</AlertDescription>
          </Alert>
        )}
        {plan.root_cause && (
          <div>
            <div className="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wide">
              Root cause
            </div>
            <p className="text-sm font-medium">{plan.root_cause}</p>
          </div>
        )}
        {plan.diagnosis && (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{plan.diagnosis}</p>
        )}
        {plan.ranked && plan.ranked.length > 0 && (
          <div className="space-y-2">
            <div className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
              Ranked findings
            </div>
            {plan.ranked.map((r) => (
              <div key={r.check_id} className="flex items-start gap-2">
                <SeverityPill severity={r.severity} />
                <div className="min-w-0">
                  <code className="text-xs font-medium">{r.check_id}</code>
                  <p className="text-muted-foreground text-xs">{r.why}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ResultsPanel({
  projectId,
  runId,
  reloadToken = 0,
  onNavigateSpec = () => {},
  onConclusionAdded,
}: {
  projectId: string;
  runId: string | null;
  reloadToken?: number;
  onNavigateSpec?: (anchorId: string) => void;
  onConclusionAdded?: () => void;
}) {
  const [report, setReport] = useState<QcReport | null>(null);
  const [spec, setSpec] = useState<SpecDoc | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "empty" | "error">("loading");

  const load = useCallback(async () => {
    if (!runId) {
      setState("empty");
      return;
    }
    setState("loading");
    try {
      const res = await fetch(`/api/projects/${projectId}/runs/${runId}/report`, {
        cache: "no-store",
      });
      if (res.status === 404) {
        setReport(null);
        setState("empty");
        return;
      }
      if (!res.ok) throw new Error(String(res.status));
      setReport((await res.json()) as QcReport);
      setState("idle");
      // spec is best-effort (enables evidence drill-down); ignore failures
      fetch(`/api/projects/${projectId}/runs/${runId}/spec`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d: SpecDoc | null) => setSpec(d))
        .catch(() => setSpec(null));
    } catch {
      setState("error");
    }
  }, [projectId, runId]);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  if (state === "loading") {
    return (
      <div className="text-muted-foreground flex items-center gap-2 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading results…
      </div>
    );
  }
  if (state === "empty" || !report) {
    return (
      <Card className="border-dashed">
        <CardContent className="text-muted-foreground py-16 text-center text-sm">
          No results yet. Run the QC pipeline to see findings, a diagnosis, and eval scores here.
        </CardContent>
      </Card>
    );
  }
  if (state === "error") {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="size-4" />
        <AlertTitle>Could not load the report</AlertTitle>
      </Alert>
    );
  }

  const profile = report.profile;
  const overall = report.overall ?? "warn";
  const s = VERDICT_STYLES[overall];

  return (
    <div className="space-y-4">
      <Card className={cn("border", s.border)}>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-4">
            <div
              className={cn(
                "flex flex-col items-center justify-center rounded-lg border px-4 py-2",
                s.bg,
                s.border,
              )}
            >
              <span className={cn("text-lg font-bold uppercase", s.text)}>{overall}</span>
              <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
                overall
              </span>
            </div>
            <div>
              <p className="text-sm font-medium">{report.assay ?? "QC report"}</p>
              <p className="text-muted-foreground text-xs">
                {report.platform} · spec{" "}
                <code className="font-mono">{report.spec_id}</code>
              </p>
            </div>
          </div>
          {profile && (
            <div className="text-muted-foreground flex gap-5 text-xs">
              <div>
                <div className="text-foreground font-mono text-sm">
                  {profile.n_pairs.toLocaleString()}
                </div>
                read pairs
              </div>
              <div>
                <div className="text-foreground font-mono text-sm">
                  {profile.r1_len.modal} bp
                </div>
                R1 modal
              </div>
              <div>
                <div className="text-foreground font-mono text-sm">
                  {profile.r2_len.modal} bp
                </div>
                R2 modal
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {report.findings && report.findings.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Checks{" "}
              <span className="text-muted-foreground font-normal">
                {report.findings.length} run
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {report.findings.map((f) => (
              <FindingRow
                key={f.check_id}
                finding={f}
                spec={spec}
                onNavigateSpec={onNavigateSpec}
              />
            ))}
          </CardContent>
        </Card>
      )}

      <DiagnosisPanel
        report={report}
        projectId={projectId}
        runId={runId}
        onPinned={onConclusionAdded}
      />
      <EvalPanel report={report} />
    </div>
  );
}
