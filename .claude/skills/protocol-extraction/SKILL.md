---
name: protocol-extraction
description: Rules for extracting oligos, step-by-step library generation, and the final library structure from a single-cell sequencing protocol PDF into the Seqcolyte spec (seqcolyte.spec.v1). Use this whenever running or improving `python -m extract from-doc`, or when parsing a 10x / Illumina / droplet library-prep protocol into oligos + library structure. Encodes canonical oligo names, placeholder tokens, verified adapter sequences, per-step ASCII product diagrams, and the scg_lib_structs color convention.
---

# Protocol → Seqcolyte spec extraction

Turn a protocol document into the spec's `oligos`, `library_generation` (with a per-step
`product` diagram), and `final_library`. The LLM output is **never silently trusted** — it is
cross-checked against `extract/verified_constants.py` and the checked-in groundtruth.

Companion resources (read for depth): `~/playground/cdna/skills/SKILL.md` (the
`seq-protocol-parser` skill — ASCII-diagram conventions), `~/playground/libstruct-bench/docs/oligo_extraction.md`
(placeholder policy + naming), and `~/playground/protocols-test/groundtruth_oligos.tsv` (canonical names).

## 1. Oligos — complete, exact, canonically named

- Extract **every** named oligo; do not stop early. For a 10x-style 3′ kit expect: Beads-oligo-dT,
  Template Switching Oligo (TSO), cDNA Forward primer, cDNA Reverse primer, Illumina TruSeq Read 1
  primer, Illumina TruSeq Read 2 primer, TruSeq adapter (double-stranded), Library PCR Primer 1,
  Library PCR Primer 2, Sample Index sequencing primer, Illumina P5 adapter, Illumina P7 adapter.
- **Name** each oligo with its canonical protocol name (match `groundtruth_oligos.tsv`, e.g.
  "Beads-oligo-dT", "Illumina P5 adapter", "Template Switching Oligo (TSO)") — a human-readable name,
  never just the `oligo_id`. `oligo_id` is `lowercase_snake_case` (e.g. `oligo_template_switching_oligo_tso`).
- Do **not** reverse-complement, complete, repair, or invent sequences. Transcribe exact characters.
- Preserve strand orientation (`5_to_3` / `3_to_5`). Double-stranded adapters → `kind: "double_stranded"`,
  `sequence: ""`, both strands in `components`.
- Fill `components` for assembled oligos (`kind: "assembled"`): one entry per named sub-part with its
  own `name` + `sequence` + `role`. Component names drive the display coloring — use recognizable
  labels (see §4) like "Partial TruSeq Read 1", "10x Barcode", "UMI", "Poly(dT)VN", "P5", "P7", "TSO".

### Placeholder tokens `[ROLE:LENGTH]`

Replace variable regions with canonical tokens, keeping the exact bp count:
`[CELL_BARCODE:N]` · `[UMI:N]` · `[SAMPLE_INDEX:N]` (i7/i5) · `[CDNA]` (the insert, no length).
Other roles when present: `[I5_INDEX:N]`, `[I7_INDEX:N]`, `[RT_BARCODE:N]`, `[LIGATION_BARCODE:N]`,
`[FEATURE_BARCODE:N]`, `[TN5_INDEX:N]`, `[RANDOM:N]`/`[PHASE_BLOCK:N]`. Infer a bare token's length
from the surrounding table before writing it. Keep IUPAC letters (V, N, B…) and chemistry markers
(`rG`, `/5Biosg/`, `*`) literal — never as placeholders.

### Verified sequences (soft cross-check — must match unless the doc clearly differs)

```
P5                 AATGATACGGCGACCACCGAGATCTACAC
P7                 CAAGCAGAAGACGGCATACGAGAT          (final-library P7 end is revcomp: ATCTCGTATGCCGTCTTCTGCTTG)
TSO                AAGCAGTGGTATCAACGCAGAGTACATGGG    (rGrGrG → GGG)
Partial TruSeq R1  CTACACGACGCTCTTCCGATCT
TruSeq Read 1      ACACTCTTTCCCTACACGACGCTCTTCCGATCT
TruSeq Read 2      GTGACTGGAGTTCAGACGTGTGCTCTTCCGATCT
TruSeq adapter fwd GATCGGAAGAGCACACGTCTGAACTCCAGTCA
```

poly(dT): write the EXACT number of T's shown (10x uses 30); if a `VN` (or `V N`) anchor follows,
append the literal `VN`.

## 2. Library generation — step-by-step, with a per-step product

`library_generation` is the ordered build workflow. Each entry:
`{step, title, note, product}`.

- `title`: short step name (e.g. "mRNA capture & reverse transcription (GEM-RT)").
- `note`: plain-English biology — the enzyme(s) and purpose.
- `product`: a **monospace ASCII diagram** of the molecular product *after* that step. This is the
  highest-value field for review — every step that changes the molecule gets one.

The last step's `product` MUST equal the assembled `final_library.annotated_library_sequence`.

### Reference: scg_lib_structs methods_html

