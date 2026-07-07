from pathlib import Path

from seqcolyte.io.fastx import read_fastx
from sim.engine import run_simulation
from conftest import make_config


def _read_labels(path):
    rows = []
    with open(path) as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            rows.append(dict(zip(hdr, line.rstrip("\n").split("\t"))))
    return rows


def test_determinism_same_seed(control, tmp_path):
    c = control(200)
    cfg1 = make_config(tmp_path / "a", c["r1"], c["r2"], seed=1729)
    cfg2 = make_config(tmp_path / "b", c["r1"], c["r2"], seed=1729)
    run_simulation(cfg1)
    run_simulation(cfg2)
    assert Path(cfg1.out_r2).read_bytes() == Path(cfg2.out_r2).read_bytes()
    assert Path(cfg1.out_labels).read_text() == Path(cfg2.out_labels).read_text()


def test_different_seed_changes_assignments(control, tmp_path):
    c = control(500)
    a = run_simulation(make_config(tmp_path / "a", c["r1"], c["r2"], seed=1))
    b = run_simulation(make_config(tmp_path / "b", c["r1"], c["r2"], seed=2))
    assert a["label_counts"] != b["label_counts"]


def test_label_distribution(control, tmp_path):
    c = control(5000)
    m = run_simulation(make_config(tmp_path, c["r1"], c["r2"], seed=1729))
    fr = m["label_fractions"]
    assert 0.27 <= (1 - fr["clean"]) <= 0.33          # ~30% affected
    assert 0.16 <= fr["readthrough"] <= 0.24          # ~20%
    assert 0.07 <= fr["pure_dimer"] <= 0.13           # ~10%
    for row in _read_labels(m["outputs"]["labels"]):
        assert row["label"] in ("clean", "readthrough", "pure_dimer")
        assert row["affected"] == ("0" if row["label"] == "clean" else "1")


def test_r1_byte_identical_and_cb_umi(control, tmp_path):
    c = control(300)
    cfg = make_config(tmp_path, c["r1"], c["r2"])
    m = run_simulation(cfg)
    assert m["r1_byte_identical"]
    assert Path(cfg.out_r1).read_bytes() == Path(c["r1"]).read_bytes()
    r1 = {r.name: r.sequence for r in read_fastx(c["r1"])}
    for row in _read_labels(cfg.out_labels):
        seq = r1[row["read_id"]]
        assert row["cb"] == seq[:16] and row["umi"] == seq[16:28]


def test_r2_length_preserved(control, tmp_path):
    c = control(300)
    cfg = make_config(tmp_path, c["r1"], c["r2"])
    run_simulation(cfg)
    for rec in read_fastx(cfg.out_r2):
        assert len(rec.sequence) == 91
        assert len(rec.sequence) == len(rec.quality)
