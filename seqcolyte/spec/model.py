"""``Spec`` — a thin, typed wrapper over the consolidated spec dict with the accessors the
simulator and QC need (oligo lookup, per-read segment offsets, whitelist, read-through chain)."""

from __future__ import annotations

from typing import Any

__all__ = ["Spec"]


class Spec:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self._oligo_index = {o["oligo_id"]: o for o in data.get("oligos", [])}

    # ---------- top level ----------
    @property
    def spec_id(self) -> str:
        return self.data["spec_id"]

    @property
    def assay(self) -> str:
        return self.data["assay"]

    @property
    def chemistry_version(self) -> str:
        return self.data["chemistry_version"]

    @property
    def platform(self) -> str:
        return self.data["platform"]

    @property
    def platform_params(self) -> dict[str, Any]:
        return self.data.get("platform_params", {})

    # ---------- oligos ----------
    @property
    def oligos(self) -> list[dict]:
        return self.data.get("oligos", [])

    def oligo(self, oligo_id: str) -> dict:
        try:
            return self._oligo_index[oligo_id]
        except KeyError:
            raise KeyError(f"no oligo {oligo_id!r} in spec {self.spec_id!r}") from None

    def oligo_sequence(self, oligo_id: str) -> str:
        seq = self.oligo(oligo_id)["sequence"]
        if seq is None:
            raise ValueError(f"oligo {oligo_id!r} has no single sequence (kind={self.oligo(oligo_id)['kind']})")
        return seq

    # ---------- reads / segments ----------
    @property
    def reads(self) -> list[dict]:
        return self.data["read_structure"]["reads"]

    def read(self, name: str) -> dict:
        for r in self.reads:
            if r["read"] == name:
                return r
        raise KeyError(f"no read {name!r} in spec {self.spec_id!r}")

    def has_read(self, name: str) -> bool:
        return any(r["read"] == name for r in self.reads)

    def read_segments(self, name: str) -> list[dict]:
        return sorted(self.read(name)["segments"], key=lambda s: s["order"])

    def segment_offsets(self, name: str) -> dict[str, tuple[int, int]]:
        """Map segment name -> (start, length) by cumulative fixed lengths, in read order.

        Stops accumulating a definite offset once a variable-length (length_range) segment
        is reached (everything downstream is position-ambiguous); such segments are omitted.
        """
        offsets: dict[str, tuple[int, int]] = {}
        pos = 0
        for seg in self.read_segments(name):
            length = seg.get("length")
            if length is None:
                break
            offsets[seg["name"]] = (pos, length)
            pos += length
        return offsets

    def segment_slice(self, read_name: str, segment_name: str) -> slice:
        start, length = self.segment_offsets(read_name)[segment_name]
        return slice(start, start + length)

    def readthrough_chain(self, read_name: str = "R2") -> list[dict]:
        return self.read(read_name).get("readthrough_chain", [])

    # ---------- whitelists ----------
    def whitelist(self, ref: str) -> dict:
        try:
            return self.data["whitelists"][ref]
        except KeyError:
            raise KeyError(f"no whitelist {ref!r} in spec {self.spec_id!r}") from None
