"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import type { SpecDoc } from "@/lib/types";
import { anchor } from "@/lib/resolveSpecRef";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          {title}
          {subtitle && <span className="text-muted-foreground ml-2 font-normal">{subtitle}</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">{children}</CardContent>
    </Card>
  );
}

function useHighlight(target: string | null, token: number, ready: boolean) {
  const [hot, setHot] = useState<string | null>(null);
  useEffect(() => {
    if (!target || !ready) return;
    const el = document.getElementById(target);
    if (!el) return;
    // let the DOM paint the freshly-rendered spec before scrolling
    const raf = requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setHot(target);
    });
    const t = setTimeout(() => setHot(null), 2200);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t);
    };
  }, [target, token, ready]);
  return hot;
}

const hl = (id: string, hot: string | null) =>
  cn(
    "scroll-mt-4 rounded-md transition-colors",
    hot === id && "ring-2 ring-primary bg-primary/5",
  );

export function SpecPanel({
  projectId,
  runId,
  highlight,
  highlightToken = 0,
}: {
  projectId: string;
  runId: string | null;
  highlight: string | null;
  highlightToken?: number;
}) {
  const [spec, setSpec] = useState<SpecDoc | null>(null);
  const [state, setState] = useState<"loading" | "idle" | "empty">("loading");
  const containerRef = useRef<HTMLDivElement>(null);
  const hot = useHighlight(highlight, highlightToken, state === "idle");

  useEffect(() => {
    if (!runId) {
      setState("empty");
      return;
    }
    setState("loading");
    fetch(`/api/projects/${projectId}/runs/${runId}/spec`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: SpecDoc) => {
        setSpec(d);
        setState("idle");
      })
      .catch(() => setState("empty"));
  }, [projectId, runId]);

  if (state === "loading") {
    return (
      <div className="text-muted-foreground flex items-center gap-2 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading spec…
      </div>
    );
  }
  if (state === "empty" || !spec) {
    return (
      <Card className="border-dashed">
        <CardContent className="text-muted-foreground py-16 text-center text-sm">
          The expected-structure spec appears once a run has snapshotted it.
        </CardContent>
      </Card>
    );
  }

  const reads = spec.read_structure?.reads ?? [];
  const r2 = reads.find((r) => r.read === "R2");

  return (
    <div ref={containerRef} className="space-y-4">
      <Section title="Read structure" subtitle="expected layout per read">
        <div className="space-y-2">
          {reads.map((rd) => (
            <div key={rd.read} id={anchor.read(rd.read)} className={cn("border-border/60 border p-2", hl(anchor.read(rd.read), hot))}>
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="font-mono text-[10px]">
                  {rd.read}
                </Badge>
                <span className="text-muted-foreground text-xs">
                  {rd.cycles ? `${rd.cycles} cycles · ` : ""}
                  {(rd.segments ?? []).map((s) => s.name).join(" + ") || "—"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {r2?.readthrough_chain && r2.readthrough_chain.length > 0 && (
        <Section title="R2 read-through chain" subtitle="what a short-insert R2 looks like">
          {r2.readthrough_chain.map((c) => (
            <div key={c.name} id={anchor.chain("R2", c.name)} className={cn("p-2", hl(anchor.chain("R2", c.name), hot))}>
              <div className="flex items-center gap-2">
                <code className="bg-muted rounded px-1.5 py-0.5 text-xs">{c.name}</code>
                {c.type && <span className="text-muted-foreground text-[11px]">{c.type}</span>}
              </div>
              {c.notes && <p className="text-muted-foreground mt-0.5 text-xs">{c.notes}</p>}
            </div>
          ))}
        </Section>
      )}

      <Section title="Oligos" subtitle={`${spec.oligos?.length ?? 0} parts`}>
        {(spec.oligos ?? []).map((o) => (
          <div key={o.oligo_id} id={anchor.oligo(o.oligo_id)} className={cn("border-border/60 border-b py-2 last:border-b-0", hl(anchor.oligo(o.oligo_id), hot))}>
            <div className="flex items-center gap-2">
              <code className="text-xs font-medium">{o.oligo_id}</code>
              {o.role && (
                <Badge variant="outline" className="text-[10px]">
                  {o.role}
                </Badge>
              )}
            </div>
            {o.sequence && (
              <p className="text-muted-foreground mt-1 font-mono text-[11px] break-all">{o.sequence}</p>
            )}
          </div>
        ))}
      </Section>

      {spec.library_generation && spec.library_generation.length > 0 && (
        <Section title="Library generation" subtitle="wet-lab build steps">
          <ol className="space-y-1.5">
            {spec.library_generation.map((s) => (
              <li key={s.step} id={anchor.libStep(s.step)} className={cn("flex gap-2 p-1", hl(anchor.libStep(s.step), hot))}>
                <span className="bg-muted text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
                  {s.step}
                </span>
                <div>
                  <p className="text-sm">{s.title}</p>
                  {s.note && <p className="text-muted-foreground text-xs">{s.note}</p>}
                </div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {spec.whitelists && Object.keys(spec.whitelists).length > 0 && (
        <Section title="Whitelists">
          {Object.entries(spec.whitelists).map(([key, wl]) => (
            <div key={key} id={anchor.whitelist(key)} className={cn("p-1", hl(anchor.whitelist(key), hot))}>
              <code className="text-xs font-medium">{key}</code>
              <p className="text-muted-foreground text-xs">
                {wl.name} · {wl.count?.toLocaleString()} barcodes × {wl.length} nt
              </p>
            </div>
          ))}
        </Section>
      )}

      {spec.platform_params && (
        <Section title="Platform parameters">
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(spec.platform_params).map(([field, val]) => (
              <div key={field} id={anchor.platformParam(field)} className={cn("bg-muted/30 rounded p-2", hl(anchor.platformParam(field), hot))}>
                <div className="text-muted-foreground text-[10px] uppercase tracking-wide">{field}</div>
                <div className="font-mono text-xs break-all">
                  {typeof val === "object" ? JSON.stringify(val) : String(val)}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {spec.final_library?.annotated_library_sequence && (
        <Section title="Final library" subtitle={spec.final_library.source_label}>
          <pre className="bg-muted/40 overflow-x-auto rounded p-2 font-mono text-[11px] whitespace-pre-wrap break-all">
            {spec.final_library.annotated_library_sequence}
          </pre>
        </Section>
      )}
    </div>
  );
}
