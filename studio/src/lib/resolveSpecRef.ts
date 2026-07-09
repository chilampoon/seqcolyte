import type { SpecDoc } from "./types";

/**
 * Resolve a finding's `evidence[].spec_ref` (a heterogeneous dotted path with an
 * optional [selector]) to a DOM anchor id in the spec viewer, and check whether
 * it actually resolves. The spec-viewer components render matching `id`s.
 * Keyed on the run's snapshot spec — NEVER on spec_id (which drifts).
 */

// Anchor-id helpers — shared by the resolver and the spec viewer so they agree.
export const anchor = {
  read: (read: string) => `spec-read-${read}`,
  chain: (read: string, name: string) => `spec-chain-${read}-${name}`,
  oligo: (id: string) => `spec-oligo-${id}`,
  whitelist: (key: string) => `spec-whitelist-${key}`,
  platformParam: (field: string) => `spec-pp-${field}`,
  libStep: (step: number) => `spec-libstep-${step}`,
};

export interface SpecRefTarget {
  anchorId: string | null;
  label: string; // human-friendly label for the chip
  found: boolean;
}

function parseSelector(seg: string): { key: string; selector?: string } {
  const m = seg.match(/^([^[]+)(?:\[([^\]]+)\])?$/);
  if (!m) return { key: seg };
  return { key: m[1], selector: m[2] };
}

export function resolveSpecRef(spec: SpecDoc | null, ref: string): SpecRefTarget {
  const fail = (label: string): SpecRefTarget => ({ anchorId: null, label, found: false });
  if (!ref) return fail(ref);
  if (!spec) return fail(ref);

  const parts = ref.split(".");
  const root = parts[0];

  if (root === "read_structure") {
    // read_structure.R2  OR  read_structure.R2.readthrough_chain[tso_5prime]
    const readName = parts[1];
    const reads = spec.read_structure?.reads ?? [];
    const read = reads.find((r) => r.read === readName);
    if (parts[2]) {
      const { key, selector } = parseSelector(parts[2]);
      if (key === "readthrough_chain" && selector) {
        const el = read?.readthrough_chain?.find((c) => c.name === selector);
        return el
          ? { anchorId: anchor.chain(readName, selector), label: `${readName} · ${selector}`, found: true }
          : fail(ref);
      }
    }
    return read
      ? { anchorId: anchor.read(readName), label: `read ${readName}`, found: true }
      : fail(ref);
  }

  if (root === "oligos") {
    const id = parts.slice(1).join(".");
    const o = spec.oligos?.find((x) => x.oligo_id === id);
    return o ? { anchorId: anchor.oligo(id), label: id, found: true } : fail(ref);
  }

  if (root === "whitelists") {
    const key = parts.slice(1).join(".");
    return spec.whitelists && key in spec.whitelists
      ? { anchorId: anchor.whitelist(key), label: key, found: true }
      : fail(ref);
  }

  if (root === "platform_params") {
    const field = parts.slice(1).join(".");
    return spec.platform_params && field in spec.platform_params
      ? { anchorId: anchor.platformParam(field), label: `platform · ${field}`, found: true }
      : fail(ref);
  }

  return fail(ref);
}
