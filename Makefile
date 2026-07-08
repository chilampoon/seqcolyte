# Thin dev shortcuts. The real interface is the `seqcolyte` CLI (see the README).
# Install with `pip install -e .` into any env — no conda required.

CRATE   := qc/core
QC_BIN  := $(CRATE)/target/release/qc-core
# times to replicate the ~40k-pair sim FASTQ for `make bench` (100 -> ~4M pairs)
BENCH_N ?= 100

.PHONY: install test rust bench pipeline clean

install:               ## editable install into the active env (+ pytest)
	pip install -e ".[dev]"

test:
	python -m pytest -q

rust:                  ## build the qc-core compute binary (needs cargo on PATH)
	cargo build --release --manifest-path $(CRATE)/Cargo.toml

bench: rust            ## time qc-core throughput on ~$(BENCH_N)x the sim FASTQ
	rm -f /tmp/big_R1.fastq /tmp/big_R2.fastq
	for i in $$(seq 1 $(BENCH_N)); do \
	  gzip -dc data/sim/adapter_dimer_f30/R1.fastq.gz >> /tmp/big_R1.fastq; \
	  gzip -dc data/sim/adapter_dimer_f30/R2.fastq.gz >> /tmp/big_R2.fastq; done
	gzip -f /tmp/big_R1.fastq /tmp/big_R2.fastq
	@echo "=== qc-core on ~$(BENCH_N)x40k pairs ===" && /usr/bin/time -p $(QC_BIN) \
	  --spec spec/10x_3p_v3.json --r1 /tmp/big_R1.fastq.gz --r2 /tmp/big_R2.fastq.gz \
	  --whitelist whitelists/3M-february-2018.txt.gz >/dev/null

pipeline:              ## run the whole chain end to end (== seqcolyte pipeline)
	seqcolyte pipeline

clean:
	rm -rf data/sim