The gold-standard per-step diagrams live in `~/playground/protocols-test/scg_html/` (69 protocols,
e.g. `10xChromium3.html`, `Drop-seq.html`, `10xChromium_scATAC.html`). Each page's "Step-by-step
library generation" section is a series of `<pre>` product diagrams in exactly this style — use them
as the template for structure, notation, and alignment. When a matching page exists for the protocol
being parsed, mirror its steps and products. **Accuracy is best-effort for now**: reconstruct products
from the protocol PDF in the scg_lib_structs style; do not fabricate sequences the document doesn't
support. (A curated "sequencing-tech wiki" built from `scg_html` will later back these products in the
Studio — until then, treat scg_lib_structs as the style + sanity reference, not a guaranteed source.)

Example step product (10x 3′, from `10xChromium3.html`):

```
(3) Adding TSO for second strand synthesis:
|--5'- CTACACGACGCTCTTCCGATCT[16-bp cell barcode][10-bp UMI](dT)VXXXXXXXXX...XXXXXXXXXCCC------->
                                                   TACATGAGACGCAACTATGGTGACGAA    -5'
```

### ASCII diagram conventions (spaces only, never tabs)

```
5'- SEQ -3'            sense strand, left→right
3'- SEQ -5'            antisense strand
-------->  <--------   polymerase extension direction
|--5'-                 attached to a gel bead
[CELL_BARCODE:16]      named variable region (keep bp count)
[UMI:12] [SAMPLE_INDEX:8]
[CDNA]                 the cDNA insert
(T)30VN                poly-dT with anchor
*A  A*                 A-tail overhang
rG                     RNA base
```

- Write adapters/primers **in full** — never truncate with `...`.
- When a primer anneals, put it on its own line and align its binding site directly above/below the
  construct by counting exact character offsets (verify 2–3 landmark bases line up).
- For steps with multiple products (e.g. after fragmentation), show each and note which are amplifiable.

Worked template (barcoded-bead / capture-RT style):

```
(1) product after gel-bead RT primer capture + reverse transcription:
|--5'- CTACACGACGCTCTTCCGATCT[CELL_BARCODE:16][UMI:12](T)30VN[CDNA]------->
                                                       3'- XXXXXXXXXX...mRNA -5'
```

## 3. Final library

`final_library.annotated_library_sequence`: the full 5′→3′ top strand assembled with tokens exactly:

```
P5 + TruSeqRead1 + [CELL_BARCODE:16] + [UMI:12] + (T)30 + VN + [CDNA] + <Read2 adapter> + [SAMPLE_INDEX:8] + revcomp(P7)
```

`final_library.annotation_lines`: one `"<sequence-or-token> = <label>"` per part in 5′→3′ order — this
is what the UI colors, so label each part with a name that maps to a type in §4 (P5, TruSeq Read 1,
10x Barcode, UMI, poly(dT), cDNA insert, TruSeq Read 2 adapter, i7 sample index, reverse complement of P7).
`final_library.strands`: include the raw 5_to_3 (and 3_to_5 if shown) strand text exactly as written.

## 3b. Library sequencing — how each read comes off the instrument

`library_sequencing` is a distinct section (it renders **after** library generation, **before** read
structure). One entry per read in sequencing order — Read 1, Index 1 (i7), Index 2 (i5) if dual-indexed,
Read 2: `{read, primer, template ("top"|"bottom"), cycles (bp), note, diagram}`.

`diagram` shows the **sequencing primer annealing to the full final-library construct** (both strands,
sequences written out) with a `------->` / `<-------` arrow for the read direction. `N` for each
unknown barcode/index position, `X` for the cDNA insert. Same alignment discipline as the step products
(spaces only; count offsets so the primer sits directly above/below its binding site). The gold-standard
diagrams are the "Library sequencing:" `<pre>` blocks in `~/playground/protocols-test/scg_html/` — mirror
them. Example (10x 3′ Read 1, off the bottom strand):

```
                         5'- ACACTCTTTCCCTACACGACGCTCTTCCGATCT------------------------->
3'- ...GATGTGCTGCGAGAAGGCTAGANNNNNNNNNNNNNNNNNNNNNNNNNN(pA)BXXX...XXXTCTAGCCTTCTCG... -5'
```

Accuracy is best-effort (reconstruct from the protocol in scg_lib_structs style; don't fabricate).

## 4. Consistent colors (scg_lib_structs convention)

So common parts read the same color across every protocol, label components/annotations so they map to
these canonical types (colors from Teichlab/scg_lib_structs `page_format.css`, mirrored in
`studio/src/lib/oligoColors.ts`):

| part | matches (in name/label) | color |
|---|---|---|
| P5 | `p5` | `#08519c` |
| P7 | `p7` | `#a50f15` |
| Read 1 primer | truseq/nextera read 1, r1 | `#6baed6` |
| Read 2 adapter | truseq/nextera read 2, r2 | `#fc9272` |
| Cell barcode | barcode, cbc | `#f768a1` |
| UMI | umi | `#807dba` |
| TSO | tso, template switch | `#2ca25f` |
| poly(dT) | poly(dt)/poly(a) | `#ca8a04` |
| Sample index | sample index, i7/i5 | `#0891b2` |
| cDNA insert | cdna, insert | `#64748b` |
| Capture seq | capture | `#0000ff` |

The display auto-colors by matching these keywords, so choosing clear part names (not opaque ids) is
what makes the report readable.

## 5. Output discipline

Output ONLY the structured JSON for the schema — no commentary, no meta-notes about tools/skills.
Be complete (every oligo, every build step, a product per step). When a sequence is genuinely absent
from the document, leave it out rather than inventing it; the cross-check will flag gaps.
