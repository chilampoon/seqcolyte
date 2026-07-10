import type { QcFinding, QcReport } from "./types";
import { libGenStepForCheck } from "./checkToLibGenStep";

/** Escape untrusted report text before interpolating into HTML. */
function esc(s: unknown): string {
  return String(s ?? "").replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string,
  );
}

const pct = (v: number | null | undefined): string =>
  v == null ? "—" : `${(v * 100).toFixed(1)}%`;

const verdictColor = (v: string): string =>
  v === "fail" ? "#ef4444" : v === "warn" ? "#f59e0b" : "#10b981";

function findingHtml(f: QcFinding): string {
  const step = libGenStepForCheck(f.check_id);
  const af = f.affected_fraction;
  const c = verdictColor(f.verdict);
  const val = f.unit === "fraction" ? pct(f.value) : `${esc(f.value)} ${esc(f.unit)}`;
  return `
  <div class="finding">
    <div class="finding-head">
      <span class="pill" style="color:${c};border-color:${c}55;background:${c}18">${esc(
        f.verdict.toUpperCase(),
      )}</span>
      <div class="grow">
        <div class="ftitle">${esc(f.title)}</div>
        <div class="muted small">${esc(f.detail)}</div>
      </div>
      <div class="fval">
        <div class="mono">${val}</div>
        <div class="muted mono xsmall">want ${esc(f.threshold)}</div>
      </div>
    </div>
    ${
      af != null
        ? `<div class="bar"><div style="width:${Math.min(
            100,
            af * 100,
          )}%;background:${c}"></div></div><div class="muted mono xsmall right">${pct(
            af,
          )} of reads</div>`
        : ""
    }
    ${
      f.evidence?.length
        ? `<div class="evidence">${f.evidence
            .map(
              (e) =>
                `<div class="ev"><code>${esc(e.spec_ref)}</code><span class="muted">${esc(
                  e.note,
                )}</span></div>`,
            )
            .join("")}</div>`
        : ""
    }
    ${step ? `<div class="chip">🧪 wet-lab step ${step.step}: ${esc(step.label)}</div>` : ""}
  </div>`;
}

function evalHtml(report: QcReport): string {
  const e = report.eval;
  if (!e) return "";
  const c = e.confusion;
  const tile = (label: string, v: number | null) =>
    `<div class="tile"><div class="tile-v">${v == null ? "—" : v.toFixed(3)}</div><div class="muted xsmall up">${label}</div></div>`;
  const cell = (label: string, v: number, good: boolean) =>
    `<div class="cell ${good ? "good" : "bad"}"><div class="cell-v">${v.toLocaleString()}</div><div class="muted xsmall">${label}</div></div>`;
  return `
  <section class="card">
    <h2>Self-scoring vs. ground-truth labels <span class="muted normal">did we catch the injected failures?</span></h2>
    <div class="tiles">${tile("precision", e.precision)}${tile("recall", e.recall)}${tile("f1", e.f1)}</div>
    <div class="matrix">
      ${cell("true positives (caught)", c.tp, true)}
      ${cell("false positives", c.fp, false)}
      ${cell("false negatives (missed)", c.fn, false)}
      ${cell("true negatives (clean)", c.tn, true)}
    </div>
    <p class="muted small">${e.n.toLocaleString()} read pairs · predicted ${
      e.predicted_affected?.toLocaleString() ?? "—"
    } affected vs. ${e.true_affected?.toLocaleString() ?? "—"} truly affected.</p>
  </section>`;
}

function diagnosisHtml(report: QcReport): string {
  const p = report.plan;
  if (!p) return "";
  const isLlm = p.method === "llm";
  return `
  <section class="card">
    <h2>Diagnosis <span class="badge ${isLlm ? "ai" : "det"}">${
      isLlm ? "AI diagnosis" : "deterministic"
    }</span></h2>
    ${
      p.llm_error
        ? `<div class="alert">AI ranking unavailable — deterministic fallback used.<div class="mono xsmall">${esc(
            p.llm_error,
          )}</div></div>`
        : ""
    }
    ${p.root_cause ? `<div class="up muted xsmall">root cause</div><p class="strong">${esc(p.root_cause)}</p>` : ""}
    ${p.diagnosis ? `<p>${esc(p.diagnosis)}</p>` : ""}
    ${
      p.ranked?.length
        ? `<div class="up muted xsmall">ranked findings</div><ul class="ranked">${p.ranked
            .map(
              (r) =>
                `<li><span class="sev sev-${esc(
                  r.severity,
                )}">${esc(r.severity)}</span> <code>${esc(r.check_id)}</code> <span class="muted">${esc(
                  r.why,
                )}</span></li>`,
            )
            .join("")}</ul>`
        : ""
    }
  </section>`;
}

