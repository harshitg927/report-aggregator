"""Report Aggregator — Merge N FOSSology reports into one.

Public API
----------
High-level::

    import report_aggregator as ra
    result = ra.merge(["a.spdx", "b.spdx"])           # auto-detect format
    result = ra.merge(paths, format="spdx2tv", output_path="merged.spdx")

Lower-level building blocks (``merge_reports``, ``InputFile``, ``load_mapping``,
format detection, provenance, RFC-6902 patches) are re-exported below for
advanced callers. Importing this package pulls in only the standard library —
the optional FastAPI service (``report_aggregator.api``) is never imported here.
"""

from __future__ import annotations

__version__ = "0.1.0"

# -- Lower-level building blocks --
from report_aggregator.engine.mapping import (
    MappingConfig,
    MappingError,
    load_mapping,
)
from report_aggregator.engine.merge import (
    InputFile,
    MergeResult,
    merge_reports,
)
from report_aggregator.engine.patch import Patch, apply_patch
from report_aggregator.engine.provenance import ProvenanceTracker
from report_aggregator.formats import (
    SUPPORTED_FORMATS,
    detect_format,
    sniff_format,
)
# -- High-level API --
from report_aggregator.library import (
    FormatDetectionError,
    FormatMismatchError,
    InputError,
    MergeOutput,
    ReportAggregatorError,
    merge,
)

__all__ = [
    "__version__",
    # High-level
    "merge",
    "MergeOutput",
    "ReportAggregatorError",
    "FormatDetectionError",
    "FormatMismatchError",
    "InputError",
    # Formats
    "SUPPORTED_FORMATS",
    "detect_format",
    "sniff_format",
    # Engine
    "merge_reports",
    "InputFile",
    "MergeResult",
    "load_mapping",
    "MappingConfig",
    "MappingError",
    "ProvenanceTracker",
    "Patch",
    "apply_patch",
]
