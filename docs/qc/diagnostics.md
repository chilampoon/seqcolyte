# Seqcolyte diagnostic catalog

> Generated from `qc/catalog/diagnostic_catalog.yaml` by `python -m qc.catalog render`. Do not edit by hand.

Catalog version: `0.1.0`

## Conceptual model

```
metric -> signal -> issue -> root cause -> diagnostic test -> impact -> recovery action
```

A **metric** is a measured value. A **signal** is an abnormal pattern in one or more metrics. An **issue** is the user-facing problem. A **root cause** is a candidate mechanism. A **diagnostic test** is a deterministic analysis that supports or rejects a cause. A **recovery action** classifies how recoverable the outcome is. The LLM may later rank/explain candidate causes, but never computes, changes, or fabricates deterministic metrics.

## Issue families

### Low called-cell recovery  (`issue.low_cell_recovery`)

Far fewer cells were called than the declared target. Many mechanisms can cause this, from barcode-processing errors to insufficient input; the target must be a compatible target type before comparing.

- **Outcome domains:** cell_analysis
- **Platforms:** illumina, nanopore
- **Workflow stages:** sample_prep, library_prep, read_processing, cell_calling
- **Supporting signals:** signal.called_cells_below_target, signal.barcode_rank_no_knee, signal.low_reads_in_cells, signal.low_whitelist_match
- **Candidate root causes:** cause.barcode_boundary_shift, cause.read_configuration_mismatch, cause.wrong_chemistry_or_whitelist, cause.overly_strict_cell_calling, cause.insufficient_viable_cell_input, cause.poor_partition_capture_or_rt, cause.low_cdna_or_library_yield
- **Confirmatory tests:** test.barcode_offset_scan, test.alternative_whitelist_scan, test.read_configuration_audit, test.cell_calling_sensitivity, test.counterfactual_barcode_reextraction
- **Recovery classes:** computationally_recoverable, partially_recoverable, requires_experiment_rerun
- **Cannot explain:** It does not by itself establish cross-sample contamination or expression-fidelity bias; those require their own evidence. A low cell count with a healthy whitelist rate points upstream (input/capture/calling), not to barcode processing.

### Low informative-read yield  (`issue.low_informative_read_yield`)

A large share of sequencing was spent on reads that carry little usable single-cell information (adapter-only, short-insert, TSO-proximal, or tail-artifact reads).

- **Outcome domains:** library_structure, sequencing_run
- **Platforms:** illumina, nanopore
- **Workflow stages:** library_prep, sequencing, read_processing
- **Supporting signals:** signal.elevated_adapter_only, signal.short_insert_elevated, signal.tso_at_read_start, signal.polyg_tail_elevated, signal.internal_adapter_elevated, signal.low_full_length_proxy
- **Candidate root causes:** cause.adapter_dimer_or_short_insert, cause.short_or_empty_cdna_products, cause.read_past_end_or_signal_decay, cause.long_read_tso_concatemer_or_fusion, cause.low_cdna_or_library_yield
- **Confirmatory tests:** test.adapter_configuration_classification, test.internal_tso_scan
- **Recovery classes:** recoverable_by_additional_sequencing, partially_recoverable, requires_library_rebuild
- **Cannot explain:** It does not directly establish a specific called-cell target collapse; relate it to cell recovery only via reads-in-cells depth. A physical library dimer percentage is not the same as the sequenced-read percentage.

### Barcode / UMI recovery failure  (`issue.barcode_umi_recovery_failure`)

Reads cannot be assigned to valid barcodes/UMIs at the expected rate, starving every downstream per-cell metric.

- **Outcome domains:** read_processing, cell_analysis
- **Platforms:** illumina, nanopore
- **Workflow stages:** read_processing
- **Supporting signals:** signal.low_whitelist_match, signal.low_barcode_umi_extractable, signal.called_cells_below_target
- **Candidate root causes:** cause.barcode_boundary_shift, cause.wrong_chemistry_or_whitelist, cause.read_configuration_mismatch
- **Confirmatory tests:** test.barcode_offset_scan, test.alternative_whitelist_scan, test.read_configuration_audit, test.r1_r2_swap_test
- **Recovery classes:** computationally_recoverable, partially_recoverable
- **Cannot explain:** A whitelist/extraction failure does not imply the wet-lab library is bad; it is usually a read-processing/configuration problem and is often computationally recoverable.

