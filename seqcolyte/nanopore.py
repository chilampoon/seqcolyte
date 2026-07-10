"""Nanopore (long-read) 10x 3' chemistry — the single source of truth for sequences and the
canonical amplified-cDNA molecule structure, shared by the simulator, QC, spec, and tests.

The Nanopore branch sequences **full-length amplified 10x cDNA** — it diverges from the Illumina
workflow *before* fragmentation / TruSeq ligation / i7 PCR / P5–P7 construction. The canonical
adapter1-first amplified-cDNA strand is::

    [R1_HANDLE][CB:16][UMI:12][polyT:30][V][N][cDNA][TSO_RC]

Because a Nanopore pore reads a single strand and either molecule end may enter first, a raw read
may be in either orientation (canonical, or its reverse complement).

Evidence / provenance
---------------------
- ``R1_HANDLE`` / ``TSO`` : 10x Genomics CG000204 (Chromium Next GEM Single Cell 3' v3.1 user guide);
  the physical TSO ends in three riboguanosines (rGrGrG) — represented here as ``GGG`` for sequence
  matching only; RNA chemistry is preserved in annotations.
- ``TSO_RC`` : DERIVED = reverse_complement(TSO). Never treated as independently observed.
- ``ADAPTER2_MOTIF`` : the shorter ONT/EPI2ME "adapter2" orientation motif (TSO_RC minus the leading
  CCC), used by wf-single-cell for stranding.
- ``ONT_FWD_PRIMER`` / ``ONT_REV_PRIMER`` : the two custom PCR primers stated verbatim in Oxford Nanopore
  SST_9198_v114_revP_06Oct2025. They belong to the OPTIONAL biotin-enrichment profile, not the baseline
  direct-ligation model; kept only as reference values.
- ONT ligation adapter + motor protein (SQK-LSK114): technical components of the physical library, not
  terminal nucleotide sequences. Their exact bases are not represented in this specification — modeled as
  non-sequence markers, never invented and never embedded inside a nucleotide string.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------- sequences

R1_HANDLE = "CTACACGACGCTCTTCCGATCT"  # partial TruSeq Read 1 (10x GEM bead handle)
TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"  # terminal rGrGrG → GGG for matching only

# ONT/EPI2ME "adapter2" orientation motif = TSO_RC without the leading CCC (see wf-single-cell)
ADAPTER2_MOTIF = "ATGTACTCTGCGTTGATACCACTGCTT"

# Custom enrichment PCR primers stated verbatim in ONT SST_9198_v114. These belong to the OPTIONAL
# biotin-enrichment profile, not the baseline direct-ligation model — kept here only as reference values.
ONT_FWD_PRIMER = "CAGCACTTGCCTGTCGCTCTATCTTCCTACACGACGCTCTTCCGATCT"  # /5Biosg/ (biotin) prefix on the physical oligo
ONT_REV_PRIMER = "CAGCTTTCTGTTGGTGCTGATATTGCAAGCAGTGGTATCAACGCAGAG"

# Non-sequence markers for physical library components. The ONT ligation adapter and its motor protein
# are technical parts of the library, NOT terminal nucleotide sequences; their exact bases are simply not
# represented in this model. Never embed these tokens inside a nucleotide string.
ONT_ADAPTER = "[ONT_LIGATION_ADAPTER]"      # double-stranded sequencing adapter (bases not modeled)
ONT_MOTOR = "[ONT_MOTOR_PROTEIN]"           # motor protein on the adapter — a protein, not a sequence
ONT_TECHNICAL_FLANK = "[ONT_TECHNICAL_FLANK]"

# 10x v3/v3.1 fixed lengths
CB_LEN = 16
UMI_LEN = 12
POLYT_LEN = 30

_COMPLEMENT = str.maketrans("ACGTNacgtnRYSWKMBVDHryswkmbvdh", "TGCANtgcanYRSWMKVBHDyrswmkvbhd")


def complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)


def reverse_complement(seq: str) -> str:
    return complement(seq)[::-1]


# TSO_RC is DERIVED, not independently observed.
TSO_RC = reverse_complement(TSO)  # == "CCCATGTACTCTGCGTTGATACCACTGCTT"


# ---------------------------------------------------------------- canonical molecule

@dataclass(frozen=True)
class NanoporeChem:
    """Chemistry constants for one Nanopore 10x 3' spec. Prefer :meth:`from_spec` so the simulator
    stays spec-driven; the hard-coded module constants are the fallback / reference values."""

    r1_handle: str = R1_HANDLE
    tso: str = TSO
    cb_len: int = CB_LEN
    umi_len: int = UMI_LEN
    polyt_len: int = POLYT_LEN

    @property
    def tso_rc(self) -> str:
        return reverse_complement(self.tso)

    @classmethod
    def from_spec(cls, spec) -> "NanoporeChem":
        """Pull the handle/TSO/lengths from a loaded ``Spec`` (falls back to module constants)."""
        get = spec.data.get if hasattr(spec, "data") else spec.get

        def _oligo_seq(*fragments: str) -> str | None:
            for o in get("oligos", []):
                name = (o.get("name") or "") + " " + (o.get("oligo_id") or "")
                if all(f in name.lower() for f in fragments) and o.get("sequence"):
                    return "".join(c for c in o["sequence"] if c in "ACGTN")
            return None

        pp = get("platform_params", {}) or {}
        return cls(
            r1_handle=_oligo_seq("truseq", "read 1") or _oligo_seq("read", "1", "primer") or R1_HANDLE,
            tso=_oligo_seq("template", "switch") or _oligo_seq("tso") or TSO,
            cb_len=int(pp.get("cell_barcode_len", CB_LEN)),
            umi_len=int(pp.get("umi_len", UMI_LEN)),
            polyt_len=int(pp.get("polyt_len", POLYT_LEN)),
        )

    def canonical_molecule(self, cb: str, umi: str, cdna: str, *, v: str = "G", n: str = "A") -> str:
        """Adapter1-first amplified-cDNA strand:
        R1_HANDLE + CB + UMI + polyT + V + N + cDNA + TSO_RC.  (v ∈ ACG, n ∈ ACGT)"""
        return self.r1_handle + cb + umi + ("T" * self.polyt_len) + v + n + cdna + self.tso_rc

    def canonical_segments(self, cb: str, umi: str, cdna: str, *, v: str = "G", n: str = "A"):
        """Ordered (name, sequence) segments of the adapter1-first strand — used for span labels."""
        return [
            ("r1_handle", self.r1_handle),
            ("cell_barcode", cb),
            ("umi", umi),
            ("polyt", "T" * self.polyt_len),
            ("vn", v + n),
            ("cdna", cdna),
            ("tso_rc", self.tso_rc),
        ]


DEFAULT_CHEM = NanoporeChem()
