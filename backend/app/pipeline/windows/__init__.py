"""
Activity window aggregation (Layer 3).

Three-layer pipeline:
  1. raw_events       — immutable vendor payloads (connectors)
  2. activity_segments — classified fragments; may overlap across types
  3. activity_windows  — gap-merged intervals per activity_type for UI

Raw data is never modified. Windows are recomputed incrementally when segments
change. Overlap across different activity types is preserved (e.g. transport +
read at the same time). Same-type small gaps are absorbed per ACTIVITY_MERGE_GAP_MINUTES.
"""

from app.pipeline.windows.service import (
    backfill_all_windows,
    recompute_windows_for_range,
    recompute_windows_for_segments,
)

__all__ = [
    "backfill_all_windows",
    "recompute_windows_for_range",
    "recompute_windows_for_segments",
]
