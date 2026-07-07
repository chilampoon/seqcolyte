"""A no-op failure mode (R2 unchanged) — useful for all-clean control runs and as the
minimal example of the plugin interface."""

from __future__ import annotations

from sim.base import FailureMode, R2Result, ReadCtx
from sim.registry import register


@register
class Passthrough(FailureMode):
    name = "passthrough"
    platform = ""  # any platform

    def build_r2(self, ctx: ReadCtx) -> R2Result:
        return R2Result(sequence=ctx.r2.sequence, quality=ctx.r2.quality, construct="clean")
