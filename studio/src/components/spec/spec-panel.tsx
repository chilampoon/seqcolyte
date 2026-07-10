"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import type { SpecDoc, SpecOligo } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  OLIGO_COLORS,
  OLIGO_LABELS,
  buildSeqIndex,
  colorizeDiagram,
  isToken,
  oligoType,
  splitSequence,
  tokenType,
  type OligoType,
} from "@/lib/oligoColors";

// ---------- colored sequence rendering ----------

function Pill({ type, label }: { type: OligoType; label: string }) {
  const c = OLIGO_COLORS[type];
  return (
    <span
      className="mx-0.5 inline-block rounded px-1 align-middle text-[10px] font-medium"
      style={{ color: c, backgroundColor: `${c}22` }}
    >
      {label}
    </span>
  );
}

/** A sequence colored per scg_lib_structs — from named components, else token split. */
function OligoSequence({ oligo }: { oligo: SpecOligo }) {
  const comps = oligo.components ?? [];
  if (comps.length) {
    return (
      <span className="font-mono text-[11px] leading-relaxed break-all">
        {comps.map((c, i) => {
          const t = oligoType(c.name);
          return isToken(c.sequence) ? (
            <Pill key={i} type={t} label={OLIGO_LABELS[t]} />
          ) : (
            <span key={i} style={{ color: OLIGO_COLORS[t] }} title={c.name}>
              {c.sequence}
            </span>
          );
        })}
      </span>
    );
  }
  const whole = oligoType(oligo.name || oligo.oligo_id || oligo.role || "");
  return (
    <span className="font-mono text-[11px] leading-relaxed break-all">
      {splitSequence(oligo.sequence ?? "").map((p, i) =>
        p.token ? (
          <Pill key={i} type={tokenType(p.text)} label={OLIGO_LABELS[tokenType(p.text)]} />
        ) : (
          <span key={i} style={{ color: OLIGO_COLORS[whole] }}>
            {p.text}
          </span>
        ),
      )}
    </span>
  );
}

