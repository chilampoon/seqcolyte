//! Numeric-formatting parity helpers.
//!
//! These must reproduce two CPython operations bit-for-bit on the *same* f64 input:
//!   * `round(x, 4)`   -> [`round4`]
//!   * `f"{x:.1%}"`    -> [`pct1`]
//!
//! Both rely on Rust's `{:.N}` float formatter, which is correctly rounded with
//! round-half-to-even ties — identical to CPython's `round`/`format`.

/// CPython `round(x, 4)`.
///
/// Implemented as "format to 4 decimals (round-half-to-even), reparse" rather than
/// `(x * 1e4).round() / 1e4`, because the latter uses round-half-away-from-zero and
/// accumulates a scaling error. Formatting rounds the true decimal expansion the same
/// way CPython's `round` does.
pub fn round4(x: f64) -> f64 {
    format!("{:.4}", x).parse::<f64>().unwrap()
}

/// CPython `f"{x:.1%}"`.
///
/// The `%` presentation type does a genuine `float` multiply by 100 *before* formatting to one
/// decimal — it is NOT equivalent to rounding the fraction at its third decimal. That multiply
/// re-rounds to a different f64, which can land on the other side of a rounding boundary:
/// `0.0545` (f64 = 0.054499…833) formats as `.3f` → "0.054", but `0.0545 * 100` = 5.45000…0178
/// (just above 5.45) → `:.1%` → "5.5%". IEEE double multiply is bit-identical across languages,
/// so reproducing the multiply is exactly what parity requires.
pub fn pct1(x: f64) -> String {
    format!("{:.1}%", x * 100.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    // round4 against CPython round(x, 4). `want` is the exact f64 CPython round(x, 4) returns
    // (generated with Python); we compare bit-for-bit. Note 0.12345 -> 0.1235 (its f64 sits just
    // above the decimal midpoint, so it is not a true tie and rounds up in both languages).
    #[test]
    fn round4_matches_python() {
        let cases: &[(f64, f64)] = &[
            (0.0, 0.0),
            (1.0, 1.0),
            (0.5, 0.5),
            (2.5, 2.5),
            (0.12345, 0.1235),
            (0.12355, 0.1235),
            (0.0125, 0.0125),
            (0.94895, 0.9489),
            (0.201, 0.201),
            (0.09675, 0.0968),
            (0.85, 0.85),
            (1.0 / 3.0, 0.3333),
            (2.0 / 3.0, 0.6667),
        ];
        for &(x, want) in cases {
            assert_eq!(round4(x), want, "round4({})", x);
        }
    }

    #[test]
    fn pct1_matches_python() {
        // (input, f"{input:.1%}")
        let cases: &[(f64, &str)] = &[
            (0.0, "0.0%"),
            (1.0, "100.0%"),
            (0.05, "5.0%"),
            (0.326, "32.6%"),
            (0.9489, "94.9%"),
            (0.201, "20.1%"),
            (0.097, "9.7%"),
            (0.5, "50.0%"),
            (0.12345, "12.3%"),
            (0.999, "99.9%"),
            (0.0001, "0.0%"),
            // regression: the fraction is just below 0.0545 but *100 rounds up to 5.5% (not 5.4%)
            (2180.0 / 40000.0, "5.5%"),
            (0.0545, "5.5%"),
        ];
        for &(x, want) in cases {
            assert_eq!(pct1(x), want, "pct1({})", x);
        }
    }
}
