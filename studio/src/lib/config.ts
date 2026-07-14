import path from "node:path";

/**
 * Central config: where the seqcolyte repo lives, where the project store lives,
 * and how to invoke the pipeline + claude CLIs. All overridable via env so the
 * app can run against a repo checkout in a non-default location.
 *
 * `next dev` runs with cwd = the studio/ project dir, so the repo is its parent.
 */
export const REPO_ROOT =
  process.env.SEQCOLYTE_REPO ?? path.resolve(process.cwd(), "..");

/** Filesystem project store. Kept OUTSIDE the python package tree. */
export const STORE_ROOT =
  process.env.SEQCOLYTE_STUDIO_DATA ?? path.join(process.cwd(), "projects");

export const PYTHON = process.env.SEQCOLYTE_PYTHON ?? "python";
export const CLAUDE_BIN = process.env.SEQCOLYTE_CLAUDE ?? "claude";
export const SEQCOLYTE_CLI = process.env.SEQCOLYTE_CLI ?? "seqcolyte";
export const DEFAULT_MODEL = process.env.SEQCOLYTE_MODEL ?? "claude-opus-4-8";

export const QC_CORE_BIN =
  process.env.SEQCOLYTE_QC_BIN ??
  path.join(REPO_ROOT, "qc", "core", "target", "release", "qc-core");

/** Repo-global shared assets (fetched once via `seqcolyte fetch`, shared by all projects). */
export const assets = {
  referenceSpec: path.join(REPO_ROOT, "spec", "10x_3p_v3.json"),
  referenceSpecPdf: path.join(REPO_ROOT, "spec", "10x_3p_v3.pdf.json"),
  whitelist: path.join(REPO_ROOT, "whitelists", "3M-february-2018.txt.gz"),
  control: {
    r1: path.join(REPO_ROOT, "data", "raw", "pbmc_1k_v3_sub_R1.fastq.gz"),
    r2: path.join(REPO_ROOT, "data", "raw", "pbmc_1k_v3_sub_R2.fastq.gz"),
  },
  /** The committed adapter-dimer simulation (labeled failures) — the demo dataset. */
  sim: {
    r1: path.join(REPO_ROOT, "data", "sim", "adapter_dimer_f30", "R1.fastq.gz"),
    r2: path.join(REPO_ROOT, "data", "sim", "adapter_dimer_f30", "R2.fastq.gz"),
    labels: path.join(REPO_ROOT, "sim", "labels", "adapter_dimer_f30.tsv"),
  },
} as const;

export const DEFAULT_ASSAY = "10x Chromium Single Cell 3' Gene Expression";
export const DEFAULT_SPEC_ID = "10x_3p_v3";

/**
 * A brand-new project has no identified library structure yet. It stays labelled
 * "new" until a protocol is extracted; only then does it adopt a known
 * technology's id (or fall back to "new" for a custom structure).
 */
export const NEW_ASSAY = "New library — describe or upload a protocol";
export const NEW_SPEC_ID = "new";
