"""Load a diagnosis threshold profile and turn a metric value into an ok/warn/fail assessment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Profile", "load_profile", "DEFAULT_PROFILE_PATH"]

DEFAULT_PROFILE_PATH = Path(__file__).with_name("profiles") / "default.yaml"

# discrete magnitudes keep the ranking deterministic and easy to explain
_MAG = {"ok": 0.0, "warn": 0.5, "fail": 1.0, "unknown": 0.0}


@dataclass
class Profile:
    version: str
    evidence_strength: str
    metrics: dict[str, dict[str, Any]]

    def is_target_dependent(self, metric_id: str) -> bool:
        return bool(self.metrics.get(metric_id, {}).get("target_dependent"))

    def assess(self, metric_id: str, value: float | None) -> tuple[str, float, str]:
        """Return (status, magnitude, basis) for a metric value. Unknown when there is no rule or no value."""
        rule = self.metrics.get(metric_id)
        if rule is None:
            return "unknown", 0.0, "no profile rule"
        if value is None:
            return "unknown", 0.0, "no value"
        direction = rule.get("direction", "higher_is_better")
        if direction == "higher_is_better":
            fail, warn = rule.get("fail_below"), rule.get("warn_below")
            if fail is not None and value < fail:
                status, basis = "fail", f"{value:g} < fail_below {fail:g}"
            elif warn is not None and value < warn:
                status, basis = "warn", f"{value:g} < warn_below {warn:g}"
            else:
                status, basis = "ok", f"{value:g} >= warn_below {warn:g}" if warn is not None else "ok"
        elif direction == "lower_is_better":
            fail, warn = rule.get("fail_above"), rule.get("warn_above")
            if fail is not None and value > fail:
                status, basis = "fail", f"{value:g} > fail_above {fail:g}"
            elif warn is not None and value > warn:
                status, basis = "warn", f"{value:g} > warn_above {warn:g}"
            else:
                status, basis = "ok", f"{value:g} <= warn_above {warn:g}" if warn is not None else "ok"
        else:  # descriptive
            return "unknown", 0.0, "descriptive metric"
        return status, _MAG[status], basis


def load_profile(path: str | Path | None = None) -> Profile:
    import yaml

    p = Path(path) if path is not None else DEFAULT_PROFILE_PATH
    data = yaml.safe_load(p.read_text())
    return Profile(
        version=str(data.get("profile_version", "?")),
        evidence_strength=str(data.get("evidence_strength", "unknown")),
        metrics=dict(data.get("metrics") or {}),
    )
