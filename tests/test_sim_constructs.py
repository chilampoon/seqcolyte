from seqcolyte.dna import revcomp
from seqcolyte.io.fastx import read_fastx
from sim.engine import run_simulation
from conftest import make_config

TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"
R1_READINTO = "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"


def _labels(path):
    with open(path) as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        return [dict(zip(hdr, ln.rstrip("\n").split("\t"))) for ln in fh]


def test_forced_readthrough(control, tmp_path):
    c = control(60)
    # short insert + polyA so TSO+insert+polyA+rc(UMI)+rc(CB) fits within 91 (barcode not truncated away)
    cfg = make_config(tmp_path, c["r1"], c["r2"],
                      params={"affected_fraction": 1.0, "dimer_fraction": 0.0,
                              "readthrough_insert_len": {"min": 0, "max": 5},
                              "polyA_len": {"min": 5, "max": 10}})
    run_simulation(cfg)
    recs = {r.name: r for r in read_fastx(cfg.out_r2)}
    for row in _labels(cfg.out_labels):
        assert row["label"] == "readthrough"
        seq = recs[row["read_id"]].sequence
        assert seq.startswith(TSO)
        assert len(seq) == 91
        # revcomp of THIS pair's barcode/UMI appear in the read, then the read-through adapter stem
        assert revcomp(row["cb"]) in seq
        assert revcomp(row["umi"]) in seq
        assert "AGATCGGAAGAGC" in seq  # R1-readinto adapter stem


def test_forced_pure_dimer_has_tso_polya_polyg(control, tmp_path):
    c = control(60)
    cfg = make_config(tmp_path, c["r1"], c["r2"],
                      params={"affected_fraction": 1.0, "dimer_fraction": 1.0})
    run_simulation(cfg)
    for rec in read_fastx(cfg.out_r2):
        seq = rec.sequence
        assert seq.startswith(TSO)          # hallmark
        assert seq.endswith("G")            # poly-G no-signal tail
        assert "A" in seq[len(TSO):len(TSO) + 25]  # poly(A) directly after the TSO
        assert len(seq) == len(rec.quality) == 91


def test_clean_reads_unchanged(control, tmp_path):
    c = control(200)
    cfg = make_config(tmp_path, c["r1"], c["r2"])
    run_simulation(cfg)
    orig = {r.name: r.sequence for r in c["r2_recs"]}
    out = {r.name: r.sequence for r in read_fastx(cfg.out_r2)}
    for row in _labels(cfg.out_labels):
        if row["label"] == "clean":
            assert out[row["read_id"]] == orig[row["read_id"]]
