//! Loose spec accessors over `serde_json::Value` — no schema re-validation (the Python side
//! already loaded/validated the spec). Mirrors the handful of `seqcolyte.spec.model.Spec`
//! accessors the checks/eval need: the cell-barcode segment slice, the TSO oligo, and
//! `platform_params.dark_base`.

use anyhow::{anyhow, Result};
use serde_json::Value;

const TSO_OLIGO: &str = "oligo_template_switching_oligo_tso";

/// A fixed-offset constant region to validate (e.g. a TSO-derived anchor or a linker) — the read
/// should carry `seq` at `offset` in `read`. Spec-driven, so it works for any library.
pub struct Anchor {
    pub read: String,
    pub offset: usize,
    pub seq: Vec<u8>,
}

pub struct SpecInfo {
    /// Whether R1 has a fixed-length cell_barcode segment (barcode-less custom libraries omit it).
    pub has_cb: bool,
    pub cb_start: usize,
    pub cb_len: usize,
    pub tso: Option<String>,
    pub dark_base: Option<u8>,
    /// Read-through adapter stems derived from the spec's oligos (TruSeq for 10x, Nextera/Tn5 ME for
    /// tagmented libraries, …) — searched in BOTH mates rather than a hardcoded stem.
    pub adapters: Vec<Vec<u8>>,
    /// Fixed-offset constant anchors to validate against the reads.
    pub anchors: Vec<Anchor>,
    /// Expected R1 length when every R1 segment is fixed-length (else None → report only).
    pub expected_r1_len: Option<usize>,
}

/// Longest run of A/C/G/T (uppercased) in `s`, if ≥ 6 nt — how a constant sequence is recovered from
/// a segment name like "TSO anchor CTAACGGG".
fn longest_acgt_run(s: &str) -> Option<Vec<u8>> {
    let up = s.to_ascii_uppercase();
    let bytes = up.as_bytes();
    let (mut best_start, mut best_len) = (0usize, 0usize);
    let mut i = 0;
    while i < bytes.len() {
        if matches!(bytes[i], b'A' | b'C' | b'G' | b'T') {
            let start = i;
            while i < bytes.len() && matches!(bytes[i], b'A' | b'C' | b'G' | b'T') {
                i += 1;
            }
            if i - start > best_len {
                best_len = i - start;
                best_start = start;
            }
        } else {
            i += 1;
        }
    }
    (best_len >= 6).then(|| bytes[best_start..best_start + best_len].to_vec())
}

fn oligo_seq_by_id(v: &Value, id: &str) -> Option<Vec<u8>> {
    v.get("oligos")?.as_array()?.iter().find_map(|o| {
        (o.get("oligo_id").and_then(|x| x.as_str()) == Some(id))
            .then(|| o.get("sequence").and_then(|s| s.as_str()))
            .flatten()
            .map(|s| acgt_only(s))
    })
}

fn acgt_only(s: &str) -> Vec<u8> {
    s.bytes()
        .map(|b| b.to_ascii_uppercase())
        .filter(|b| matches!(b, b'A' | b'C' | b'G' | b'T'))
        .collect()
}

/// Read-through adapter stems from the spec's oligos (role/id heuristics; excludes P5/P7 flow-cell).
fn adapters_from_spec(v: &Value) -> Vec<Vec<u8>> {
    let mut out: Vec<Vec<u8>> = Vec::new();
    let Some(oligos) = v.get("oligos").and_then(|o| o.as_array()) else {
        return out;
    };
    for o in oligos {
        let role = o
            .get("role")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let id = o
            .get("oligo_id")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let hay = format!("{role} {id}");
        let is_readthrough = ["read_through", "readthrough", "readinto", "transposase", "mosaic", "tn5", "nextera"]
            .iter()
            .any(|k| hay.contains(k));
        if !is_readthrough {
            continue;
        }
        let seq = acgt_only(o.get("sequence").and_then(|s| s.as_str()).unwrap_or(""));
        if seq.len() >= 10 {
            let stem: Vec<u8> = seq.into_iter().take(16).collect();
            if !out.contains(&stem) {
                out.push(stem);
            }
        }
    }
    out
}

