//! Byte-level sequence predicates — verbatim ports of `qc/model.py`.

/// `qc.model.startswith_fuzzy(seq, pattern, max_mismatch)`.
///
/// True if `seq` begins with `pattern` allowing up to `max_mismatch` substitutions.
/// Shorter-than-pattern `seq` is never a match (mirrors the Python length guard).
pub fn startswith_fuzzy(seq: &[u8], pattern: &[u8], max_mismatch: u32) -> bool {
    if seq.len() < pattern.len() {
        return false;
    }
    let mut mm = 0u32;
    for i in 0..pattern.len() {
        if seq[i] != pattern[i] {
            mm += 1;
            if mm > max_mismatch {
                return false;
            }
        }
    }
    true
}

/// `qc.model.has_homopolymer_tail(seq, base, window=20, min_run=15, tol=3)`.
///
/// True if the 3' end of `seq` is a near-pure run of `base`. `seq[-window:]` becomes the
/// whole read when it is shorter than `window`; reads shorter than `min_run` are excluded.
pub fn has_homopolymer_tail(seq: &[u8], base: u8) -> bool {
    const WINDOW: usize = 20;
    const MIN_RUN: usize = 15;
    const TOL: usize = 3;
    if seq.len() < MIN_RUN {
        return false;
    }
    let start = seq.len().saturating_sub(WINDOW);
    let tail = &seq[start..];
    let count = tail.iter().filter(|&&b| b == base).count();
    count >= tail.len() - TOL
}

#[cfg(test)]
mod tests {
    use super::*;

    const TSO: &[u8] = b"AAGCAGTGGTATCAACGCAGAGTACATGGG";

    #[test]
    fn startswith_fuzzy_edges() {
        // exact
        let mut s = TSO.to_vec();
        s.extend_from_slice(b"AAAA");
        assert!(startswith_fuzzy(&s, TSO, 0));
        // 2 substitutions ok
        let mut s2 = b"XX".to_vec();
        s2.extend_from_slice(&TSO[2..]);
        s2.extend_from_slice(b"AAAA");
        assert!(startswith_fuzzy(&s2, TSO, 2));
        // 3 substitutions too many
        let mut s3 = b"XXX".to_vec();
        s3.extend_from_slice(&TSO[3..]);
        s3.extend_from_slice(b"AAAA");
        assert!(!startswith_fuzzy(&s3, TSO, 2));
        // shorter than pattern
        assert!(!startswith_fuzzy(b"AAG", TSO, 2));
        assert!(!startswith_fuzzy(b"", b"A", 0));
    }

    #[test]
    fn homopolymer_tail_edges() {
        // 21 G tail within a 91bp read
        let mut a = vec![b'A'; 70];
        a.extend(std::iter::repeat(b'G').take(21));
        assert!(has_homopolymer_tail(&a, b'G'));
        // no G tail
        assert!(!has_homopolymer_tail(&vec![b'A'; 91], b'G'));
        // too short
        assert!(!has_homopolymer_tail(&vec![b'G'; 14], b'G'));
        // exactly min_run of pure base
        assert!(has_homopolymer_tail(&vec![b'G'; 15], b'G'));
        // tail with tol=3 mismatches allowed (last 20: 17 G + 3 A)
        let mut b = vec![b'A'; 71];
        b.extend(std::iter::repeat(b'G').take(17));
        b.extend(std::iter::repeat(b'A').take(3));
        // last 20 = 17 G + 3 A -> count 17 >= 20-3 -> true
        assert!(has_homopolymer_tail(&b, b'G'));
    }
}
