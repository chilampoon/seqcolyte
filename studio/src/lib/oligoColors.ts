/**
 * Consistent per-oligo colors so common parts (P5, P7, cell barcode, UMI, TSO,
 * read primers, sample index…) read the same across every protocol — following
 * the scg_lib_structs convention (Teichlab/scg_lib_structs `page_format.css`).
 */

export type OligoType =
  | "p5"
  | "p7"
  | "read1"
  | "read2"
  | "cell_barcode"
  | "umi"
  | "tso"
  | "poly_dt"
  | "sample_index"
  | "capture"
  | "cdna"
  | "me"
  | "other";

/** Hex colors: scg_lib_structs values where defined, sensible additions otherwise. */
export const OLIGO_COLORS: Record<OligoType, string> = {
  p5: "#08519c", // scg p5
  p7: "#a50f15", // scg p7
  read1: "#6baed6", // scg s5 — Read 1 sequencing primer (TruSeq/Nextera Read 1)
  read2: "#fc9272", // scg s7 — Read 2 adapter (TruSeq/Nextera Read 2)
  cell_barcode: "#f768a1", // scg cbc
  umi: "#807dba", // scg umi
  tso: "#2ca25f", // scg tso
  capture: "#0000ff", // scg cs1
  me: "#969696", // scg me — Nextera mosaic end
  poly_dt: "#ca8a04", // added — poly(dT)/poly(A)
  sample_index: "#0891b2", // added — i7 / i5 sample index
  cdna: "#64748b", // added — variable cDNA insert
  other: "#94a3b8",
};

export const OLIGO_LABELS: Record<OligoType, string> = {
  p5: "P5",
  p7: "P7",
  read1: "Read 1 primer",
  read2: "Read 2 adapter",
  cell_barcode: "Cell barcode",
  umi: "UMI",
  tso: "TSO",
  poly_dt: "poly(dT)",
  sample_index: "Sample index",
  capture: "Capture seq",
  me: "Mosaic end",
  cdna: "cDNA insert",
  other: "Other",
};

/** Map a component / segment / annotation label to a canonical oligo type. */
export function oligoType(label: string): OligoType {
  const s = label.toLowerCase();
  if (/\bp5\b/.test(s)) return "p5";
  if (/\bp7\b/.test(s)) return "p7";
  if (/tso|template.?switch/.test(s)) return "tso";
  if (/barcode|\bcbc\b/.test(s)) return "cell_barcode";
  if (/\bumi\b/.test(s)) return "umi";
  if (/poly.?\(?d?t\)?|poly.?a\b|\bdt\)?vn\b/.test(s)) return "poly_dt";
  if (/sample.?index|\bi7\b|\bi5\b|\bindex\b/.test(s)) return "sample_index";
  if (/capture/.test(s)) return "capture";
  if (/cdna|insert/.test(s)) return "cdna";
  if (/mosaic|\bme\b/.test(s)) return "me";
  if (/read.?2|\br2\b/.test(s)) return "read2";
  if (/read.?1|\br1\b/.test(s)) return "read1";
  return "other";
}

export const colorFor = (label: string): string => OLIGO_COLORS[oligoType(label)];

/** True for a schematic token like `[CELL_BARCODE:16]` or `[CDNA]`. */
export const isToken = (seq: string): boolean => /^\s*\[[^\]]+\]\s*$/.test(seq);

/** Split a raw sequence into token / literal-base parts (fallback when no components). */
export function splitSequence(seq: string): { text: string; token: boolean }[] {
  const parts: { text: string; token: boolean }[] = [];
  const re = /\[[^\]]+\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(seq))) {
    if (m.index > last) parts.push({ text: seq.slice(last, m.index), token: false });
    parts.push({ text: m[0], token: true });
    last = re.lastIndex;
  }
  if (last < seq.length) parts.push({ text: seq.slice(last), token: false });
  return parts;
}

/** Derive an oligo type from a schematic token name, e.g. `[CELL_BARCODE:16]` → cell_barcode. */
export function tokenType(token: string): OligoType {
  return oligoType(token.replace(/[[\]]/g, "").replace(/:\d+/g, ""));
}

// ---------- ASCII library-generation diagram colorizing ----------
//
// Colors the sequences inside the scg_lib_structs-style step diagrams WITHOUT touching
// any character — coloring is span-only, so the 5'->3' / 3'->5' strand alignment in the
// monospace <pre> is preserved exactly.

