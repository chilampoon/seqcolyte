# Optional shortcuts only. The real interface is `python -m extract|sim|qc` (see the README).
# After `make install`, run `conda activate seqcolyte` and use the python commands directly.

RUN    := conda run -n seqcolyte
CONFIG ?= sim/configs/adapter_dimer_f30.yaml

.PHONY: install test pipeline clean

install:               ## create the conda env + editable install
	conda env create -f environment.yml || conda env update -f environment.yml
	$(RUN) pip install -e .

test:
	$(RUN) python -m pytest -q

pipeline:              ## protocol -> spec -> control FASTQ -> simulate failures -> QC
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
