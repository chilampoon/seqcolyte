"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import type { SpecDoc, SpecOligo, SpecPublication, SpecReference } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { DataProcessingDag } from "@/components/spec/data-processing-dag";
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
      className="mx-0.5 inline-block rounded px-1 align-middle text-[11px] font-medium"
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
      <span className="font-mono text-xs leading-relaxed break-all">
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
    <span className="font-mono text-xs leading-relaxed break-all">
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
    <span className="font-mono text-xs leading-relaxed whitespace-nowrap">
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

// ---------- reference / publication helpers ----------

function refHref(r: SpecReference): string | null {
  if (r.url) return r.url;
  if (r.doi) return `https://doi.org/${r.doi}`;
  return null;
}

function pubHref(p: SpecPublication): string | null {
  const o = p.original_publication;
  if (!o) return null;
  if (o.url) return o.url;
  if (o.doi) return `https://doi.org/${o.doi}`;
  return null;
}

function throughputText(p: SpecPublication): string | null {
  const t = p.throughput;
  if (!t) return null;
  if (t.summary) return t.summary;
  const parts = [
    t.cells && `${t.cells} cells`,
    t.rna && `RNA: ${t.rna}`,
    t.dna && `DNA: ${t.dna}`,
  ].filter(Boolean);
  return parts.length ? (parts.join("; ") as string) : null;
}

function hasPublication(p: SpecPublication): boolean {
  return !!(
    p.year != null ||
    p.original_publication?.title ||
    (p.authors?.length ?? 0) > 0 ||
    throughputText(p) ||
    visibleOther(p.other).length > 0
  );
}

// Turn accessions / DOIs / URLs inside a free-text value into links.
const LINK_RE =
  /(GSE\d+|GSM\d+|GDS\d+|SR[PRX]\d+|PRJ(?:NA|EB)\d+|E-MTAB-\d+|10\.\d{4,}\/[^\s,;)\]]+|https?:\/\/[^\s)\]]+)/gi;

function accHref(tok: string): string {
  if (/^GS[EM]|^GDS/i.test(tok)) return `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=${tok}`;
  if (/^SR[PRX]/i.test(tok)) return `https://www.ncbi.nlm.nih.gov/sra/?term=${tok}`;
  if (/^PRJ/i.test(tok)) return `https://www.ncbi.nlm.nih.gov/bioproject/?term=${tok}`;
  if (/^E-MTAB/i.test(tok)) return `https://www.ebi.ac.uk/biostudies/arrayexpress/studies/${tok}`;
  if (/^10\./.test(tok)) return `https://doi.org/${tok}`;
  return tok;
}