/** Color an ASCII step-product diagram — span-only, so strand alignment is untouched. */
function ProductDiagram({ text, index }: { text: string; index: [string, OligoType][] }) {
  return (
    <>
      {colorizeDiagram(text, index).map((seg, i) =>
        seg.type ? (
          <span key={i} style={{ color: OLIGO_COLORS[seg.type] }}>
            {seg.text}
          </span>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </>
  );
}

/** The final-library molecule, colored from its `annotation_lines` breakdown. */
function FinalLibrarySequence({ lines }: { lines: string[] }) {
  return (
    <span className="font-mono text-[11px] leading-relaxed whitespace-nowrap">
      {lines.map((line, i) => {
        const eq = line.lastIndexOf(" = ");
        const seqPart = (eq >= 0 ? line.slice(0, eq) : line).trim();
        const label = eq >= 0 ? line.slice(eq + 3).trim() : seqPart;
        const t = oligoType(label);
        return isToken(seqPart) ? (
          <Pill key={i} type={t} label={OLIGO_LABELS[t]} />
        ) : (
          <span key={i} style={{ color: OLIGO_COLORS[t] }} title={label}>
            {seqPart.replace(/\s*\+\s*/g, "")}
          </span>
        );
      })}
    </span>
  );
}

// ---------- derived text + legend ----------

const LEGEND_ORDER: OligoType[] = [
  "p5",
  "read1",
  "cell_barcode",
  "umi",
  "poly_dt",
  "tso",
  "cdna",
  "read2",
  "sample_index",
  "p7",
  "capture",
  "me",
];

function typesInSpec(spec: SpecDoc): OligoType[] {
  const set = new Set<OligoType>();
  for (const o of spec.oligos ?? []) {
    if (o.components?.length) o.components.forEach((c) => set.add(oligoType(c.name)));
    else splitSequence(o.sequence ?? "").forEach((p) => p.token && set.add(tokenType(p.text)));
  }
  for (const line of spec.final_library?.annotation_lines ?? []) {
    const eq = line.lastIndexOf(" = ");
    if (eq >= 0) set.add(oligoType(line.slice(eq + 3)));
  }
  set.delete("other");
  return LEGEND_ORDER.filter((t) => set.has(t));
}

function describe(spec: SpecDoc): string {
  const full = JSON.stringify(spec);
  const bc = full.match(/\[CELL_BARCODE:(\d+)\]/)?.[1];
  const umi = full.match(/\[UMI:(\d+)\]/)?.[1];
  const bits: string[] = [
    `${spec.assay ?? "Sequencing assay"}${spec.chemistry_version ? ` (${spec.chemistry_version})` : ""}.`,
  ];
  const nano = spec.platform === "nanopore";
  if (bc || umi) {
    const carries = [bc && `a ${bc} nt cell barcode`, umi && `a ${umi} nt UMI`]
      .filter(Boolean)
      .join(" and ");
    bits.push(
      nano
        ? `After orientation normalization to the R1-handle-first direction, a raw long read carries ${carries} near its 5' end, then the cDNA insert; reads may occur in either orientation and are not guaranteed full-length.`
        : `Read 1 carries ${carries}; Read 2 reads the cDNA insert.`,
    );
  }
  const platform = spec.platform
    ? spec.platform.charAt(0).toUpperCase() + spec.platform.slice(1)
    : "";
  if (nano) {
    const steps = (spec.library_generation ?? []) as Array<{ phase?: string }>;
    const byPhase = (p: string) => steps.filter((s) => s.phase === p).length;
    bits.push(
      `${spec.oligos?.length ?? 0} sequence-defined 10x oligos across ${byPhase(
        "cdna_construction",
      )} cDNA-construction stages, ${byPhase("ont_library_prep")} ONT library-prep stages, and ${byPhase(
        "sequencing",
      )} sequencing stage${platform ? ` on ${platform}` : ""}.`,
    );
  } else {
    bits.push(
      `${spec.oligos?.length ?? 0} oligos across ${spec.library_generation?.length ?? 0} library-prep steps${
        platform ? `, sequenced on ${platform}` : ""
      }.`,
    );
  }
  return bits.join(" ");
}

function Section({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <h2 className="text-foreground border-border/60 flex items-baseline gap-2 border-b pb-1.5 text-sm font-semibold tracking-wide uppercase">
        {title}
        {sub && (
          <span className="text-muted-foreground text-xs font-normal tracking-normal normal-case">
            {sub}
          </span>
        )}
      </h2>
      {children}
    </section>
  );
}

// ---------- panel ----------

export function SpecPanel({
  specUrl,
  reloadToken = 0,
}: {
  specUrl: string | null;
  reloadToken?: number;
}) {
  const [spec, setSpec] = useState<SpecDoc | null>(null);
  const [state, setState] = useState<"loading" | "idle" | "empty">("loading");
  const [oligosOpen, setOligosOpen] = useState(false);

  // Constant sequences (10x/Illumina defaults + this spec's own oligo components) for
  // coloring the step-product diagrams. Built once per spec.
  const seqIndex = useMemo(() => {
    const extra: [string, OligoType][] = [];
    for (const o of spec?.oligos ?? []) {
      for (const c of o.components ?? []) {
        if (
          !c.sequence.includes("[") &&
          /^[ACGTNUVBDHKMRSWY]+$/i.test(c.sequence) &&
          c.sequence.length >= 8
        ) {
          extra.push([c.sequence, oligoType(c.name)]);
        }
      }
    }
    return buildSeqIndex(extra);
  }, [spec]);

  useEffect(() => {
    if (!specUrl) {
      setState("empty");
      return;
    }
    setState("loading");
    fetch(specUrl, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: SpecDoc) => {
        setSpec(d);
        setState("idle");
      })
      .catch(() => setState("empty"));
  }, [specUrl, reloadToken]);

  if (state === "loading") {
    return (
      <div className="text-muted-foreground flex items-center gap-2 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading spec…
      </div>
    );
  }
  if (state === "empty" || !spec) {
    return (
      <div className="text-muted-foreground py-16 text-center text-sm">
        Upload a protocol in the chat to extract the expected read/library structure — it appears
        here for review.
      </div>
    );
  }

  const oligos = spec.oligos ?? [];
  const steps = spec.library_generation ?? [];
  const seqReads = spec.library_sequencing ?? [];
  const reads = spec.read_structure?.reads ?? [];
  const fl = spec.final_library;
  const legend = typesInSpec(spec);

  return (
    <div className="space-y-6">
      {/* 1. Title */}
      <div className="space-y-1.5">
        <h1 className="text-lg leading-tight font-semibold">{spec.assay ?? "Extracted spec"}</h1>
        <div className="flex flex-wrap gap-1.5">
          {spec.chemistry_version && (
            <Badge variant="secondary" className="text-[10px]">
              {spec.chemistry_version}
            </Badge>
          )}
          {spec.platform && (
            <Badge variant="outline" className="text-[10px]">
              {spec.platform}
            </Badge>
          )}
          {spec.spec_id && (
            <Badge variant="outline" className="font-mono text-[10px]">
              {spec.spec_id}
            </Badge>
          )}
        </div>
      </div>

      {/* 2. Description */}
      <p className="text-muted-foreground text-sm leading-relaxed">{describe(spec)}</p>

      {/* color legend */}
      {legend.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {legend.map((t) => (
            <span key={t} className="inline-flex items-center gap-1 text-[11px]">
              <span className="size-2.5 rounded-sm" style={{ backgroundColor: OLIGO_COLORS[t] }} />
              <span className="text-muted-foreground">{OLIGO_LABELS[t]}</span>
            </span>
          ))}
        </div>
      )}

      {/* 3. Oligo table (foldable) */}
      {oligos.length > 0 && (
        <section className="space-y-2.5">
          <button
            onClick={() => setOligosOpen((o) => !o)}
            className="text-foreground hover:text-primary border-border/60 flex w-full items-baseline gap-1.5 border-b pb-1.5 text-sm font-semibold tracking-wide uppercase"
          >
            <ChevronRight
              className={cn(
                "size-4 shrink-0 self-center transition-transform",
                oligosOpen && "rotate-90",
              )}
            />
            Oligos
            <span className="text-muted-foreground text-xs font-normal tracking-normal normal-case">
              {oligos.length}
            </span>
          </button>
          {oligosOpen && (
            <div className="border-border/60 divide-border/60 divide-y rounded-lg border">
              {oligos.map((o) => (
                <div key={o.oligo_id} className="space-y-1 p-2.5">
                  <div className="text-sm leading-snug font-medium">{o.name ?? o.oligo_id}</div>
                  {o.role && (
                    <div className="text-muted-foreground text-[11px] leading-snug">{o.role}</div>
                  )}
                  <OligoSequence oligo={o} />
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 4. Library generation — final library structure is the last step */}
      {(steps.length > 0 || fl) && (
        <Section title="Library generation" sub="step-by-step build">
          <ol className="space-y-2.5">
            {steps.map((s) => (
              <li key={s.step} className="flex gap-2.5">
                <span className="bg-muted text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
                  {s.step}
                </span>
                <div className="min-w-0 space-y-1">
                  <div className="text-sm leading-snug font-medium">{s.title}</div>
                  {s.note && (
                    <div className="text-muted-foreground text-[11px] leading-snug">{s.note}</div>
                  )}
                  {s.product && (
                    <pre className="bg-muted/40 overflow-x-auto rounded-md p-2 font-mono text-[10px] leading-relaxed">
                      <ProductDiagram text={s.product} index={seqIndex} />
                    </pre>
                  )}
                </div>
              </li>
            ))}
            {fl && (
              <li className="flex gap-2.5">
                <span className="bg-primary/15 text-primary flex size-5 shrink-0 items-center justify-center rounded-full text-[10px]">
                  ★
                </span>
                <div className="min-w-0 space-y-1.5">
                  <div className="text-sm leading-snug font-medium">Final library</div>
                  {fl.source_label && (
                    <div className="text-muted-foreground text-[11px] leading-snug">
                      {fl.source_label}
                    </div>
                  )}
                  <div className="bg-muted/40 overflow-x-auto rounded-md p-2">
                    {fl.annotation_lines?.length ? (
                      <FinalLibrarySequence lines={fl.annotation_lines} />
                    ) : (
                      <span className="font-mono text-[11px] whitespace-nowrap">
                        {fl.annotated_library_sequence ?? fl.library_sequence}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            )}
          </ol>
        </Section>
      )}

      {/* 5. Library sequencing — how each read comes off the instrument */}
      {seqReads.length > 0 && (
        <Section title="Library sequencing" sub="how each read is sequenced">
          <div className="space-y-3">
            {seqReads.map((r, i) => (
              <div key={i} className="space-y-1">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    {r.read}
                  </Badge>
                  {r.cycles != null && (
                    <span className="text-muted-foreground text-[11px]">{r.cycles} bp</span>
                  )}
                  {r.primer && (
                    <span className="text-muted-foreground text-[11px]">· {r.primer}</span>
                  )}
                  {r.template && (
                    <span className="text-muted-foreground text-[11px]">· {r.template} strand</span>
                  )}
                </div>
                {r.note && (
                  <div className="text-muted-foreground text-[11px] leading-snug">{r.note}</div>
                )}
                {r.diagram && (
                  <pre className="bg-muted/40 overflow-x-auto rounded-md p-2 font-mono text-[10px] leading-relaxed">
                    <ProductDiagram text={r.diagram} index={seqIndex} />
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 6. Read structure (last) */}
      {reads.length > 0 && (
        <Section title="Read structure" sub="what each read sequences">
          <div className="space-y-1.5">
            {reads.map((rd) => (
              <div key={rd.read} className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="font-mono text-[10px]">
                  {rd.read}
                </Badge>
                {rd.cycles != null && (
                  <span className="text-muted-foreground text-[11px]">{rd.cycles} bp</span>
                )}
                <span className="flex flex-wrap items-center gap-1.5">
                  {(rd.segments ?? []).length > 0 ? (
                    rd.segments!.map((sg, i) => {
                      const bp =
                        sg.length != null
                          ? `${sg.length}`
                          : sg.length_range
                            ? `${sg.length_range[0]}–${sg.length_range[1]}`
                            : null;
                      return (
                        <span key={i} className="inline-flex items-center gap-1">
                          <Pill type={oligoType(sg.name)} label={sg.name} />
                          {bp != null && (
                            <span className="text-muted-foreground text-[10px]">{bp} bp</span>
                          )}
                        </span>
                      );
                    })
                  ) : (
                    <span className="text-muted-foreground text-[11px]">—</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