/** Render a QC report (qc_report.json) as a self-contained, theme-aware HTML document. */
export function renderQcReportHtml(
  report: QcReport,
  meta: { runId: string; projectName: string },
): string {
  const overall = report.overall ?? "warn";
  const oc = verdictColor(overall);
  const profile = report.profile;
  const findings = report.findings ?? [];

  const body = `
  <header class="topbar">
    <div>
      <div class="up muted xsmall">QC report</div>
      <h1>${esc(meta.projectName)}</h1>
      <div class="muted small">${esc(report.platform ?? "")} · spec <code>${esc(
        report.spec_id ?? "",
      )}</code> · run <code>${esc(meta.runId)}</code></div>
    </div>
    <div class="verdict" style="color:${oc};border-color:${oc}55;background:${oc}14">
      <div class="verdict-v">${esc(overall.toUpperCase())}</div><div class="muted xsmall up">overall</div>
    </div>
  </header>
  ${
    profile
      ? `<div class="profile">
      <div><div class="mono strong">${profile.n_pairs.toLocaleString()}</div><div class="muted xsmall">read pairs</div></div>
      <div><div class="mono strong">${profile.r1_len.modal} bp</div><div class="muted xsmall">R1 modal</div></div>
      <div><div class="mono strong">${profile.r2_len.modal} bp</div><div class="muted xsmall">R2 modal</div></div>
    </div>`
      : ""
  }
  ${
    findings.length
      ? `<section class="card"><h2>Checks <span class="muted normal">${findings.length} run</span></h2>${findings
          .map(findingHtml)
          .join("")}</section>`
      : ""
  }
  ${diagnosisHtml(report)}
  ${evalHtml(report)}`;

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
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:20px; max-width:900px; }
  h1 { font-size:20px; margin:2px 0; font-weight:600; }
  h2 { font-size:14px; margin:0 0 12px; font-weight:600; }
  .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  .muted { color:var(--muted); } .small { font-size:12px; } .xsmall { font-size:11px; }
  .strong { font-weight:600; } .normal { font-weight:400; } .up { text-transform:uppercase; letter-spacing:.04em; }
  .right { text-align:right; } .grow { flex:1; min-width:0; }
  code { background:var(--code); padding:1px 5px; border-radius:4px; font-family:ui-monospace,monospace; font-size:12px; }
  .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px; }
  .verdict { border:1px solid; border-radius:10px; padding:8px 16px; text-align:center; }
  .verdict-v { font-size:18px; font-weight:700; }
  .profile { display:flex; gap:28px; padding:12px 0 20px; border-bottom:1px solid var(--border); margin-bottom:20px; }
  .card { border:1px solid var(--border); background:var(--card); border-radius:12px; padding:16px; margin-bottom:16px; }
  .finding { padding:12px 0; border-bottom:1px solid var(--border); }
  .finding:last-child { border-bottom:0; padding-bottom:0; }
  .finding-head { display:flex; gap:12px; align-items:flex-start; }
  .pill { border:1px solid; border-radius:6px; padding:2px 7px; font-size:10px; font-weight:700; }
  .ftitle { font-weight:500; }
  .fval { text-align:right; white-space:nowrap; }
  .bar { height:6px; background:var(--code); border-radius:3px; overflow:hidden; margin:8px 0 2px; }
  .bar > div { height:100%; }
  .evidence { margin-top:8px; display:flex; flex-direction:column; gap:4px; }
  .ev { font-size:11px; display:flex; gap:8px; } .ev code { flex-shrink:0; }
  .chip { display:inline-block; margin-top:8px; border:1px solid var(--border); border-radius:6px; padding:2px 8px; font-size:11px; color:var(--muted); }
  .tiles { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:12px; }
  .tile { background:var(--code); border-radius:8px; padding:12px; text-align:center; }
  .tile-v { font-size:22px; font-weight:600; font-family:ui-monospace,monospace; }
  .matrix { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .cell { border-radius:8px; padding:12px; border:1px solid; }
  .cell.good { border-color:#10b98155; background:#10b98110; } .cell.bad { border-color:#ef444455; background:#ef444410; }
  .cell-v { font-size:18px; font-weight:600; font-family:ui-monospace,monospace; }
  .badge { font-size:10px; border-radius:5px; padding:2px 7px; font-weight:600; }
  .badge.ai { color:#6366f1; background:#6366f118; border:1px solid #6366f155; } .badge.det { color:var(--muted); background:var(--code); border:1px solid var(--border); }
  .alert { border:1px solid #f59e0b55; background:#f59e0b12; border-radius:8px; padding:10px; margin-bottom:12px; font-size:12px; }
  .ranked { list-style:none; padding:0; margin:6px 0 0; display:flex; flex-direction:column; gap:6px; }
  .ranked li { font-size:12px; }
  .sev { font-size:10px; font-weight:600; border-radius:4px; padding:1px 6px; text-transform:uppercase; }
  .sev-high { color:#ef4444; background:#ef444418; } .sev-medium { color:#f59e0b; background:#f59e0b18; }
  .sev-low { color:#3b82f6; background:#3b82f618; } .sev-none { color:var(--muted); background:var(--code); }
</style>
</head>
<body>${body}</body>
</html>`;
}