function Linkified({ text }: { text: string }) {
  return (
    <>
      {text.split(LINK_RE).map((part, i) =>
        i % 2 === 1 ? (
          <a
            key={i}
            href={accHref(part)}
            target="_blank"
            rel="noreferrer"
            className="text-primary hover:underline"
          >
            {part}
          </a>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

// `publication.other` labels that merely repeat the description / read structure — hidden in the panel.
const REDUNDANT_OTHER = new Set([
  "cell barcode", "umi", "umi length", "barcode design", "barcode pool", "assay type",
  "bead barcode structure", "tn5 barcodes", "chemistry", "cell label", "molecular index",
  "indexing", "barcode structure", "cell barcode structure", "cell label (barcode)",
  "statistical model", "analysis pipeline", "computational tool", "computational tools",
]);

function visibleOther(other?: { label: string; value: string }[]): { label: string; value: string }[] {
  return (other ?? []).filter((o) => !REDUNDANT_OTHER.has((o.label ?? "").toLowerCase().trim()));
}

/** Strip a redundant "(N cycles …)" parenthetical from a read name — bp is shown separately. */
const cleanReadName = (name: string): string =>
  name.replace(/\s*\(\s*\d+\s*(?:cyc|cycles?)[^)]*\)/i, "").trim();

/** A pure sample-index read (i7/i5/I1/I2) that carries no biology — hidden from Library sequencing. */
function isIndexRead(r: { read?: string | null; note?: string | null }): boolean {
  const text = `${r.read ?? ""} ${r.note ?? ""}`.toLowerCase();
  const isIndex = /\b(i1|i2|i7|i5|index\s*1|index\s*2)\b/.test((r.read ?? "").toLowerCase()) ||
    /\b(sample|well|i7|i5)\s*index\b/.test(text);
  const isBio = /(cell\s*barcode|\bbarcode\b|umi|cdna|read\s*1|read\s*2|\bl1\b|genom|insert)/.test(text);
  return isIndex && !isBio;
}

/** A label → value row for the neat "Paper & protocol details" layout. */
function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-0.5 sm:grid-cols-[9rem_1fr]">
      <div className="text-muted-foreground">{label}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
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
      <h2 className="text-foreground border-border/60 flex items-baseline gap-2 border-b pb-1.5 text-base font-semibold tracking-wide uppercase">
        {title}
        {sub && (
          <span className="text-muted-foreground text-sm font-normal tracking-normal normal-case">
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
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set());
  const [authorsOpen, setAuthorsOpen] = useState(false);
  const toggleStep = (n: number) =>
    setOpenSteps((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });

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
      <div className="text-muted-foreground flex items-center gap-2 py-16 text-base">
        <Loader2 className="size-4 animate-spin" /> Loading spec…
      </div>
    );
  }
  if (state === "empty" || !spec) {
    return (
      <div className="text-muted-foreground py-16 text-center text-base">
        Upload a protocol in the chat to extract the expected read/library structure — it appears
        here for review.
      </div>
    );
  }

  const oligos = spec.oligos ?? [];
  const steps = spec.library_generation ?? [];
  const seqReads = (spec.library_sequencing ?? []).filter((r) => !isIndexRead(r));
  const reads = spec.read_structure?.reads ?? [];
  const fl = spec.final_library;
  const legend = typesInSpec(spec);

  return (
    <div className="space-y-6">
      {/* 1. Title */}
      <div className="space-y-1.5">
        <h1 className="text-xl leading-tight font-semibold">
          {spec.title ?? spec.assay ?? "Extracted spec"}
        </h1>
        {spec.title && spec.assay && spec.assay !== spec.title && (
          <div className="text-muted-foreground text-sm leading-snug">{spec.assay}</div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {spec.modality && (
            <Badge className="border-transparent bg-sky-500/15 text-xs text-sky-600 dark:text-sky-400">
              {spec.modality}
            </Badge>
          )}
          {spec.method_type && (
            <Badge className="border-transparent bg-violet-500/15 text-xs text-violet-600 dark:text-violet-400">
              {spec.method_type}
            </Badge>
          )}
          {spec.chemistry_version && spec.chemistry_version !== "unspecified" && (
            <Badge variant="secondary" className="text-xs">
              {spec.chemistry_version}
            </Badge>
          )}
          {spec.platform && (
            <Badge variant="outline" className="text-xs">
              {spec.platform}
            </Badge>
          )}
        </div>
      </div>

      {/* 2. Description + reference */}
      <div className="space-y-1.5">
        <p className="text-muted-foreground text-sm leading-relaxed">
          {spec.description ?? describe(spec)}
        </p>
        {spec.reference &&
          (spec.reference.label || refHref(spec.reference) || spec.reference.path) && (
            <p className="text-muted-foreground text-xs leading-snug">
              <span className="font-medium">Reference: </span>
              {refHref(spec.reference) ? (
                <a
                  href={refHref(spec.reference)!}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline"
                >
                  {spec.reference.label ?? refHref(spec.reference)}
                </a>
              ) : (
                (spec.reference.label ?? spec.reference.path)
              )}
            </p>
          )}
      </div>

      {/* color legend */}
      {legend.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {legend.map((t) => (
            <span key={t} className="inline-flex items-center gap-1 text-xs">
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
            className="text-foreground hover:text-primary border-border/60 flex w-full items-baseline gap-1.5 border-b pb-1.5 text-base font-semibold tracking-wide uppercase"
          >
            <ChevronRight
              className={cn(
                "size-4 shrink-0 self-center transition-transform",
                oligosOpen && "rotate-90",
              )}
            />
            Oligos
            <span className="text-muted-foreground text-sm font-normal tracking-normal normal-case">
              {oligos.length}
            </span>
          </button>
          {oligosOpen && (
            <div className="border-border/60 divide-border/60 divide-y rounded-lg border">
              {oligos.map((o) => (
                <div key={o.oligo_id} className="space-y-1 p-2.5">
                  <div className="text-base leading-snug font-medium">{o.name ?? o.oligo_id}</div>
                  {o.role && (
                    <div className="text-muted-foreground text-xs leading-snug">{o.role}</div>
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
            {steps.map((s) => {
              const open = openSteps.has(s.step);
              return (
                <li key={s.step} className="flex gap-2.5">
                  <span className="bg-muted text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium">
                    {s.step}
                  </span>
                  <div className="min-w-0 space-y-1">
                    <div className="text-base leading-snug font-medium">{s.title}</div>
                    {s.summary && (
                      <div className="text-muted-foreground text-sm leading-snug">{s.summary}</div>
                    )}
                    {/* only the verbose note collapses; the diagram stays visible */}
                    {s.note && (
                      <>
                        <button
                          onClick={() => toggleStep(s.step)}
                          className="text-muted-foreground hover:text-primary flex items-center gap-1 text-xs"
                        >
                          <ChevronRight
                            className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
                          />
                          details
                        </button>
                        {open && (
                          <div className="text-muted-foreground text-sm leading-snug">{s.note}</div>
                        )}
                      </>
                    )}
                    {s.product && (
                      <pre className="bg-muted/40 overflow-x-auto rounded-md p-2 font-mono text-[11px] leading-relaxed">
                        <ProductDiagram text={s.product} index={seqIndex} />
                      </pre>
                    )}
                  </div>
                </li>
              );
            })}
            {fl && (
              <li className="flex gap-2.5">
                <span className="bg-primary/15 text-primary flex size-5 shrink-0 items-center justify-center rounded-full text-[11px]">
                  ★
                </span>
                <div className="min-w-0 space-y-1.5">
                  <div className="text-base leading-snug font-medium">Final library</div>
                  {fl.source_label && (
                    <div className="text-muted-foreground text-xs leading-snug">
                      {fl.source_label}
                    </div>
                  )}
                  <div className="bg-muted/40 overflow-x-auto rounded-md p-2">
                    {fl.annotation_lines?.length ? (
                      <FinalLibrarySequence lines={fl.annotation_lines} />
                    ) : (
                      <span className="font-mono text-xs whitespace-nowrap">
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
                {/* The read-name/length/primer/strand header is redundant with the diagram's
                    caption (which already names the read + primer + strand), so it's dropped
                    when a diagram is present. Fall back to a minimal header line only for the
                    rare read that has no captioned diagram, so it stays identifiable. */}
                {!r.diagram && (
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <Badge variant="secondary" className="font-mono text-xs">
                      {r.read ? cleanReadName(r.read) : `Read ${i + 1}`}
                    </Badge>
                    {r.cycles != null && (
                      <span className="text-muted-foreground text-sm">{r.cycles} bp</span>
                    )}
                    {r.primer && (
                      <span className="text-muted-foreground text-sm">· {r.primer}</span>
                    )}
                    {r.template && (
                      <span className="text-muted-foreground text-sm">· {r.template} strand</span>
                    )}
                  </div>
                )}
                {r.note && (
                  <div className="text-muted-foreground text-sm leading-snug">{r.note}</div>
                )}
                {r.diagram && (
                  <pre className="bg-muted/40 overflow-x-auto rounded-md p-2 font-mono text-xs leading-relaxed">
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
                <Badge variant="secondary" className="font-mono text-[11px]">
                  {rd.read}
                </Badge>
                {rd.cycles != null && (
                  <span className="text-muted-foreground text-xs">{rd.cycles} bp</span>
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
                            <span className="text-muted-foreground text-[11px]">{bp} bp</span>
                          )}
                        </span>
                      );
                    })
                  ) : (
                    <span className="text-muted-foreground text-xs">—</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 7. Data processing — computational pipeline (DAG) + statistical model */}
      {(() => {
        const dp = spec.data_processing;
        const stat = dp?.statistical_model ?? spec.publication?.statistical_model;
        if (!dp?.summary && !(dp?.steps?.length ?? 0) && !(dp?.tools?.length ?? 0) && !stat) return null;
        return (
          <Section title="Data processing" sub="computational pipeline">
            <div className="space-y-3 text-sm leading-relaxed">
              {dp?.summary && <p className="text-muted-foreground">{dp.summary}</p>}
              {(dp?.nodes?.length ?? 0) > 0 ? (
                <DataProcessingDag dp={dp!} />
              ) : (dp?.steps?.length ?? 0) > 0 ? (
                <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5">
                  {dp!.steps!.map((st, i) => (
                    <span key={i} className="flex items-center gap-1.5">
                      <span className="bg-muted rounded-md px-2 py-0.5 text-xs font-medium">{st}</span>
                      {i < dp!.steps!.length - 1 && (
                        <span className="text-muted-foreground text-xs">→</span>
                      )}
                    </span>
                  ))}
                </div>
              ) : null}
              {stat && (
                <DetailRow label="Statistical model">
                  <Linkified text={stat} />
                </DetailRow>
              )}
            </div>
          </Section>
        );
      })()}

      {/* 8. Paper & protocol details */}
      {spec.publication && hasPublication(spec.publication) && (
        <Section title="Details" sub="paper & protocol">
          {(() => {
            const pub = spec.publication!;
            const href = pubHref(pub);
            const tput = throughputText(pub);
            const other = visibleOther(pub.other);
            return (
              <div className="space-y-2 text-sm leading-relaxed">
                {pub.original_publication?.title && (
                  <DetailRow label="Publication">
                    {href ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary hover:underline"
                      >
                        {pub.original_publication.title}
                      </a>
                    ) : (
                      pub.original_publication.title
                    )}
                    {(pub.original_publication.journal || pub.year != null) && (
                      <span className="text-muted-foreground">
                        {" — "}
                        {[pub.original_publication.journal, pub.year].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </DetailRow>
                )}
                {tput && (
                  <DetailRow label="Throughput">
                    <Linkified text={tput} />
                  </DetailRow>
                )}
                {other.map((o, i) => (
                  <DetailRow key={i} label={o.label}>
                    <Linkified text={o.value} />
                  </DetailRow>
                ))}
                {(pub.authors?.length ?? 0) > 0 && (
                  <div className="pt-1">
                    <button
                      onClick={() => setAuthorsOpen((o) => !o)}
                      className="hover:text-primary flex items-center gap-1 text-sm font-medium"
                    >
                      <ChevronRight
                        className={cn(
                          "size-3.5 shrink-0 transition-transform",
                          authorsOpen && "rotate-90",
                        )}
                      />
                      Authors
                      <span className="text-muted-foreground font-normal">{pub.authors!.length}</span>
                    </button>
                    {authorsOpen && (
                      <ul className="border-border/60 mt-1.5 space-y-1 border-l pl-3">
                        {pub.authors!.map((a, i) => (
                          <li key={i}>
                            <span className={a.corresponding ? "font-medium" : undefined}>
                              {a.name}
                            </span>
                            {a.corresponding && (
                              <Badge variant="secondary" className="ml-1.5 text-xs">
                                corresponding
                              </Badge>
                            )}
                            {a.email && (
                              <a
                                href={`mailto:${a.email}`}
                                className="text-primary ml-1.5 hover:underline"
                              >
                                {a.email}
                              </a>
                            )}
                            {a.affiliation && (
                              <div className="text-muted-foreground text-xs">{a.affiliation}</div>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            );
          })()}
        </Section>
      )}
    </div>
  );
}
