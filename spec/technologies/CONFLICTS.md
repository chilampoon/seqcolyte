# Cross-check conflicts — paper-derived extraction vs curated scg_html

The wiki spec is extracted from the papers/protocols (papers-first); this compares it against the curated scg_html ground truth. A flag means the paper disagrees with the human curation — which may itself be the error. Recall is sequence-EXACT, so version drift and standard adapters the paper omits legitimately lower it.

73 cross-checked · **3 barcode/UMI length disagreements (substantive)** · 21 low sequence-overlap (recall < 0.5).

## Barcode/UMI length disagreements (substantive — review these first)

| technology | recall | length disagreement |
|---|---|---|
| hydrop_rna | 0.75 | **UMI**: paper [8] vs curation [8, 10] |
| mars_seq_v2 | 0.7 | **CELL_BARCODE**: paper [7] vs curation [7, 9] |
| sci_rna_seq3 | 0.4 | **UMI**: paper [8] vs curation [8, 10] |

## Low sequence overlap (recall < 0.5 — usually version drift / unprinted adapters)

| technology | recall | oligos matched | top missed oligos |
|---|---|---|---|
| flash_seq | 0.118 | 2/17 | FLASH-seq_TSO, Fwd_PCR_primer, Illumina P5 adapter, Illumina P7 adapter, Nextera Index 1 sequencing primer (i7)… |
| ddseq_single_cell_3_rna_seq_kit | 0.125 | 2/16 | Bead-TruSeq Read 1-UMI-CBC-DO-A, Bead-TruSeq Read 1-UMI-CBC-DO-B, Bead-TruSeq Read 1-UMI-CBC-poly(T), ddSEQ cDNA/DO Index Plate forward primer, ddSEQ Single-Cell 3' RNA-Seq cDNA Index Plate reverse… |
| vasa_drop | 0.182 | 2/11 | Beads-oligo-dT19V, Illumina Nextera Read 1 primer, Illumina Nextera Read 2 primer, Library PCR P7 primer, Ligation adapter… |
| smart_seq3 | 0.235 | 4/17 | FLASH-seq_TSO, Illumina Nextera Read 1 primer, Illumina Nextera Read 2 primer, Illumina P5 adapter, Illumina P7 adapter… |
| pip_seq_v4 | 0.25 | 3/12 | Barcoded beads-oligo (T2/20/100 PIPs, FB0003913/FB0003914/FB0003915), Illumina Nextera Read 2 primer, Illumina P5 adapter, Illumina P7 adapter, Illumina TruSeq Read 1 primer… |
| scdamid | 0.25 | 3/12 | AdRb, AdRt, Illumina adaptor top, Illumina Multiplexing PCR Primer, Illumina P5 adapter… |
| plate_scatac_seq | 0.273 | 3/11 | Illumina P5 adapter, Illumina P7 adapter, Nextera Index 2 sequencing primer (i5), Nextera N7xx primer entry point (s7), Nextera N/S5xx primer entry point (s5)… |
| itchip_seq | 0.3 | 3/10 | Barcoded Tn5 sequence s5, Barcoded Tn5 sequence s7, Illumina TruSeq Read 1 primer, Illumina TruSeq Read 2 primer, Indexed P7 primer… |
| sci_rna_seq | 0.3 | 3/10 | Barcoded RT primer, Nextera Index 1 sequencing primer (i7), Nextera N7 index primer, Nextera N/S5xx primer entry point (s5), Nextera Tn5 binding site (19-bp Mosaic End (ME))… |
| s3_atac | 0.333 | 3/9 | A14_ME_LNA (Nextera_R1_A14 + U-ME), Nextera Index 2 sequencing primer (i5), PCR_i5_primer, TruSeq i7 PCR primer, SBS12_18_UME_sci indexed Tn5 adapter… |
| scths_seq | 0.333 | 4/12 | Illumina Nextera Read 1 primer, Illumina Nextera Read 2 primer, Nextera Index 1 sequencing primer (i7), Nextera (XT) N7xx Index primer, Random hexamer for reverse transcription… |
| smart_seq3xpress | 0.353 | 6/17 | FLASH-seq_TSO, Illumina P5 adapter, Illumina P7 adapter, Nextera Index 1 sequencing primer (i7), Nextera N7xx primer entry point (s7)… |
| strt_seq_c1 | 0.375 | 3/8 | Barcoded C1-Tn5 forward (including 19-bp Mosaic End (ME)), Barcoded Tn5 reverse oligo, C1-P1-RNA-TSO, Solexa P1 adapter, Solexa P2 adapter |
| 10x_chromium_5_immune_profiling_feature_barcoding_v3 | 0.389 | 7/18 | Barcoded oligo (FeatureBarcode, FB) on antibody against surface protein, cDNA reverse primer, Dual Index Kit forward primer, Dual Index Kit TN Set A (PN-3000510) (Reverse primer), Dual Index Kit TT Set A (PN-3000431) (Reverse primer)… |
| microwell_seq | 0.4 | 6/15 | A1-A96 (96 of them in 96 individual wells), B1-B96 (96 of them in 96 individual wells), C1-C96 (96 of them in 96 individual wells), Illumina Nextera Read 2 primer, Indexed-Beads-seqA… |
| issaac_seq_droplet | 0.429 | 6/14 | Nextera Index 1 sequencing primer (i7), Nextera Index 2 sequencing primer (i5), Nextera Tn5 binding site (19-bp Mosaic End (ME)), Nextera (XT) N7xx Index primer, Nextera (XT) N/S5xx Index primer… |
| smart_seq | 0.429 | 6/14 | Illumina Nextera Read 1 primer, Illumina Nextera Read 2 primer, Nextera Index 1 sequencing primer (i7), Nextera Index 2 sequencing primer (i5), Nextera N7xx primer entry point (s7)… |
| 10x_chromium_5_immune_profiling_feature_barcoding_v1_1 | 0.444 | 8/18 | Barcoded oligo (FeatureBarcode, FB) on antibody against surface protein, Dual Index Kit forward primer, Dual Index Kit TN Set A (PN-3000510) (Reverse primer), Dual Index Kit TT Set A (PN-3000431) (Reverse primer), Feature cDNA Primers 4 reverse (PN-2000277) for FB… |
| sci_atac_seq | 0.455 | 5/11 | ATAC index sequencing primer, Barcoded Tn5 sequence s5, Barcoded Tn5 sequence s7, P5 index primer, P7 index primer… |
| fipresci | 0.462 | 6/13 | Illumina P5 adapter, Illumina P7 adapter, Illumina TruSeq Read 1 primer, Illumina TruSeq Read 2 primer, S-P7-index… |
| issaac_seq_facs | 0.462 | 6/13 | Nextera Index 1 sequencing primer (i7), Nextera Index 2 sequencing primer (i5), Nextera (XT) N7xx Index primer, Nextera (XT) N/S5xx Index primer, TruSeq i5 index sequencing primer (index2)… |