### Abnormal library structure  (`issue.abnormal_library_structure`)

Sequenced molecules deviate from the expected architecture (short/empty inserts, TSO-proximal reads, adapter-only reads, or long-read internal motifs).

- **Outcome domains:** library_structure
- **Platforms:** illumina, nanopore
- **Workflow stages:** library_prep, read_processing
- **Supporting signals:** signal.tso_at_read_start, signal.internal_adapter_elevated, signal.short_insert_elevated, signal.elevated_adapter_only, signal.low_full_length_proxy
- **Candidate root causes:** cause.short_or_empty_cdna_products, cause.adapter_dimer_or_short_insert, cause.long_read_tso_concatemer_or_fusion
- **Confirmatory tests:** test.adapter_configuration_classification, test.internal_tso_scan
- **Recovery classes:** partially_recoverable, requires_library_rebuild
- **Cannot explain:** Structural abnormality alone does not quantify lost cells or prove cross-sample mixing; a short-read TSO read-through and a long-read internal TSO motif are different events and must not be conflated.

## Root causes

| cause_id | title | stage | cell-recovery | recoverability | produces |
| --- | --- | --- | --- | --- | --- |
| cause.barcode_boundary_shift | Barcode boundary shift | read_processing | direct | computationally_recoverable | issue.barcode_umi_recovery_failure, issue.low_cell_recovery |
| cause.read_configuration_mismatch | Read-configuration mismatch | sequencing | direct | partially_recoverable | issue.barcode_umi_recovery_failure, issue.low_cell_recovery |
| cause.wrong_chemistry_or_whitelist | Wrong chemistry or barcode whitelist | read_processing | direct | computationally_recoverable | issue.barcode_umi_recovery_failure, issue.low_cell_recovery |
| cause.adapter_dimer_or_short_insert | Adapter dimers or short inserts | library_prep | indirect | recoverable_by_additional_sequencing | issue.low_informative_read_yield, issue.abnormal_library_structure |
| cause.short_or_empty_cdna_products | Short or empty cDNA products | library_prep | indirect | partially_recoverable | issue.abnormal_library_structure, issue.low_informative_read_yield |
| cause.insufficient_viable_cell_input | Insufficient viable-cell input | sample_prep | direct | requires_experiment_rerun | issue.low_cell_recovery |
| cause.poor_partition_capture_or_rt | Poor partition capture or RT | library_prep | direct | requires_experiment_rerun | issue.low_cell_recovery, issue.low_informative_read_yield |
| cause.low_cdna_or_library_yield | Low cDNA or library yield | library_prep | indirect | partially_recoverable | issue.low_cell_recovery, issue.low_informative_read_yield |
| cause.overly_strict_cell_calling | Overly strict cell calling | cell_calling | direct | computationally_recoverable | issue.low_cell_recovery |
| cause.read_past_end_or_signal_decay | Read-past-end or signal decay | sequencing | unlikely | computationally_recoverable | issue.low_informative_read_yield |
| cause.long_read_tso_concatemer_or_fusion | Long-read TSO concatemer or fused read | library_prep | indirect | partially_recoverable | issue.abnormal_library_structure, issue.low_informative_read_yield |

## Root-cause matrix (issue x candidate cause)

| issue \ cause | barcode_boundary_shift | read_configuration_mismatch | wrong_chemistry_or_whitelist | adapter_dimer_or_short_insert | short_or_empty_cdna_products | insufficient_viable_cell_input | poor_partition_capture_or_rt | low_cdna_or_library_yield | overly_strict_cell_calling | read_past_end_or_signal_decay | long_read_tso_concatemer_or_fusion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| issue.low_cell_recovery | x | x | x |  |  | x | x | x | x |  |  |
| issue.low_informative_read_yield |  |  |  | x | x |  |  | x |  | x | x |
| issue.barcode_umi_recovery_failure | x | x | x |  |  |  |  |  |  |  |  |
| issue.abnormal_library_structure |  |  |  | x | x |  |  |  |  |  | x |

## Diagnostic tests

