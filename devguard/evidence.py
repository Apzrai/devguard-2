"""
devguard/evidence.py — Evidence and Provenance layer.

Creates a tamper-evident, cryptographically-linked provenance record for
the analyzed project state.  Every analyzed file is SHA-256 hashed.  An
aggregate chain hash ties them all together into a single fingerprint that
will change if any file is modified.

This runs BEFORE any Bob execution so that the pre-change state is
immutably recorded.

Output schema:
{
  "evidence_id": str,       # UUID
  "recorded_at": str,       # ISO-8601 UTC
  "project_root": str,
  "file_hashes": [FileHashRecord],
  "aggregate_hash": str,    # SHA-256 of all individual hashes concatenated in sort order
  "total_files": int,
  "total_test_functions": int,
}

FileHashRecord:
{
  "path": str,
  "sha256": str,
  "file_type": str,         # "source" | "test" | "doc" | "other"
  "provenance": "OBSERVED",
}
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from devguard.understand import ProjectUnderstanding


# ---------------------------------------------------------------------------
# File type classification
# ---------------------------------------------------------------------------

def _classify(path_str: str) -> str:
    p = Path(path_str)
    if p.name.startswith("test_") and p.suffix == ".py":
        return "test"
    if p.suffix == ".py" and p.name not in ("__init__.py", "__main__.py"):
        return "source"
    if p.suffix == ".md":
        return "doc"
    return "other"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class Evidence:
    """Holds the provenance record for an analyzed project state."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    @property
    def aggregate_hash(self) -> str:
        return self._data["aggregate_hash"]

    @property
    def evidence_id(self) -> str:
        return self._data["evidence_id"]

    @property
    def file_hashes(self) -> list[dict]:
        return self._data["file_hashes"]

    def get_hash(self, path_suffix: str) -> str | None:
        """Return the SHA-256 for a file whose path ends with path_suffix."""
        for fh in self._data["file_hashes"]:
            if fh["path"].replace("\\", "/").endswith(path_suffix.replace("\\", "/")):
                return fh["sha256"]
        return None

    def matches(self, other: "Evidence") -> bool:
        """Return True if two Evidence records have the same aggregate hash."""
        return self._data["aggregate_hash"] == other._data["aggregate_hash"]


def collect_evidence(u: ProjectUnderstanding) -> Evidence:
    """Build a provenance evidence record from a ProjectUnderstanding.

    Hashes every source file, test file, and documentation file recorded
    in the understanding.  Computes an aggregate hash over all of them
    in stable (sorted) path order.

    Args:
        u: A ProjectUnderstanding produced by understand().

    Returns:
        An Evidence instance with full file hash records and aggregate hash.
    """
    data = u.to_dict()
    project_root = Path(data["project_root"])

    file_hashes: list[dict] = []
    total_test_functions = 0

    # Collect hashes from all recorded files (source + test + doc)
    all_file_records = (
        data["source_files"]
        + data["test_files"]
        + data["doc_files"]
    )

    for record in all_file_records:
        path_str = record["path"]
        file_type = _classify(path_str)

        # Use the hash already computed during understand() — no re-read needed
        sha = record["sha256"]

        file_hashes.append({
            "path": path_str,
            "sha256": sha,
            "file_type": file_type,
            "provenance": "OBSERVED",
        })

        if file_type == "test":
            total_test_functions += record.get("test_count", 0)

    # Sort by path for deterministic aggregate computation
    file_hashes.sort(key=lambda x: x["path"])

    # Aggregate hash: SHA-256 over all individual hashes concatenated in sorted path order
    combined = "".join(fh["sha256"] for fh in file_hashes)
    aggregate_hash = hashlib.sha256(combined.encode()).hexdigest()

    return Evidence({
        "evidence_id": str(uuid.uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "file_hashes": file_hashes,
        "aggregate_hash": aggregate_hash,
        "total_files": len(file_hashes),
        "total_test_functions": total_test_functions,
        "provenance": "OBSERVED",
    })
