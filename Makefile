SHELL := /bin/bash
ENV   := seqcolyte
RUN   := conda run -n $(ENV)

SPEC_ID := tenx_3p_v3
SEED    ?= 100
N_READS ?= 40000
CONFIG  ?= sim/configs/adapter_dimer_f30.yaml

.PHONY: all install tools-check spec spec-check test data whitelist sanity sim qc pipeline summary clean distclean

WHITELIST ?= whitelists/3M-february-2018.txt.gz
QC_DIR    ?= data/sim/adapter_dimer_f30
QC_LABELS ?= sim/labels/adapter_dimer_f30.tsv

# Default: offline + fast (build the spec, run unit tests).
all: spec test

# --- setup ---
install:
	conda env create -f environment.yml || conda env update -f environment.yml
	$(RUN) pip install -e .

tools-check:
	@$(RUN) seqkit version | head -1
	@$(RUN) bash -c 'seqtk 2>&1 | head -2 | tail -1' || echo "seqtk: not found (optional)"

# --- spec (offline, deterministic) ---
spec:
	$(RUN) python -m extract build --spec $(SPEC_ID)

spec-check:              ## CI guard: committed spec must match a fresh build
	$(RUN) python -m extract check --spec $(SPEC_ID)

test:
	$(RUN) python -m pytest

# --- data (network + heavy) ---
whitelist:
	$(RUN) python -m sim.get_data whitelist

data: tools-check
	$(RUN) python -m sim.get_data data --n $(N_READS) --seed $(SEED)

sanity:
	$(RUN) python -m sim.sanity --json-out data/raw/sanity.json

sim: spec
	$(RUN) python -m sim run --config $(CONFIG)

qc:                      ## Step 3: QC the simulated failures (hybrid — Claude ranks + diagnoses)
	$(RUN) python -m qc run --spec spec/$(SPEC_ID).json \
	  --r1 $(QC_DIR)/R1.fastq.gz --r2 $(QC_DIR)/R2.fastq.gz \
	  --whitelist $(WHITELIST) --labels $(QC_LABELS) --json-out $(QC_DIR)/qc_report.json

summary:
	$(RUN) python -m sim.report

# Full chain: spec -> {whitelist, data} -> sanity -> sim -> qc -> summary
pipeline: spec whitelist data sanity sim qc summary

# --- cleanup ---
clean:
	rm -rf data/sim

distclean: clean
	rm -rf data/raw whitelists
