/** Shared domain types for the studio project store + QC artifacts. */

export interface Conclusion {
  id: string;
  createdAt: string;
  title: string;
  body: string;
  runId?: string | null;
  source: "manual" | "diagnosis";
}

export type StepName = "extract" | "simulate" | "qc";
export type StepStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "canceled";
export type RunStatus = StepStatus;
export type Verdict = "pass" | "warn" | "fail";

export interface StepRecord {
  name: StepName;
  status: StepStatus;
  pid?: number;
  exitCode?: number | null;
  startedAt?: string;
  finishedAt?: string;
  /** log path relative to the run dir, e.g. "logs/qc.log" */
  log: string;
  costUsd?: number | null;
  durationMs?: number | null;
  error?: string;
}

export interface RunOptions {
  useLlm: boolean;
  maxReads?: number | null;
  withLabels?: boolean;
  withWhitelist?: boolean;
  failureMode?: string;
  seed?: number;
  fastqSource?: "control" | "sim" | "upload";
  /** modality: "nanopore" runs use the long-read QC path */
  platform?: string;
}

export interface RunRecord {
  schemaVersion: "studio.run.v1";
  id: string;
  projectId: string;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  pipeline: StepName[];
  options: RunOptions;
  /** Exact provenance: which spec/reads/whitelist/labels produced this run's report. */
  inputsSnapshot: {
    specPath: string;
    r1: string;
    r2: string;
    whitelist?: string | null;
    labels?: string | null;
  };
  steps: Partial<Record<StepName, StepRecord>>;
  overallStatus: RunStatus;
  /** QC verdict, populated once the qc step's report is available. */
  overall?: Verdict | null;
}

/** Onboarding → analysis lifecycle. Drives the assistant's gating prompts. */
export type ProjectPhase =
  | "awaiting_inputs"
  | "extracting"
  | "awaiting_spec_review"
  | "spec_confirmed"
  | "analyzing"
  | "complete";

export interface ProjectManifest {
  schemaVersion: "studio.project.v1";
  id: string;
  name: string;
  assay: string;
  specId: string;
  createdAt: string;
  updatedAt: string;
  /** relative-to-project path of the active spec (extract output or reference copy) */
  activeSpecPath: string | null;
  /** Current lifecycle phase (defaults to awaiting_inputs when absent). */
  phase?: ProjectPhase;
  /** The user reviewed and confirmed the extracted spec. */
  specConfirmed?: boolean;
  /** Featured demo project (surfaced in the landing "Demos" section). */
  demo?: boolean;
  /** One-line description shown on the demo card (falls back to a verdict-based default). */
  demoBlurb?: string;
  inputs: {
    protocolDoc: string | null;
    notesPath: string | null;
    /** project-relative paths of uploaded design/oligo tables (csv/tsv/xlsx) */
    tables?: string[];
    /** which reads back the analysis: user-uploaded FASTQ vs. the built-in demo dataset */
    reads?: "uploaded" | "demo" | null;
    fastq: {
      source: "control" | "sim" | "upload";
      r1: string | null;
      r2: string | null;
    };
  };
  latestRunId: string | null;
  runIds: string[];
}

// ---- QC report (tolerant; the report is partial by design) ----

export interface QcEvidence {
  spec_ref: string;
  note: string;
}
export interface QcFinding {
  check_id: string;
  title: string;
  verdict: Verdict;
  value: number;
  unit: string;
  threshold: string;
  affected_fraction: number | null;
  severity: number;
  evidence: QcEvidence[];
  detail: string;
}
export interface QcRanked {
  check_id: string;
  severity: "none" | "low" | "medium" | "high";
  why: string;
}
export interface QcPlan {
  ranked?: QcRanked[];
  root_cause?: string;
  diagnosis?: string;
  method?: "llm" | "deterministic";
  llm_error?: string;
}
export interface QcEval {
  n: number;
  predicted_affected?: number;
  true_affected?: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  confusion: { tp: number; fp: number; fn: number; tn: number };
}
export interface QcLenStat {
  min: number;
  max: number;
  modal: number;
}
export interface QcReport {
  qc_version?: string;
  spec_id?: string;
  assay?: string;
  platform?: string;
  profile?: { n_pairs: number; r1_len: QcLenStat; r2_len: QcLenStat };
  findings?: QcFinding[];
  plan?: QcPlan;
  overall?: Verdict;
  eval?: QcEval | null;
}

// ---- Spec (expected read/library structure) ----

export interface SpecOligoComponent {
  name: string;
  sequence: string;
  role?: string;
}
export interface SpecOligo {
  oligo_id: string;
  name?: string;
  role?: string;
  kind?: string;
  sequence?: string;
  /** named sub-parts (e.g. TruSeq Read 1, 10x Barcode, UMI, poly(dT)) with their sequences */
  components?: SpecOligoComponent[];
  notes?: string;
}
export interface SpecSegment {
  name: string;
  type?: string;
  order?: number;
  length?: number;
  length_range?: [number, number];
  whitelist_ref?: string;
  notes?: string;
}
export interface SpecReadthroughElement {
  name: string;
  type?: string;
  constant_ref?: string;
  notes?: string;
}
export interface SpecRead {
  read: string;
  primer?: string;
  template?: string;
  cycles?: number;
  segments?: SpecSegment[];
  readthrough_chain?: SpecReadthroughElement[];
}
export interface SpecLibStep {
  step: number;
  title: string;
  note?: string | null;
  /** monospace ASCII diagram of the molecular product after this step (scg_lib_structs style) */
  product?: string | null;
}
export interface SpecSequencingRead {
  read: string;
  primer?: string | null;
  template?: string | null;
  cycles?: number | null;
  note?: string | null;
  /** ASCII diagram of the sequencing primer annealing to the final library + read direction */
  diagram?: string | null;
}
export interface SpecWhitelist {
  name?: string;
  count?: number;
  length?: number;
  path?: string;
}
export interface SpecDoc {
  spec_id?: string;
  assay?: string;
  platform?: string;
  chemistry_version?: string;
  platform_params?: Record<string, unknown>;
  oligos?: SpecOligo[];
  read_structure?: { reads?: SpecRead[] };
  library_generation?: SpecLibStep[];
  library_sequencing?: SpecSequencingRead[];
  final_library?: {
    source_label?: string;
    annotated_library_sequence?: string;
    library_sequence?: string;
    /** human-readable "<sequence-or-token> = <label>" breakdown, in 5'→3' order */
    annotation_lines?: string[];
  };
  whitelists?: Record<string, SpecWhitelist>;
}
