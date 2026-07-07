from seqcolyte.io.fastx import FastqRecord, write_fastx_gz
from sim.sanity import r1_length_stats, whitelist_hit_rate
from conftest import synth_cb, synth_umi


def test_r1_length_stats_pass(control, tmp_path):
    c = control(10)
    st = r1_length_stats(c["r1"])
    assert st["min"] == st["max"] == 28 and st["n"] == 10


def test_short_r1_detected(tmp_path):
    path = str(tmp_path / "bad_R1.fastq.gz")
    recs = [FastqRecord(name="a", sequence="ACGT" * 7, quality="I" * 28),          # 28
            FastqRecord(name="b", sequence="ACGT" * 6 + "ACG", quality="I" * 27)]  # 27
    write_fastx_gz(path, recs)
    st = r1_length_stats(path)
    assert st["min"] == 27 and st["max"] == 28  # not all 28 -> would fail the check


def test_whitelist_hit_rate(tmp_path):
    # control barcodes are synth_cb(i); put 0 and 1 in the whitelist -> 2/4 hits
    path = str(tmp_path / "R1.fastq.gz")
    recs = [FastqRecord(name=f"r{i}", sequence=synth_cb(i) + synth_umi(i), quality="I" * 28)
            for i in range(4)]
    write_fastx_gz(path, recs)
    whitelist = {synth_cb(0).encode("ascii"), synth_cb(1).encode("ascii")}
    rate, hits, total = whitelist_hit_rate(path, whitelist, cb_len=16)
    assert (hits, total) == (2, 4)
    assert rate == 0.5
