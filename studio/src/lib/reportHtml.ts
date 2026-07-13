import type { QcFinding, QcReport } from "./types";

/** Escape untrusted report text before interpolating into HTML. */
function esc(s: unknown): string {
  return String(s ?? "").replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string,
  );
}

const pct = (v: number | null | undefined): string =>
  v == null ? "—" : `${(v * 100).toFixed(1)}%`;

const isIssue = (f: QcFinding): boolean => f.verdict === "fail" || f.verdict === "warn";

interface CheckKnowledge {
  rootCause: string;
  fix: string;
  references?: { label: string; url: string; why: string }[];
}

const TENX_GUIDE = "https://www.10xgenomics.com/support";

/**
 * Per-check root cause + suggested fix (+ optional references), keyed by the QC engine's check ids.
 * This is the general rule applied to every QC execution — grounded in the diagnostic catalog's
 * causes/adapters. A check not listed here falls back to whatever the finding's own detail carries.
 */
const CHECK_KNOWLEDGE: Record<string, CheckKnowledge> = {
  // --- Illumina short-read checks ---
  tso_at_r2_start: {
    rootCause:
      "Read 2 begins with template-switch-oligo (TSO) sequence instead of cDNA. This is the signature of short or empty cDNA inserts — adapter dimers and short fragments where the read runs past the tiny insert into the TSO handle.",
    fix: "Trim the leading TSO from R2 before alignment. The root fix is at the bench: tighten SPRI/bead size selection to remove short inserts and adapter dimers, and confirm cDNA yield before library construction.",
    references: [
      {
        label: "10x Chromium Single Cell 3′ Reagent Kits User Guide",
        url: TENX_GUIDE,
        why: "the expected R2 structure — R2 should start with cDNA, not the TSO handle",
      },
    ],
  },
  r2_adapter_readthrough: {
    rootCause:
      "Read 2 runs through the insert into the Illumina adapter stem (AGATCGGAAGAGC), meaning inserts are shorter than the read length — short fragments or residual adapter dimers.",
    fix: "Adapter-trim R2 (cutadapt / fastp) before alignment to recover the usable portion. To fix the source, improve size selection so inserts exceed the read length.",
  },
  r2_polyg_tail: {
    rootCause:
      "Read 2 ends in a poly-G run. On two-colour Illumina instruments (NovaSeq/NextSeq) a 'no-signal' base is called G, so poly-G tails mark reads that ran past the insert end or lost signal — usually short inserts.",
    fix: "Trim 3′ poly-G tails (e.g. fastp --trim_poly_g) before alignment. Because the underlying cause is short inserts, improving size selection removes both the poly-G and the read-through.",
  },
  whitelist_hit_rate: {
    rootCause:
      "Few cell barcodes match the chemistry whitelist. This points to the wrong chemistry/whitelist being used, or a barcode-position offset where extraction reads the barcode at the wrong bases.",
    fix: "Confirm the chemistry and whitelist match the kit. Scan a small barcode offset and alternative whitelists; if a shift or wrong whitelist is found, re-extract barcodes computationally — no re-sequencing needed.",
    references: [
      {
        label: "10x Chromium Single Cell 3′ Reagent Kits User Guide",
        url: TENX_GUIDE,
        why: "the cell-barcode position and the correct whitelist for each chemistry",
      },
    ],
  },
  r1_length: {
    rootCause:
      "Read 1 is not the length the chemistry expects (it must cover the 16 bp cell barcode + 12 bp UMI). A wrong R1 length means barcodes/UMIs can't be extracted — a read-configuration mismatch (wrong cycles, wrong chemistry, or R1/R2 swapped).",
    fix: "Audit the sequencing read layout against the chemistry. If only extraction was misconfigured, re-extract; if the run used the wrong cycle count, additional sequencing or a rerun is required.",
    references: [
      {
        label: "10x Chromium Single Cell 3′ Reagent Kits User Guide",
        url: TENX_GUIDE,
        why: "the expected R1 cycle count and barcode + UMI layout",
      },
    ],
  },
  // --- Nanopore long-read checks ---
  tso_concatemer: {
    rootCause:
      "A fraction of long reads carry an internal TSO/adapter2 copy mid-read — the signature of template-switch concatemers or two cDNAs fused into one read during library prep.",
    fix: "Split reads at the internal TSO junctions computationally to recover the individual molecules. At the bench, the optional enriched profile — full-length biotinylated-primer streptavidin pull-down (ONT SST_9198) — depletes these artifacts; the baseline direct-ligation prep does not.",
    references: [
      {
        label: "GoT-Splice — Cortes-Lopez et al., Cell Stem Cell 2023",
        url: "https://www.cell.com/cell-stem-cell/fulltext/S1934-5909(23)00257-6",
        why: "the sc-Nanopore MDS study this dataset models — how internal-TSO / fused reads are handled downstream",
      },
      {
        label: "ScNaUmi-seq / Sicelore — Lebrigand et al., Nat Commun 2020",
        url: "https://www.nature.com/articles/s41467-020-17800-6",
        why: "the nanopore single-cell method — detecting these artifacts and splitting fused reads",
      },
    ],
  },
};

