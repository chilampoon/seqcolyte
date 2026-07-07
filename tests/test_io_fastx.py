from pathlib import Path

from seqcolyte.io.fastx import FastqRecord, iter_pairs, read_fastx, write_fastx_gz


def _recs():
    return [
        FastqRecord(name="r0", sequence="ACGTACGT", quality="IIIIIIII", comment="1:N:0:AA"),
        FastqRecord(name="r1", sequence="TTTTGGGG", quality="FFFFFFFF", comment=None),
    ]


def test_write_read_roundtrip(tmp_path):
    path = str(tmp_path / "x.fastq.gz")
    write_fastx_gz(path, _recs())
    got = list(read_fastx(path))
    assert [(r.name, r.sequence, r.quality, r.comment) for r in got] == [
        ("r0", "ACGTACGT", "IIIIIIII", "1:N:0:AA"),
        ("r1", "TTTTGGGG", "FFFFFFFF", None),
    ]


def test_gzip_is_deterministic(tmp_path):
    a, b = str(tmp_path / "a.gz"), str(tmp_path / "b.gz")
    write_fastx_gz(a, _recs())
    write_fastx_gz(b, _recs())
    assert Path(a).read_bytes() == Path(b).read_bytes()


def test_iter_pairs(tmp_path):
    r1p, r2p = str(tmp_path / "R1.gz"), str(tmp_path / "R2.gz")
    write_fastx_gz(r1p, _recs())
    write_fastx_gz(r2p, _recs())
    pairs = list(iter_pairs(r1p, r2p))
    assert len(pairs) == 2
    assert pairs[0][0].name == pairs[0][1].name