## All cross-checked technologies

| technology | recall | library exact-match | flag |
|---|---|---|---|
| 10x_chromium_3_feature_barcoding | 0.875 | no | ok |
| 10x_chromium_3_gene_expression_v1 | 0.6 | no | ok |
| 10x_chromium_3_gene_expression_v2 | 0.909 | yes | ok |
| 10x_chromium_3_gene_expression_v3 | 0.818 | no | ok |
| 10x_chromium_3_gene_expression_v3_1 | 0.818 | no | ok |
| 10x_chromium_3_gene_expression_v4 | 0.636 | no | ok |
| 10x_chromium_5_gene_expression_v1_1 | 0.909 | no | ok |
| 10x_chromium_5_gene_expression_v2 | 0.727 | no | ok |
| 10x_chromium_5_gene_expression_v3 | 0.545 | no | ok |
| 10x_chromium_5_immune_profiling_feature_barcoding_v1_1 | 0.444 | no | low-overlap |
| 10x_chromium_5_immune_profiling_feature_barcoding_v2 | 0.667 | no | ok |
| 10x_chromium_5_immune_profiling_feature_barcoding_v3 | 0.389 | no | low-overlap |
| 10x_chromium_single_cell_atac_v2 | 0.818 | no | ok |
| 10x_chromium_single_cell_multiome_atac_plus_gene_expression | 0.545 | no | ok |
| bd_rhapsody_wta | 0.5 | no | ok |
| cel_seq | 0.714 | no | ok |
| cel_seq2 | 0.643 | yes | ok |
| ch_atac_seq | 0.545 | no | ok |
| crispr_sciatac | 0.875 | no | ok |
| ddseq_scatac_seq | 0.5 | no | ok |
| ddseq_single_cell_3_rna_seq_kit | 0.125 | no | low-overlap |
| dr_seq | 0.6 | no | ok |
| drop_seq | 0.667 | no | ok |
| fipresci | 0.462 | no | low-overlap |
| flash_seq | 0.118 | no | low-overlap |
| hydrop_atac | 0.889 | no | ok |
| hydrop_rna | 0.75 | no | ⚠️ length |
| indrop_v1 | 0.556 | no | ok |
| indrop_v2 | 0.8 | no | ok |
| issaac_seq_droplet | 0.429 | no | low-overlap |
| issaac_seq_facs | 0.462 | no | low-overlap |
| itchip_seq | 0.3 | no | low-overlap |
| lianti | 0.6 | no | ok |
| malbac | 1.0 | no | ok |
| mars_seq_v2 | 0.7 | no | ⚠️ length |
| microsplit | 0.556 | no | ok |
| microwell_seq | 0.4 | no | low-overlap |
| paired_seq | 0.565 | no | ok |
| petri_seq | 0.75 | no | ok |
| pi_atac_seq | 0.636 | yes | ok |
| pip_seq_v4 | 0.25 | no | low-overlap |
| plate_scatac_seq | 0.273 | no | low-overlap |
| quartz_seq | 0.833 | no | ok |
| s3_atac | 0.333 | no | low-overlap |
| scbs_seq | 0.571 | no | ok |
| scdam_and_t_seq | 0.7 | no | ok |
| scdamid | 0.25 | no | low-overlap |
| scdnase_seq | 0.75 | no | ok |
| sci_atac_seq | 0.455 | no | low-overlap |
| sci_atac_seq3 | 0.636 | no | ok |
| sci_rna_seq | 0.3 | no | low-overlap |
| sci_rna_seq3 | 0.4 | no | ⚠️ length |
| scifi_atac_seq | 0.786 | no | ok |
| scifi_rna_seq | 0.733 | no | ok |
| scrb_seq | 0.538 | no | ok |
| scrrbs | 0.714 | no | ok |
| scths_seq | 0.333 | no | low-overlap |
| seq_well_s3 | 0.667 | no | ok |
| share_seq | 0.632 | no | ok |
| smart_seq | 0.429 | no | low-overlap |
| smart_seq2 | 0.643 | no | ok |
| smart_seq3 | 0.235 | no | low-overlap |
| smart_seq3xpress | 0.353 | no | low-overlap |
| snare_seq | 0.667 | no | ok |
| spear_atac | 0.5 | no | ok |
| split_seq | 0.522 | no | ok |
| strt_seq | 0.714 | no | ok |
| strt_seq_2i | 0.545 | no | ok |
| strt_seq_c1 | 0.375 | no | low-overlap |
| tang_2009 | 1.0 | no | ok |
| txci_atac_seq | 0.692 | no | ok |
| vasa_drop | 0.182 | no | low-overlap |
| vasa_plate | 0.727 | no | ok |