const _COMP: Record<string, string> = {
  A: "T", T: "A", G: "C", C: "G", N: "N", U: "A",
  R: "Y", Y: "R", S: "S", W: "W", K: "M", M: "K", B: "V", V: "B", D: "H", H: "D",
};
const complement = (s: string): string =>
  s.split("").map((c) => _COMP[c] ?? c).join("");
const revcomp = (s: string): string => complement(s).split("").reverse().join("");

/** Canonical 10x / Illumina constant sequences (extended per-spec at call time). */
const CONSTANTS: [string, OligoType][] = [
  ["AATGATACGGCGACCACCGAGATCTACAC", "p5"],
  ["CAAGCAGAAGACGGCATACGAGAT", "p7"],
  ["AAGCAGTGGTATCAACGCAGAGTACATGGG", "tso"],
  ["ACACTCTTTCCCTACACGACGCTCTTCCGATCT", "read1"], // full TruSeq Read 1
  ["TCTTTCCCTACACGACGCTCTTCCGATCT", "read1"], // TruSeq Read 1 with ACAC shared into P5
  ["CTACACGACGCTCTTCCGATCT", "read1"], // partial TruSeq Read 1 handle
  ["AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC", "read2"], // TruSeq Read 2 adapter
  ["GTGACTGGAGTTCAGACGTGTGCTCTTCCGATCT", "read2"], // TruSeq Read 2 primer
  ["GATCGGAAGAGCACACGTCTGAACTCCAGTCA", "read2"],
  ["CTGTCTCTTATACACATCT", "me"], // Nextera mosaic end
];

/** Build a longest-first sequence→type index (forward + complement + revcomp of each). */
export function buildSeqIndex(extra: [string, OligoType][] = []): [string, OligoType][] {
  const out = new Map<string, OligoType>();
  for (const [seq, t] of [...CONSTANTS, ...extra]) {
    const s = seq.toUpperCase().replace(/[^ACGTNUVBDHKMRSWY]/g, "");
    if (s.length < 6) continue;
    for (const v of [s, complement(s), revcomp(s)]) if (!out.has(v)) out.set(v, t);
  }
  return [...out.entries()].sort((a, b) => b[0].length - a[0].length);
}

export type DiagramSeg = { text: string; type: OligoType | null };

/**
 * Split a step-product diagram into colored / plain segments. Tokens, poly-runs, cDNA
 * X-runs, and known constant sequences (both strands, via the index) get a type; structural
 * characters (`5'-`, arrows, spaces, newlines) stay plain. Character-preserving → alignment-safe.
 */
export function colorizeDiagram(text: string, index: [string, OligoType][]): DiagramSeg[] {
  const segs: DiagramSeg[] = [];
  let buf = "";
  const flush = () => {
    if (buf) segs.push({ text: buf, type: null });
    buf = "";
  };
  const push = (t: string, ty: OligoType) => {
    flush();
    segs.push({ text: t, type: ty });
  };

  let i = 0;
  while (i < text.length) {
    const rest = text.slice(i);
    let m = /^\[[^\]]+\]/.exec(rest); // placeholder token
    if (m) {
      const ty = /mrna/i.test(m[0]) ? "cdna" : tokenType(m[0]);
      push(m[0], ty);
      i += m[0].length;
      continue;
    }
    m = /^\((?:d?T|A|pA)\)\d*[VBN]*/i.exec(rest); // poly-dT / poly-A
    if (m) {
      push(m[0], "poly_dt");
      i += m[0].length;
      continue;
    }
    m = /^X{2,}/i.exec(rest); // cDNA insert placeholder
    if (m) {
      push(m[0], "cdna");
      i += m[0].length;
      continue;
    }
    const upper = rest.toUpperCase(); // constant sequence (longest match, either strand)
    let hit: [string, OligoType] | null = null;
    for (const [seq, ty] of index) {
      if (upper.startsWith(seq)) {
        hit = [seq, ty];
        break;
      }
    }
    if (hit) {
      push(rest.slice(0, hit[0].length), hit[1]);
      i += hit[0].length;
      continue;
    }
    buf += text[i];
    i++;
  }
  flush();
  return segs;
}
