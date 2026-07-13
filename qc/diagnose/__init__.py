"""Deterministic diagnosis engine: imported evidence + a typed cell target -> firing signals ->
ranked candidate issues and root-cause hypotheses (with supporting/contradicting evidence and
recoverability), all grounded in the diagnostic catalog. Thresholds live in a versioned, provenance-
tagged profile; nothing here computes from an LLM or the network. An optional LLM layer (explain.py)
may narrate/re-rank within the candidate set, but never changes a metric.
"""

from qc.diagnose.engine import diagnose
from qc.diagnose.model import Diagnosis, FiredSignal, Hypothesis, MetricAssessment

__all__ = ["diagnose", "Diagnosis", "FiredSignal", "Hypothesis", "MetricAssessment"]
