"""Step 3 — protocol-aware QC. Reads the expected-structure spec + raw FASTQ, runs a deterministic
check toolbox, lets Claude rank + explain the findings, and (given ground-truth labels) scores itself.

Hybrid design: checks are deterministic and testable; the LLM decides what matters and writes the
evidence-chained diagnosis. Everything ties back to the spec, so a Nanopore spec would select
different checks without any engine change.
"""

QC_VERSION = "0.1.0"