| test_id | title | status | supports |
| --- | --- | --- | --- |
| test.barcode_offset_scan | Barcode offset scan | planned | cause.barcode_boundary_shift |
| test.alternative_whitelist_scan | Alternative-whitelist scan | planned | cause.wrong_chemistry_or_whitelist, cause.barcode_boundary_shift |
| test.read_configuration_audit | Read-configuration audit | planned | cause.read_configuration_mismatch, cause.wrong_chemistry_or_whitelist |
| test.r1_r2_swap_test | R1/R2 swap test | planned | cause.read_configuration_mismatch |
| test.adapter_configuration_classification | Adapter-configuration classification | implemented | cause.adapter_dimer_or_short_insert, cause.short_or_empty_cdna_products, cause.read_past_end_or_signal_decay |
| test.internal_tso_scan | Internal TSO scan (long-read) | implemented | cause.long_read_tso_concatemer_or_fusion |
| test.cell_calling_sensitivity | Cell-calling sensitivity analysis | planned | cause.overly_strict_cell_calling, cause.insufficient_viable_cell_input, cause.poor_partition_capture_or_rt |
| test.counterfactual_barcode_reextraction | Counterfactual barcode re-extraction | planned | cause.barcode_boundary_shift, cause.read_configuration_mismatch |

## Recovery classes

| recovery_class | label | description |
| --- | --- | --- |
| computationally_recoverable | Computationally recoverable | The signal can be corrected in silico from existing data (e.g. re-extract barcodes at a corrected offset, re-run cell calling) without new sequencing or a new library. |
| partially_recoverable | Partially recoverable | Some information can be rescued computationally, but a fraction is unrecoverable from the current data. |
| recoverable_by_additional_sequencing | Recoverable by additional sequencing | The existing library is sound but under-sequenced for the goal; more sequencing recovers the signal. |
| requires_library_rebuild | Requires library rebuild | The molecular library itself is compromised; recovery needs a new library from retained material. |
| requires_experiment_rerun | Requires experiment rerun | The defect originates upstream of library prep (e.g. cell input); recovery needs a new experiment. |
| unknown | Unknown / insufficient evidence | Available evidence does not determine recoverability. |

## Evidence-scope coverage (metrics by required scope)

| scope | metrics | metric ids |
| --- | --- | --- |
| alignment_assignment | 8 | mapping.genome_fraction, mapping.primary_fraction, mapping.unmapped_fraction, mapping.supplementary_fraction, assignment.gene_fraction, assignment.transcript_fraction, assignment.unique_genes, assignment.unique_isoforms |
| cell_analysis | 8 | cell.target_count, cell.called_count, cell.target_attainment, cell.reads_in_cells_fraction, cell.mean_reads, cell.median_genes, cell.median_umis, cell.barcode_rank_separation |
| complexity_expression | 2 | complexity.sequencing_saturation, complexity.duplicate_fraction |
| library_structure | 7 | library.full_length_proxy_fraction, library.adapter_only_fraction, library.short_insert_fraction, library.tso_at_rna_read_start_fraction, library.internal_adapter_fraction, library.polyg_tail_fraction, library.unclassified_fraction |
| read_processing | 6 | barcode.extractable_fraction, barcode.whitelist_fraction, barcode.valid_fraction, barcode.corrected_fraction, umi.extractable_fraction, umi.valid_fraction |
| sequencing_run | 3 | run.reads_total, run.reads_pass, run.reads_pass_fraction |

## References

| reference_id | title | source | evidence | url |
| --- | --- | --- | --- | --- |
| ref.tenx_3p_v3_userguide | Chromium Single Cell 3' Reagent Kits v3 / v3.1 User Guide | 10x Genomics | strong |  |
| ref.cellranger_web_summary | Cell Ranger web summary metric definitions | 10x Genomics Cell Ranger documentation | strong |  |
| ref.wf_single_cell_docs | EPI2ME wf-single-cell workflow documentation | Oxford Nanopore Technologies / EPI2ME Labs | strong | https://epi2me.nanoporetech.com/epi2me-docs/workflows/wf-single-cell/ |
| ref.lebrigand_2020 | High throughput error corrected Nanopore single cell transcriptome sequencing (ScNaUmi-seq / Sicelore) | Lebrigand et al., Nature Communications 2020 | strong | https://www.nature.com/articles/s41467-020-17800-6 |