/** A deterministic 0–100 quality score from the finding severities (fail full weight, warn 0.6×). */
function scoreOf(findings: QcFinding[]): { score: number; band: "good" | "warn" | "critical" } {
  let keep = 1;
  for (const f of findings) {
    if (!isIssue(f)) continue;
    const s = Math.max(0, Math.min(1, f.severity ?? 0));
    keep *= 1 - (f.verdict === "warn" ? s * 0.6 : s);
  }
  const score = Math.round(100 * keep);
  const band = score >= 80 ? "good" : score >= 50 ? "warn" : "critical";
  return { score, band };
}

const BAND_COLOR = { good: "#10b981", warn: "#f59e0b", critical: "#ef4444" } as const;
const BAND_LABEL = { good: "Good", warn: "Needs attention", critical: "Critical" } as const;
const sevColor = (v: string): string =>
  v === "fail" ? "#ef4444" : v === "warn" ? "#f59e0b" : "#10b981";

/** Strip machine-format debris (raw dicts) and the trailing "Fix: …" from a detail string. */
function cleanDetail(detail: string): string {
  return String(detail ?? "")
    .replace(/\.?\s*Categories:\s*\{[^}]*\}\.?/gi, "")
    .replace(/\{[^{}]*\}/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Split a detail into the root-cause description and the suggested fix (on "Fix:"). */
function splitDetail(detail: string): { cause: string; fix: string | null } {
  const raw = String(detail ?? "");
  const i = raw.search(/\bFix:\s*/i);
  if (i === -1) return { cause: cleanDetail(raw), fix: null };
  return {
    cause: cleanDetail(raw.slice(0, i)),
    fix: cleanDetail(raw.slice(i).replace(/^\s*Fix:\s*/i, "")) || null,
  };
}

const fmtValue = (f: QcFinding): string =>
  f.unit === "fraction" ? pct(f.value) : `${esc(f.value)} ${esc(f.unit)}`;

/** A structured card for a failing/warning check: issue → root cause → suggested fix (with references). */
function issueCard(f: QcFinding): string {
  const c = sevColor(f.verdict);
  const k = CHECK_KNOWLEDGE[f.check_id];
  const detail = splitDetail(f.detail);
  const rootCause = k?.rootCause ?? detail.cause;
  const fix = k?.fix ?? detail.fix;
  const refs = k?.references;
  const af = f.affected_fraction;
  return `
  <div class="issue" style="border-color:${c}44">
    <div class="issue-head">
      <span class="pill" style="color:${c};border-color:${c}55;background:${c}18">${esc(
        f.verdict.toUpperCase(),
      )}</span>
      <div class="grow"><div class="issue-title">${esc(f.title)}</div></div>
      <div class="fval"><div class="mono strong">${fmtValue(f)}</div><div class="muted mono xsmall">want ${esc(
        f.threshold,
      )}</div></div>
    </div>
    ${
      af != null
        ? `<div class="bar"><div style="width:${Math.min(100, af * 100)}%;background:${c}"></div></div>`
        : ""
    }
    ${rootCause ? `<div class="sec"><div class="sec-h">Root cause</div><p>${esc(rootCause)}</p></div>` : ""}
    ${
      fix
        ? `<div class="sec"><div class="sec-h">Suggested fix</div><p>${esc(fix)}</p>${
            refs?.length
              ? `<div class="refs-block"><div class="sec-h2">References — where to look</div><ul class="refs">${refs
                  .map(
                    (r) =>
                      `<li><a href="${esc(r.url)}" target="_blank" rel="noreferrer">${esc(
                        r.label,
                      )}</a> <span class="muted">— ${esc(r.why)}</span></li>`,
                  )
                  .join("")}</ul></div>`
              : ""
          }</div>`
        : ""
    }
  </div>`;
}

/** A compact one-line row for a passing / descriptive check. */
function otherRow(f: QcFinding): string {
  const mark = f.verdict === "pass" ? "✓" : "·";
  return `<div class="orow"><span class="ok">${mark}</span><span class="oname">${esc(
    f.title,
  )}</span><span class="mono muted oval">${fmtValue(f)}</span><span class="muted small odetail">${esc(
    cleanDetail(f.detail),
  )}</span></div>`;
}

/** Render a QC report (qc_report.json) as a self-contained, theme-aware HTML document. */
export function renderQcReportHtml(
  report: QcReport,
  meta: { runId: string; projectName: string },
): string {
  const profile = report.profile;
  const findings = report.findings ?? [];
  const nano = report.platform === "nanopore";
  const { score, band } = scoreOf(findings);
  const bc = BAND_COLOR[band];

  const issues = findings.filter(isIssue).sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0));
  const others = findings.filter((f) => !isIssue(f));

  const body = `
  <header class="topbar">
    <div>
      <div class="up muted xsmall">QC report</div>
      <h1>${esc(meta.projectName)}</h1>
      <div class="muted small">${esc(report.platform ?? "")} · spec <code>${esc(
        report.spec_id ?? "",
      )}</code> · run <code>${esc(meta.runId)}</code></div>
    </div>
    <div class="score" style="color:${bc};border-color:${bc}55;background:${bc}12">
      <div class="score-v">${score}<span class="score-max">/100</span></div>
      <div class="xsmall up strong">${esc(BAND_LABEL[band])}</div>
    </div>
  </header>
  ${
    profile
      ? nano
        ? `<div class="profile">
      <div><div class="mono strong">${profile.n_pairs.toLocaleString()}</div><div class="muted xsmall">reads</div></div>
      <div><div class="mono strong">${profile.r1_len.modal} bp</div><div class="muted xsmall">modal read length</div></div>
      <div><div class="mono strong">${profile.r1_len.max.toLocaleString()} bp</div><div class="muted xsmall">longest read</div></div>
    </div>`
        : `<div class="profile">
      <div><div class="mono strong">${profile.n_pairs.toLocaleString()}</div><div class="muted xsmall">read pairs</div></div>
      <div><div class="mono strong">${profile.r1_len.modal} bp</div><div class="muted xsmall">R1 modal</div></div>
      <div><div class="mono strong">${profile.r2_len.modal} bp</div><div class="muted xsmall">R2 modal</div></div>
    </div>`
      : ""
  }
  ${
    issues.length
      ? `<section class="card"><h2>Issues <span class="muted normal">${issues.length} of ${
          findings.length
        } checks need attention</span></h2>${issues.map(issueCard).join("")}</section>`
      : `<section class="card ok-card"><h2>No issues</h2><p class="muted small">All ${findings.length} checks passed.</p></section>`
  }
  ${
    others.length
      ? `<section class="card"><h2>Other checks <span class="muted normal">${others.length} passed</span></h2>${others
          .map(otherRow)
          .join("")}</section>`
      : ""
  }`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>QC report · ${esc(meta.projectName)}</title>
