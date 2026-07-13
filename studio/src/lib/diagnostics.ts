import path from "node:path";
import { promises as fs } from "node:fs";
import { REPO_ROOT } from "./config";

/**
 * Types + reader for the diagnostic catalog. The catalog is generated from
 * `qc/catalog/diagnostic_catalog.yaml` by `python -m qc.catalog render` into
 * `spec/diagnostics/catalog.json`; the studio only reads that JSON (never the YAML).
 */

export interface DiagRelationship {
  relationship: "direct" | "indirect" | "unlikely" | "context_dependent";
  note: string;
}
export interface DiagAlias {
  label: string;
  producer?: string;
  source_scope?: string;
  denominator?: string;
  note?: string;
}
export interface DiagMetric {
  metric_id: string;
  label: string;
  description: string;
  domain: string;
  unit: string;
  value_type: string;
  direction: string;
  scoreability: string;
  required_scopes: string[];
  platforms: string[];
  assays: string[];
  denominator?: string;
  canonical_calculation?: string;
  caveats?: string[];
  aliases?: DiagAlias[];
  references?: string[];
}
export interface DiagSignal {
  signal_id: string;
  label: string;
  description: string;
  metrics: string[];
  platforms?: string[];
  related_causes?: string[];
  is_root_cause?: boolean;
  references?: string[];
}
export interface DiagIssue {
  issue_id: string;
  title: string;
  summary: string;
  outcome_domains: string[];
  platforms: string[];
  workflow_stages: string[];
  supporting_signals: string[];
  contradicting_signals?: string[];
  candidate_root_causes: string[];
  impacts: string[];
  required_evidence: string[];
  missing_evidence?: string[];
  confirmatory_tests: string[];
  recovery_classes: string[];
  computational_actions?: string[];
  sequencing_actions?: string[];
  wetlab_actions?: string[];
  related_issues?: string[];
  simulation_modes?: string[];
  references?: string[];
  what_this_issue_cannot_explain: string;
}
export interface DiagCause {
  cause_id: string;
  title: string;
  mechanism: string;
  workflow_stage: string;
  produces_issues: string[];
  observable_signals: string[];
  evidence_against?: string[];
  required_inputs: string[];
  diagnostic_tests: string[];
  cell_recovery_relationship: DiagRelationship;
  sample_integrity_relationship: DiagRelationship;
  expression_fidelity_relationship: DiagRelationship;
  recoverability: string;
  recommended_actions?: string[];
  references?: string[];
  simulation_modes?: string[];
}
export interface DiagTest {
  test_id: string;
  title: string;
  purpose: string;
  required_inputs: string[];
  algorithm_summary: string;
  outputs: string;
  interpretation: string;
  limitations: string;
  supports_causes: string[];
  rejects_causes?: string[];
  status: "implemented" | "planned" | "external";
  implemented_by?: string;
  references?: string[];
}
export interface DiagRecoveryAction {
  recovery_class: string;
  label: string;
  description: string;
}
export interface DiagReference {
  reference_id: string;
  title: string;
  source: string;
  url?: string;
  assay_context?: string;
  note?: string;
  evidence_strength: string;
}
export interface DiagnosticCatalog {
  catalog_version: string;
  metrics: DiagMetric[];
  signals: DiagSignal[];
  issues: DiagIssue[];
  root_causes: DiagCause[];
  diagnostic_tests: DiagTest[];
  recovery_actions: DiagRecoveryAction[];
  references: DiagReference[];
}

export async function loadDiagnosticCatalog(): Promise<DiagnosticCatalog | null> {
  try {
    const raw = await fs.readFile(
      path.join(REPO_ROOT, "spec", "diagnostics", "catalog.json"),
      "utf8",
    );
    const parsed = JSON.parse(raw) as DiagnosticCatalog;
    if (!parsed || !Array.isArray(parsed.issues)) return null;
    return parsed;
  } catch {
    return null;
  }
}
