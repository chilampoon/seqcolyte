SHELL := /bin/bash
ENV   := seqcolyte
RUN   := conda run -n $(ENV)

SPEC_ID := tenx_3p_v3
SEED    ?= 100
N_READS ?= 40000
CONFIG  ?= sim/configs/adapter_dimer_f30.yaml

.PHONY: all install tools-check spec spec-check test data whitelist sanity sim pipeline summary clean distclean

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

summary:
	$(RUN) python -m sim.report

# Full chain: spec -> {whitelist, data} -> sanity -> sim -> summary
pipeline: spec whitelist data sanity sim summary

# --- cleanup ---
clean:
	rm -rf data/sim

distclean: clean
	rm -rf data/raw whitelists
