# Canonical metric glossary

> Generated from `qc/catalog/diagnostic_catalog.yaml` by `python -m qc.catalog render`. Do not edit by hand.

| metric_id | label | domain | unit | direction | scoreability | denominator | source aliases |
| --- | --- | --- | --- | --- | --- | --- | --- |
| run.reads_total | Total reads | sequencing_run | count | descriptive | descriptive |  | Input reads; Number of Reads |
| run.reads_pass | Pass reads | sequencing_run | count | higher_is_better | profile_dependent |  | Pass reads |
| run.reads_pass_fraction | Pass-read fraction | sequencing_run | fraction | higher_is_better | profile_dependent | reads passing quality / total reads produced |  |
| barcode.extractable_fraction | Barcode-extractable fraction | read_processing | fraction | higher_is_better | scoreable | reads with an extractable barcode / reads examined |  |
| barcode.whitelist_fraction | Barcode whitelist-match fraction | read_processing | fraction | higher_is_better | scoreable | reads with exact whitelist match / reads with an extracted barcode |  |
| barcode.valid_fraction | Valid-barcode fraction | read_processing | fraction | higher_is_better | scoreable | reads with a valid (corrected) barcode / reads examined | Valid Barcodes; Valid barcode |
| barcode.corrected_fraction | Barcode-corrected fraction | read_processing | fraction | descriptive | descriptive |  |  |
| umi.extractable_fraction | UMI-extractable fraction | read_processing | fraction | higher_is_better | scoreable |  |  |
| umi.valid_fraction | Valid-UMI fraction | read_processing | fraction | higher_is_better | scoreable |  |  |
| library.full_length_proxy_fraction | Full-length-proxy fraction | library_structure | fraction | higher_is_better | scoreable |  | % full length reads; Full length |
| library.adapter_only_fraction | Adapter-only fraction | library_structure | fraction | lower_is_better | scoreable |  |  |
| library.short_insert_fraction | Short-insert fraction | library_structure | fraction | lower_is_better | scoreable |  |  |
| library.tso_at_rna_read_start_fraction | TSO-at-RNA-read-start fraction (short-read) | library_structure | fraction | lower_is_better | scoreable |  |  |
| library.internal_adapter_fraction | Internal-adapter fraction (long-read) | library_structure | fraction | lower_is_better | scoreable |  |  |
| library.polyg_tail_fraction | Poly-G tail fraction | library_structure | fraction | lower_is_better | scoreable |  |  |
| library.unclassified_fraction | Unclassified-read fraction | library_structure | fraction | lower_is_better | scoreable |  |  |
| mapping.genome_fraction | Genome-mapped fraction | alignment_assignment | fraction | higher_is_better | scoreable |  | Reads Mapped to Genome; Mapped |
| mapping.primary_fraction | Primary-alignment fraction | alignment_assignment | fraction | higher_is_better | scoreable |  |  |
| mapping.unmapped_fraction | Unmapped fraction | alignment_assignment | fraction | lower_is_better | scoreable |  | Unmapped |
| mapping.supplementary_fraction | Supplementary-alignment fraction | alignment_assignment | fraction | descriptive | descriptive |  | Supplementary |
| assignment.gene_fraction | Gene-assigned fraction | alignment_assignment | fraction | higher_is_better | scoreable |  | Gene assigned |
| assignment.transcript_fraction | Transcript-assigned fraction | alignment_assignment | fraction | higher_is_better | scoreable |  | Transcript assigned |
| assignment.unique_genes | Unique genes detected | alignment_assignment | count | higher_is_better | descriptive |  | Unique genes |
| assignment.unique_isoforms | Unique isoforms detected | alignment_assignment | count | higher_is_better | descriptive |  | Unique isoforms |
| cell.target_count | Target cell count | cell_analysis | count | descriptive | target_dependent |  |  |
| cell.called_count | Called cell count | cell_analysis | count | descriptive | target_dependent |  | Estimated Number of Cells; Estimated cells |
| cell.target_attainment | Target attainment | cell_analysis | ratio | higher_is_better | target_dependent | cell.called_count / cell.target_count |  |
| cell.reads_in_cells_fraction | Fraction reads in cells | cell_analysis | fraction | higher_is_better | scoreable |  | Fraction Reads in Cells |
| cell.mean_reads | Mean reads per cell | cell_analysis | count | descriptive | profile_dependent |  | Mean Reads per Cell; Reads per cell (mean) |
| cell.median_genes | Median genes per cell | cell_analysis | count | higher_is_better | profile_dependent |  | Median Genes per Cell; Genes per cell (median) |
| cell.median_umis | Median UMIs per cell | cell_analysis | count | higher_is_better | profile_dependent |  | Median UMI Counts per Cell; UMIs per cell (median) |
| cell.barcode_rank_separation | Barcode-rank knee separation | cell_analysis | dimensionless | descriptive | descriptive |  |  |
| complexity.sequencing_saturation | Sequencing saturation | complexity_expression | fraction | descriptive | profile_dependent |  | Sequencing Saturation |
| complexity.duplicate_fraction | Duplicate fraction | complexity_expression | fraction | descriptive | profile_dependent |  |  |
