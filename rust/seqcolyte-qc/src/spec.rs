//! Loose spec accessors over `serde_json::Value` — no schema re-validation (the Python side
//! already loaded/validated the spec). Mirrors the handful of `seqcolyte.spec.model.Spec`
//! accessors the checks/eval need: R1 `cycles`, the cell-barcode segment slice, the TSO oligo,
//! and `platform_params.dark_base`.

use anyhow::{anyhow, Result};
use serde_json::Value;

const TSO_OLIGO: &str = "oligo_template_switching_oligo_tso";

pub struct SpecInfo {
    pub r1_cycles: i64,
    pub cb_start: usize,
    pub cb_len: usize,
    pub tso: Option<String>,
    pub dark_base: Option<u8>,
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

    // `spec.read("R1").get("cycles", 28)`
    let r1_cycles = r1.get("cycles").and_then(|c| c.as_i64()).unwrap_or(28);

    // `spec.segment_slice("R1", "cell_barcode")` via segment_offsets.
    let (cb_start, cb_len) = cell_barcode_slice(r1)?;

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

    Ok(SpecInfo {
        r1_cycles,
        cb_start,
        cb_len,
        tso,
        dark_base,
    })
}

/// Port of `segment_offsets("R1")["cell_barcode"]`: sort R1 segments by `order`, accumulate
/// fixed `length`, stop at the first segment without a fixed length, return cell_barcode's
/// `(start, len)`.
fn cell_barcode_slice(r1: &Value) -> Result<(usize, usize)> {
    let segs = r1
        .get("segments")
        .and_then(|s| s.as_array())
        .ok_or_else(|| anyhow!("R1 has no segments"))?;

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
    cb.ok_or_else(|| anyhow!("R1 has no fixed-length cell_barcode segment"))
}