/// Fixed-offset constant anchors + the expected R1 length, from each read's fixed-length prefix.
fn anchors_and_r1_len(v: &Value) -> (Vec<Anchor>, Option<usize>) {
    let mut anchors = Vec::new();
    let mut expected_r1_len = None;
    let Some(reads) = v
        .get("read_structure")
        .and_then(|r| r.get("reads"))
        .and_then(|r| r.as_array())
    else {
        return (anchors, expected_r1_len);
    };
    for r in reads {
        let read_name = r.get("read").and_then(|x| x.as_str()).unwrap_or("").to_string();
        let Some(segs) = r.get("segments").and_then(|s| s.as_array()) else {
            continue;
        };
        let mut sorted: Vec<&Value> = segs.iter().collect();
        sorted.sort_by_key(|s| s.get("order").and_then(|o| o.as_i64()).unwrap_or(0));
        let mut pos = 0usize;
        let mut all_fixed = true;
        for s in sorted {
            let length = match s.get("length").and_then(|l| l.as_i64()) {
                Some(l) => l as usize,
                None => {
                    all_fixed = false;
                    break; // variable-length segment → offsets past here are not fixed
                }
            };
            let typ = s.get("type").and_then(|t| t.as_str()).unwrap_or("");
            if typ == "constant" {
                let name = s.get("name").and_then(|n| n.as_str()).unwrap_or("");
                let seq = longest_acgt_run(name).or_else(|| {
                    s.get("constant_ref")
                        .and_then(|c| c.as_str())
                        .and_then(|id| oligo_seq_by_id(v, id))
                });
                if let Some(seq) = seq {
                    if seq.len() >= 6 {
                        anchors.push(Anchor { read: read_name.clone(), offset: pos, seq });
                    }
                }
            }
            pos += length;
        }
        if read_name == "R1" && all_fixed && pos > 0 {
            expected_r1_len = Some(pos);
        }
    }
    (anchors, expected_r1_len)
}

pub fn parse_spec(v: &Value) -> Result<SpecInfo> {
    let reads = v
        .get("read_structure")
        .and_then(|r| r.get("reads"))
        .and_then(|r| r.as_array())
        .ok_or_else(|| anyhow!("spec missing read_structure.reads"))?;

    let r1 = reads
        .iter()
        .find(|rd| rd.get("read").and_then(|x| x.as_str()) == Some("R1"))
        .ok_or_else(|| anyhow!("spec has no R1 read"))?;

    // `spec.segment_slice("R1", "cell_barcode")` via segment_offsets. Optional: a custom,
    // barcode-less library (e.g. plate/index-demuxed 5' RNA-seq) simply has no cell_barcode —
    // the whitelist check then skips instead of the run failing.
    let cb = cell_barcode_slice(r1);
    let (cb_start, cb_len) = cb.unwrap_or((0, 0));

    // `spec.oligo_sequence("oligo_template_switching_oligo_tso")` (absent -> None; checks skip).
    let tso = v
        .get("oligos")
        .and_then(|o| o.as_array())
        .and_then(|arr| {
            arr.iter()
                .find(|ol| ol.get("oligo_id").and_then(|x| x.as_str()) == Some(TSO_OLIGO))
        })
        .and_then(|ol| ol.get("sequence"))
        .and_then(|s| s.as_str())
        .map(|s| s.to_string());

    // `spec.platform_params.get("dark_base")` — falsey (missing / null / empty) -> None.
    let dark_base = v
        .get("platform_params")
        .and_then(|p| p.get("dark_base"))
        .and_then(|d| d.as_str())
        .filter(|s| !s.is_empty())
        .and_then(|s| s.bytes().next());

    let adapters = adapters_from_spec(v);
    let (anchors, expected_r1_len) = anchors_and_r1_len(v);

    Ok(SpecInfo {
        has_cb: cb.is_some(),
        cb_start,
        cb_len,
        tso,
        dark_base,
        adapters,
        anchors,
        expected_r1_len,
    })
}

/// Port of `segment_offsets("R1")["cell_barcode"]`: sort R1 segments by `order`, accumulate
/// fixed `length`, stop at the first segment without a fixed length, return cell_barcode's
/// `(start, len)`.
fn cell_barcode_slice(r1: &Value) -> Option<(usize, usize)> {
    let segs = r1.get("segments").and_then(|s| s.as_array())?;

    let mut sorted: Vec<&Value> = segs.iter().collect();
    sorted.sort_by_key(|s| s.get("order").and_then(|o| o.as_i64()).unwrap_or(0));

    let mut pos: usize = 0;
    let mut cb: Option<(usize, usize)> = None;
    for s in sorted {
        let length = match s.get("length").and_then(|l| l.as_i64()) {
            Some(l) => l as usize,
            None => break, // variable-length segment: stop accumulating definite offsets
        };
        let name = s.get("name").and_then(|n| n.as_str()).unwrap_or("");
        if name == "cell_barcode" {
            cb = Some((pos, length));
        }
        pos += length;
    }
    cb
}
