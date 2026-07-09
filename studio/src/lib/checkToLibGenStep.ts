/**
 * QC checks reference read-structure / oligo / whitelist locations, never a
 * numbered `library_generation` step. This curated map surfaces the implicated
 * wet-lab build step for each check (data-driven so new checks are easy to add).
 * Step numbers refer to spec.library_generation[].step for the 10x 3' v3 assay.
 */
export const CHECK_TO_LIBGEN_STEP: Record<string, { step: number; label: string }> = {
  tso_at_r2_start: { step: 3, label: "Adding TSO for second-strand synthesis" },
  r2_adapter_readthrough: { step: 6, label: "Truseq adapter ligation" },
  r2_polyg_tail: { step: 8, label: "Final library / short-insert artifact" },
  whitelist_hit_rate: { step: 1, label: "mRNA capture & barcoding (Beads-oligo-dT)" },
  r1_length: { step: 1, label: "Barcode + UMI read structure" },
};

export function libGenStepForCheck(checkId: string): { step: number; label: string } | null {
  return CHECK_TO_LIBGEN_STEP[checkId] ?? null;
}
