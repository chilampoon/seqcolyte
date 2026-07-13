"""Machine-readable diagnostic catalog: canonical QC metrics, signals, issues, root causes,
diagnostic tests, and recovery actions, plus a deterministic loader/validator/doc-generator.

The catalog is authored once in ``diagnostic_catalog.yaml`` and validated against ``schema.json``
(JSON Schema) plus cross-reference checks in :mod:`qc.catalog.validate`. ``render_docs`` emits the
generated artifacts consumed elsewhere — ``spec/diagnostics/catalog.json`` (read by the studio) and
``docs/qc/*.md``. Nothing here touches the network or an LLM.
"""

from qc.catalog.loader import Catalog, load_catalog

__all__ = ["Catalog", "load_catalog"]
