# Optional shortcuts only. The real interface is `python -m extract|sim|qc` (see the README).
# After `make install`, run `conda activate seqcolyte` and use the python commands directly.

RUN    := conda run -n seqcolyte
CONFIG ?= sim/configs/adapter_dimer_f30.yaml

CRATE   := qc/core
QC_BIN  := $(CRATE)/target/release/qc-core
# times to replicate the ~40k-pair sim FASTQ for `make bench` (100 -> ~4M pairs)
BENCH_N ?= 100

.PHONY: install test rust bench clean

install:               ## create the conda env + editable install
	conda env create -f environment.yml || conda env update -f environment.yml
	$(RUN) pip install -e .

test:
	$(RUN) python -m pytest -q

rust:                  ## build the qc-core compute-core binary (needs cargo on PATH)
	cargo build --release --manifest-path $(CRATE)/Cargo.toml

bench: rust            ## time python-vs-rust QC compute on ~$(BENCH_N)x the sim FASTQ
	rm -f /tmp/big_R1.fastq /tmp/big_R2.fastq
	for i in $$(seq 1 $(BENCH_N)); do \
	  gzip -dc data/sim/adapter_dimer_f30/R1.fastq.gz >> /tmp/big_R1.fastq; \
	  gzip -dc data/sim/adapter_dimer_f30/R2.fastq.gz >> /tmp/big_R2.fastq; done
	gzip -f /tmp/big_R1.fastq /tmp/big_R2.fastq
	@echo "=== python engine ===" && /usr/bin/time -p $(RUN) python -m qc run --no-llm --engine python \
	  --spec spec/tenx_3p_v3.json --r1 /tmp/big_R1.fastq.gz --r2 /tmp/big_R2.fastq.gz \
	  --whitelist whitelists/3M-february-2018.txt.gz >/dev/null
	@echo "=== rust binary ===" && /usr/bin/time -p $(QC_BIN) \
	  --spec spec/tenx_3p_v3.json --r1 /tmp/big_R1.fastq.gz --r2 /tmp/big_R2.fastq.gz \
	  --whitelist whitelists/3M-february-2018.txt.gz >/dev/null

pipeline: rust         ## protocol -> spec -> control FASTQ -> simulate failures -> QC
	$(RUN) python -m extract build
	$(RUN) python -m sim.get_data whitelist
	$(RUN) python -m sim.get_data data
	$(RUN) python -m sim.sanity
	$(RUN) python -m sim run --config $(CONFIG)
	$(RUN) python -m qc run --spec spec/tenx_3p_v3.json \
	  --r1 data/sim/adapter_dimer_f30/R1.fastq.gz --r2 data/sim/adapter_dimer_f30/R2.fastq.gz \
	  --whitelist whitelists/3M-february-2018.txt.gz --labels sim/labels/adapter_dimer_f30.tsv

clean:
	rm -rf data/sim
