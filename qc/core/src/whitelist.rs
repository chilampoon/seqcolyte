//! Cell-barcode whitelist membership, matching `sim.sanity.load_whitelist` +
//! `qc.checks.check_whitelist_hit_rate`.
//!
//! Python builds a `set[bytes]` of stripped non-empty lines and tests `read[0:16] in set`.
//! We 2-bit-encode each ACGT barcode into a `u64` (`cb_len <= 32`) and store those in an
//! `FxHashSet<u64>`. Whitelist lines that are not `cb_len` bases of pure ACGT can never equal
//! an ACGT read barcode of length `cb_len`, so dropping them is exact; a read barcode with a
//! non-ACGT base fails to encode and is (correctly) counted as off-list.

use anyhow::Result;
use flate2::read::MultiGzDecoder;
use rustc_hash::FxHashSet;
use std::fs::File;
use std::io::{BufRead, BufReader, Read};

/// 2-bit pack an ACGT byte slice into a u64 (A=0 C=1 G=2 T=3). Any other base -> None.
pub fn encode(bc: &[u8]) -> Option<u64> {
    let mut v: u64 = 0;
    for &b in bc {
        let d = match b {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => return None,
        };
        v = (v << 2) | d;
    }
    Some(v)
}

/// True iff `r1[start..start+len]` is a pure-ACGT barcode present in `set`.
pub fn hit(r1: &[u8], start: usize, len: usize, set: &FxHashSet<u64>) -> bool {
    if r1.len() < start + len {
        return false;
    }
    match encode(&r1[start..start + len]) {
        Some(k) => set.contains(&k),
        None => false,
    }
}

/// Load a barcode whitelist (`.txt` or `.txt.gz`), keeping only `cb_len`-length pure-ACGT
/// entries encoded to u64.
pub fn load(path: &str, cb_len: usize) -> Result<FxHashSet<u64>> {
    let file = File::open(path)?;
    let reader: Box<dyn Read> = if path.ends_with(".gz") {
        Box::new(MultiGzDecoder::new(file))
    } else {
        Box::new(file)
    };
    let mut set = FxHashSet::default();
    for line in BufReader::new(reader).lines() {
        let line = line?;
        let t = line.trim();
        if t.len() == cb_len {
            if let Some(k) = encode(t.as_bytes()) {
                set.insert(k);
            }
        }
    }
    Ok(set)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encode_rejects_non_acgt() {
        assert!(encode(b"ACGTN").is_none());
        assert!(encode(b"acgt").is_none()); // lowercase not accepted (matches byte compare)
        assert_eq!(encode(b"A"), Some(0));
        assert_eq!(encode(b"T"), Some(3));
        assert_eq!(encode(b"AC"), Some(0b0001));
    }

    #[test]
    fn membership() {
        let mut set = FxHashSet::default();
        set.insert(encode(b"ACGTACGTACGTACGT").unwrap());
        assert!(hit(b"ACGTACGTACGTACGTAAAAAAAAAAAA", 0, 16, &set));
        assert!(!hit(b"TTTTTTTTTTTTTTTTAAAAAAAAAAAA", 0, 16, &set));
        assert!(!hit(b"ACGTACGTACGTACGN", 0, 16, &set)); // N -> off-list
        assert!(!hit(b"ACGT", 0, 16, &set)); // too short
    }
}
