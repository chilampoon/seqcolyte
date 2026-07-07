"""FASTQ I/O.

Reading: prefer ``pysam.FastxFile`` (fast, transparent gzip); fall back to a pure-stdlib
gzip parser behind the same interface so the package never hard-fails without pysam.

Writing: a deterministic gzip writer (``mtime=0``, no embedded filename) so simulated
artifacts are byte-reproducible across runs.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from typing import Iterable, Iterator

__all__ = ["FastqRecord", "read_fastx", "iter_pairs", "write_fastx_gz", "format_record"]


@dataclass(slots=True)
class FastqRecord:
    """A single FASTQ record. ``name`` is the id (no leading '@'); ``comment`` is everything
    after the first space in the header (or None)."""

    name: str
    sequence: str
    quality: str
    comment: str | None = None

    @property
    def header(self) -> str:
        return self.name if self.comment is None else f"{self.name} {self.comment}"


def _read_with_pysam(path: str) -> Iterator[FastqRecord]:
    import pysam

    with pysam.FastxFile(path) as fh:
        for entry in fh:
            yield FastqRecord(
                name=entry.name,
                sequence=entry.sequence,
                quality=entry.quality,
                comment=entry.comment,
            )


def _read_with_stdlib(path: str) -> Iterator[FastqRecord]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:  # type: ignore[operator]
        while True:
            header = fh.readline()
            if not header:
                return
            seq = fh.readline().rstrip("\n")
            fh.readline()  # '+' separator
            qual = fh.readline().rstrip("\n")
            header = header.rstrip("\n")
            if not header.startswith("@"):
                raise ValueError(f"malformed FASTQ header: {header!r}")
            body = header[1:]
            name, _, comment = body.partition(" ")
            yield FastqRecord(name=name, sequence=seq, quality=qual, comment=comment or None)


def read_fastx(path: str) -> Iterator[FastqRecord]:
    """Yield FastqRecords from a (optionally gzipped) FASTQ file."""
    try:
        import pysam  # noqa: F401
    except ImportError:
        yield from _read_with_stdlib(path)
    else:
        yield from _read_with_pysam(path)


def iter_pairs(r1_path: str, r2_path: str) -> Iterator[tuple[FastqRecord, FastqRecord]]:
    """Yield (R1, R2) record pairs in file order. Raises if the files differ in length."""
    r1_iter, r2_iter = read_fastx(r1_path), read_fastx(r2_path)
    for r1 in r1_iter:
        try:
            r2 = next(r2_iter)
        except StopIteration:
            raise ValueError("R2 exhausted before R1 — files are not paired/equal length")
        yield r1, r2
    if next(r2_iter, None) is not None:
        raise ValueError("R1 exhausted before R2 — files are not paired/equal length")


def format_record(rec: FastqRecord) -> bytes:
    """Serialize one record to 4-line FASTQ bytes."""
    if len(rec.sequence) != len(rec.quality):
        raise ValueError(
            f"seq/qual length mismatch for {rec.name!r}: {len(rec.sequence)} != {len(rec.quality)}"
        )
    return f"@{rec.header}\n{rec.sequence}\n+\n{rec.quality}\n".encode("ascii")


def write_fastx_gz(path: str, records: Iterable[FastqRecord], *, compresslevel: int = 6) -> int:
    """Write records to a gzipped FASTQ deterministically (mtime=0, no embedded filename).

    Returns the number of records written.
    """
    n = 0
    with open(path, "wb") as raw:
        # filename="" suppresses the FNAME header field so bytes don't depend on the output path.
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=compresslevel, mtime=0) as gz:
            for rec in records:
                gz.write(format_record(rec))
                n += 1
    return n