<style>
  :root {
    --bg:#ffffff; --fg:#0a0a0a; --muted:#6b7280; --card:#ffffff; --border:#e5e7eb; --code:#f3f4f6;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0a0a0a; --fg:#ededed; --muted:#9ca3af; --card:#141414; --border:#262626; --code:#1f1f1f; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:20px; max-width:820px; }
  h1 { font-size:20px; margin:2px 0; font-weight:600; }
  h2 { font-size:14px; margin:0 0 14px; font-weight:600; }
  p { margin:0; }
  .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  .muted { color:var(--muted); } .small { font-size:12px; } .xsmall { font-size:11px; }
  .strong { font-weight:600; } .normal { font-weight:400; } .up { text-transform:uppercase; letter-spacing:.04em; }
  .grow { flex:1; min-width:0; }
  code { background:var(--code); padding:1px 5px; border-radius:4px; font-family:ui-monospace,monospace; font-size:12px; }
  a { color:inherit; }
  .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px; }
  .score { border:1px solid; border-radius:12px; padding:10px 18px; text-align:center; min-width:110px; }
  .score-v { font-size:30px; font-weight:700; line-height:1; }
  .score-max { font-size:13px; font-weight:600; opacity:.7; }
  .profile { display:flex; gap:28px; padding:12px 0 20px; border-bottom:1px solid var(--border); margin-bottom:20px; }
  .card { border:1px solid var(--border); background:var(--card); border-radius:12px; padding:16px; margin-bottom:16px; }
  .ok-card h2 { color:#10b981; }
  .issue { border:1px solid; border-radius:10px; padding:14px; margin-bottom:12px; }
  .issue:last-child { margin-bottom:0; }
  .issue-head { display:flex; gap:12px; align-items:flex-start; margin-bottom:4px; }
  .issue-title { font-weight:600; font-size:15px; }
  .pill { border:1px solid; border-radius:6px; padding:2px 7px; font-size:10px; font-weight:700; flex-shrink:0; }
  .fval { text-align:right; white-space:nowrap; }
  .bar { height:6px; background:var(--code); border-radius:3px; overflow:hidden; margin:6px 0 10px; }
  .bar > div { height:100%; }
  .sec { margin-top:12px; }
  .sec-h { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:600; margin-bottom:3px; }
  .refs-block { margin-top:10px; padding:8px 12px; border-left:2px solid var(--border); background:var(--code); border-radius:0 6px 6px 0; }
  .sec-h2 { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:600; margin-bottom:4px; }
  .refs { margin:0; padding-left:18px; } .refs li { margin:3px 0; font-size:12px; }
  .refs a { text-decoration:underline; text-underline-offset:2px; }
  .orow { display:flex; align-items:baseline; gap:10px; padding:6px 0; border-bottom:1px solid var(--border); }
  .orow:last-child { border-bottom:0; }
  .ok { color:#10b981; width:12px; flex-shrink:0; }
  .oname { font-weight:500; flex-shrink:0; }
  .oval { flex-shrink:0; } .odetail { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  @media (max-width:560px) { .odetail { display:none; } }
</style>
</head>
<body>${body}</body>
</html>`;
}
