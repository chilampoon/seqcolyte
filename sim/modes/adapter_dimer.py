"""Adapter-dimer / short-insert read-through — the Illumina 10x 3' failure.

Both sub-types lead with the TSO (the hallmark), built from the spec's constants:

  readthrough (insert 1-30):  TSO + insert + poly(A) + revcomp(UMI) + revcomp(CB)
                              + revcomp(R1 primer) + revcomp(P5), fit to the read length.
                              At ~90 nt this fits by truncation -> adapter read-through
                              (the AGATCGGAAGAGC stem) and reverse-complemented barcode are visible.

  pure_dimer (insert 0):      TSO + short poly(A) + poly-G no-signal tail to the read length —
                              the classic empty TSO<->poly-dT product on two-color instruments.

revcomp(CB)/revcomp(UMI) use *this pair's* barcode/UMI (from R1), never random. Synthesized
bases get a spuriously-high quality so a naive quality filter cannot flag them.
"""

from __future__ import annotations

from seqcolyte.dna import homopolymer, revcomp
from sim.base import FailureMode, R2Result, ReadCtx, draw_uniform_int, fit_to_length, synth_quality
from sim.registry import register

_TSO = "oligo_template_switching_oligo_tso"
_R1_READINTO = "oligo_r1_readinto_adapter"
_P5_RC = "oligo_p5_rc"


@register
class AdapterDimer(FailureMode):
    name = "adapter_dimer"
    platform = "illumina"

    def build_r2(self, ctx: ReadCtx) -> R2Result:
        spec, rng, params = ctx.spec, ctx.rng, ctx.params
        qcfg = params.get("quality", {})
        phred = int(qcfg.get("phred", 37))
        pad_base = spec.platform_params.get("dark_base") or "G"
        polya_base = spec.platform_params.get("polyA_base") or "A"

        tso = spec.oligo_sequence(_TSO)
        polya_len = draw_uniform_int(rng, params.get("polyA_len", {"min": 5, "max": 20}))

        parts: list[tuple[str, str]] = [(tso, synth_quality(len(tso), phred))]

        if ctx.subtype == "pure_dimer":
            insert_len = 0
            parts.append((homopolymer(polya_base, polya_len), synth_quality(polya_len, phred)))
            recipe = f"TSO|polyA({polya_len})"
        else:  # readthrough
            insert_len = draw_uniform_int(rng, params.get("readthrough_insert_len", {"min": 0, "max": 30}))
            insert = ctx.r2.sequence[:insert_len]
            insert_qual = (
                ctx.r2.quality[:insert_len] if qcfg.get("overlay_insert", True)
                else synth_quality(insert_len, phred)
            )
            r1_readinto = spec.oligo_sequence(_R1_READINTO)
            p5_rc = spec.oligo_sequence(_P5_RC)
            parts += [
                (insert, insert_qual),
                (homopolymer(polya_base, polya_len), synth_quality(polya_len, phred)),
                (revcomp(ctx.umi), synth_quality(len(ctx.umi), phred)),
                (revcomp(ctx.cb), synth_quality(len(ctx.cb), phred)),
                (r1_readinto, synth_quality(len(r1_readinto), phred)),
                (p5_rc, synth_quality(len(p5_rc), phred)),
            ]
            recipe = f"TSO|insert({insert_len})|polyA({polya_len})|rc_UMI|rc_CB|rc_R1primer|rc_P5"

        seq = "".join(s for s, _ in parts)
        qual = "".join(q for _, q in parts)
        seq, qual, pad_len, truncated = fit_to_length(seq, qual, ctx.r2_len, pad_base, phred)
        construct = f"{recipe}|padG({pad_len})" if pad_len else (f"{recipe}|trunc" if truncated else recipe)

        return R2Result(
            sequence=seq,
            quality=qual,
            construct=construct,
            fields={"insert_len": insert_len, "polyA_len": polya_len, "pad_len": pad_len, "truncated": truncated},
        )
