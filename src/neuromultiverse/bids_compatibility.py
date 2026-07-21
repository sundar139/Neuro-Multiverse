"""Deterministic BIDS compatibility-view builder.

Strips optional task-ontology metadata fields (CogAtlasID, CogPOID) from a
BIDS dataset copy, leaving all other content byte-identical. The resulting
compatibility view passes fMRIPrep 25.2.5's internal BIDS validation, which
rejects non-URI values in those fields.

The source dataset is never modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_EXPECTED_FILE_COUNT",
    "DEFAULT_EXPECTED_TOTAL_BYTES",
    "REMOVED_FIELDS",
    "BIDSCompatibilityRecord",
    "CompatibilityCensus",
    "CompatibilityError",
    "CompatibilityResult",
    "build_compatibility_view",
    "compute_tree_digest",
    "copy_dataset",
    "sanitize_json",
    "verify_view",
]

#: Fields that are removed from every JSON file in the compatibility view.
REMOVED_FIELDS: tuple[str, ...] = ("CogAtlasID", "CogPOID")

#: Hardcoded pilot census from the accepted acquisition evidence.
DEFAULT_EXPECTED_FILE_COUNT = 22
DEFAULT_EXPECTED_TOTAL_BYTES = 187570603

#: Sanitized error message categories (no paths, no participant data).
_SANITIZED_CENSUS = "source census mismatch"
_SANITIZED_JSON_PARSE = "malformed JSON detected in compatibility source"
_SANITIZED_NON_JSON_BYTE = "non-JSON byte-identity verification failed"
_SANITIZED_JSON_SEMANTIC = "JSON semantic verification failed"
_SANITIZED_SOURCE_IMMUTABLE = "source immutability verification failed"
_SANITIZED_NONEMPTY_DEST = "destination is not empty"


class CompatibilityError(Exception):
    """A precondition or runtime failure in the compatibility-view builder."""


class CompatibilityCensus:
    """A file-count and byte-total census over a tree."""

    def __init__(self, file_count: int, total_bytes: int) -> None:
        self.file_count = file_count
        self.total_bytes = total_bytes

    @classmethod
    def from_tree(cls, root: Path) -> CompatibilityCensus:
        files = [p for p in root.rglob("*") if p.is_file()]
        return cls(len(files), sum(p.stat().st_size for p in files))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CompatibilityCensus):
            return NotImplemented
        return self.file_count == other.file_count and self.total_bytes == other.total_bytes

    def __repr__(self) -> str:
        return f"CompatibilityCensus(files={self.file_count}, bytes={self.total_bytes})"


class BIDSCompatibilityRecord:
    """The canonical evidence record produced by the builder."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record

    @property
    def record(self) -> dict[str, Any]:
        return dict(self._record)

    @property
    def sha256(self) -> str:
        serialized = json.dumps(self._record, indent=2, sort_keys=True, separators=(", ", ": "))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def reference(self) -> str:
        return f"ds000030-bids-compatibility-sha256:{self.sha256}"

    def write(self, path: Path) -> None:
        path.write_text(
            json.dumps(self._record, indent=2, sort_keys=True, separators=(", ", ": ")) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)


class CompatibilityResult:
    """Outcome of a build run; safe to print (no paths, no participant data)."""

    def __init__(
        self,
        source_census_matched: bool,
        destination_census: CompatibilityCensus,
        json_files_changed: int,
        removed_field_counts: dict[str, int],
        non_json_hashes_unchanged: bool,
        source_unchanged: bool,
        source_tree_digest_before: str,
        source_tree_digest_after: str,
        no_voxel_access: bool,
        evidence_reference: str,
        changed_file_count: int,
    ) -> None:
        self.source_census_matched = source_census_matched
        self.destination_census = destination_census
        self.json_files_changed = json_files_changed
        self.removed_field_counts = removed_field_counts
        self.non_json_hashes_unchanged = non_json_hashes_unchanged
        self.source_unchanged = source_unchanged
        self.source_tree_digest_before = source_tree_digest_before
        self.source_tree_digest_after = source_tree_digest_after
        self.no_voxel_access = no_voxel_access
        self.evidence_reference = evidence_reference
        self.changed_file_count = changed_file_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_census_matched": self.source_census_matched,
            "destination_census_files": self.destination_census.file_count,
            "destination_census_bytes": self.destination_census.total_bytes,
            "json_files_changed": self.json_files_changed,
            "removed_field_counts": dict(self.removed_field_counts),
            "non_json_hashes_unchanged": self.non_json_hashes_unchanged,
            "source_unchanged": self.source_unchanged,
            "source_tree_digest_before": self.source_tree_digest_before,
            "source_tree_digest_after": self.source_tree_digest_after,
            "no_voxel_access": self.no_voxel_access,
            "evidence_reference": self.evidence_reference,
            "changed_file_count": self.changed_file_count,
        }


def _is_json(path: Path) -> bool:
    return path.suffix.lower() == ".json"


def _set_modes(root: Path) -> None:
    """Recursively set directories 700 and files 600."""
    for p in root.rglob("*"):
        if p.is_dir():
            p.chmod(0o700)
        elif p.is_file():
            p.chmod(0o600)


def _check_source_census(root: Path) -> CompatibilityCensus:
    """Verify the source tree against the expected pilot census."""
    census = CompatibilityCensus.from_tree(root)
    expected = CompatibilityCensus(DEFAULT_EXPECTED_FILE_COUNT, DEFAULT_EXPECTED_TOTAL_BYTES)
    if census != expected:
        raise CompatibilityError(_SANITIZED_CENSUS)
    return census


def _outside_repository(path: Path, repo_root: Path) -> bool:
    """Return True when *path* cannot resolve to a location inside the repository."""
    try:
        resolved = path.resolve()
    except (RuntimeError, ValueError):
        resolved = path
    root = repo_root.resolve()
    try:
        if resolved == root or root in resolved.parents:
            return False
    except (OSError, ValueError):
        pass
    return not str(resolved).replace("\\", "/").startswith(str(root).replace("\\", "/") + "/")


def _validate_paths(
    source: Path,
    destination: Path,
    evidence_path: Path | None,
    repo_root: Path,
) -> None:
    """Precondition checks that fail closed."""
    if not source.is_absolute():
        raise CompatibilityError("source must be an absolute path")
    if not destination.is_absolute():
        raise CompatibilityError("destination must be an absolute path")
    if evidence_path is not None and not evidence_path.is_absolute():
        raise CompatibilityError("evidence-output path must be absolute")

    if not _outside_repository(source, repo_root):
        raise CompatibilityError("source must lie outside the repository")
    if not _outside_repository(destination, repo_root):
        raise CompatibilityError("destination must lie outside the repository")
    if evidence_path is not None and not _outside_repository(evidence_path, repo_root):
        raise CompatibilityError("evidence-output path must lie outside the repository")

    if source == destination:
        raise CompatibilityError("source and destination must differ")
    if source.resolve() == destination.resolve():
        raise CompatibilityError("source and destination resolve to the same path")

    if destination.exists():
        # Fail on ANY existing content, including hidden files
        try:
            existing = list(destination.iterdir())
        except PermissionError:
            raise CompatibilityError(_SANITIZED_NONEMPTY_DEST) from None
        if existing:
            raise CompatibilityError(_SANITIZED_NONEMPTY_DEST)


def compute_tree_digest(root: Path) -> str:
    """SHA-256 of all file contents sorted by relative path."""
    h = hashlib.sha256()
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda x: x.relative_to(root),
    )
    for p in files:
        rel = str(p.relative_to(root)).encode("utf-8")
        h.update(rel)
        h.update(p.read_bytes())
    return h.hexdigest()


def copy_dataset(source: Path, destination: Path) -> None:
    """Copy the source tree to destination using shutil.copytree."""
    shutil.copytree(source, destination, symlinks=False)
    _set_modes(destination)


def sanitize_json(content: str) -> tuple[str, list[str], bool]:
    """Remove REMOVED_FIELDS from a JSON string.

    Returns (new_content, removed_fields_list, changed).
    When no target field is present, returns the original content unchanged.
    """
    data = json.loads(content)
    removed: list[str] = []
    for field in REMOVED_FIELDS:
        if field in data:
            removed.append(field)
            del data[field]
    if not removed:
        return content, [], False
    output = json.dumps(data, indent=2, sort_keys=True, separators=(", ", ": ")) + "\n"
    return output, removed, True


def verify_view(source: Path, destination: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Run all post-build verification checks; return changed-JSON-file entries."""
    src_census = _check_source_census(source)

    dest_census = CompatibilityCensus.from_tree(destination)
    if dest_census.file_count != src_census.file_count:
        raise CompatibilityError(_SANITIZED_CENSUS)

    # non-JSON files must have identical content
    for p in sorted(destination.rglob("*"), key=lambda x: x.relative_to(destination)):
        if p.is_file() and not _is_json(p):
            rel = p.relative_to(destination)
            src_path = source / rel
            if not src_path.exists():
                raise CompatibilityError(_SANITIZED_NON_JSON_BYTE)
            if (
                hashlib.sha256(p.read_bytes()).hexdigest()
                != hashlib.sha256(src_path.read_bytes()).hexdigest()
            ):
                raise CompatibilityError(_SANITIZED_NON_JSON_BYTE)

    # JSON files: verify only CogAtlasID/CogPOID changed; collect per-file entries
    changed_entries: list[dict[str, Any]] = []
    for p in sorted(destination.rglob("*"), key=lambda x: x.relative_to(destination)):
        if p.is_file() and _is_json(p):
            rel = p.relative_to(destination)
            src_path = source / rel
            if not src_path.exists():
                continue
            dest_bytes = p.read_bytes()
            src_bytes = src_path.read_bytes()
            if dest_bytes == src_bytes:
                continue  # unchanged JSON — byte-identical
            # Changed: determine which fields were removed
            dest_data = json.loads(dest_bytes)
            src_data = json.loads(src_bytes)
            removed_fields: list[str] = []
            for field in REMOVED_FIELDS:
                if field in src_data and field not in dest_data:
                    removed_fields.append(field)
                elif (
                    field in src_data and field in dest_data and src_data[field] != dest_data[field]
                ):
                    raise CompatibilityError(_SANITIZED_JSON_SEMANTIC)
            # Verify no other semantic differences
            src_stripped = {k: v for k, v in src_data.items() if k not in REMOVED_FIELDS}
            dest_stripped = {k: v for k, v in dest_data.items() if k not in REMOVED_FIELDS}
            if src_stripped != dest_stripped:
                raise CompatibilityError(_SANITIZED_JSON_SEMANTIC)
            changed_entries.append(
                {
                    "relative_path": str(rel),
                    "source_sha256": hashlib.sha256(src_bytes).hexdigest(),
                    "destination_sha256": hashlib.sha256(dest_bytes).hexdigest(),
                    "removed_fields": sorted(removed_fields),
                }
            )

    verify_no_zero_bytes(destination)
    verify_no_root_owned(destination)

    if not _outside_repository(source, repo_root):
        raise CompatibilityError("source must remain outside repository")
    if not _outside_repository(destination, repo_root):
        raise CompatibilityError("destination must remain outside repository")

    return changed_entries


def verify_no_zero_bytes(root: Path) -> None:
    zero = [p for p in root.rglob("*") if p.is_file() and p.stat().st_size == 0]
    if zero:
        raise CompatibilityError("zero-byte files present in output")


def verify_no_root_owned(root: Path) -> None:
    """Check no root-owned files (POSIX only; no-op on Windows)."""
    if os.name != "posix":
        return
    root_owned = [p for p in root.rglob("*") if p.stat().st_uid == 0]
    if root_owned:
        raise CompatibilityError("root-owned files present in output")


def _error(err: Exception) -> str:
    """Extract sanitized message from an error, stripping any embedded path or ID."""
    msg = str(err)
    # Replace likely path patterns
    for pattern in ("/home/", "/mnt/", "C:\\", "\\\\wsl", "sub-"):
        if pattern in msg:
            return "internal error: path or identifier leaked"
    return msg


def build_compatibility_view(
    source: Path,
    destination: Path,
    *,
    repo_root: Path,
    evidence_path: Path | None = None,
) -> CompatibilityResult:
    """Build a BIDS compatibility view by stripping CogAtlasID and CogPOID.

    Parameters
    ----------
    source:
        Absolute path to the source BIDS dataset (read-only).
    destination:
        Absolute path for the new compatibility view (will be created).
    repo_root:
        Repository root for outside-repository enforcement.
    evidence_path:
        Optional absolute path for the canonical evidence record.

    Returns
    -------
    CompatibilityResult with aggregate, path-free summary.
    """
    # Preconditions
    _validate_paths(source, destination, evidence_path, repo_root)

    # Census match
    src_census = _check_source_census(source)

    # Source tree digest before copy (immutability anchor)
    src_digest_before = compute_tree_digest(source)

    # Destination must not exist
    if destination.exists():
        raise CompatibilityError(_SANITIZED_NONEMPTY_DEST)

    # Copy
    copy_dataset(source, destination)

    # Strip fields
    json_files_changed = 0
    removed_field_counts: dict[str, int] = dict.fromkeys(REMOVED_FIELDS, 0)
    changed_file_entries: list[dict[str, Any]] = []
    for p in sorted(destination.rglob("*")):
        if p.is_file() and _is_json(p):
            try:
                original_bytes = p.read_bytes()
                sanitized, removed_fields_list, changed = sanitize_json(
                    original_bytes.decode("utf-8")
                )
            except json.JSONDecodeError:
                raise CompatibilityError(_SANITIZED_JSON_PARSE) from None
            if changed:
                json_files_changed += 1
                src_sha = hashlib.sha256(original_bytes).hexdigest()
                dest_sha = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
                for field in removed_fields_list:
                    removed_field_counts[field] = removed_field_counts.get(field, 0) + 1
                p.write_text(sanitized, encoding="utf-8")
                p.chmod(0o600)
                rel = str(p.relative_to(destination))
                changed_file_entries.append(
                    {
                        "relative_path": rel,
                        "source_sha256": src_sha,
                        "destination_sha256": dest_sha,
                        "removed_fields": sorted(removed_fields_list),
                    }
                )
    verify_entries = verify_view(source, destination, repo_root)

    # Source unchanged: tree digest after vs before
    src_digest_after = compute_tree_digest(source)
    source_unchanged = src_digest_before == src_digest_after

    dest_census = CompatibilityCensus.from_tree(destination)
    src_digest = compute_tree_digest(source)

    # Merge changed entries from strip phase with verification entries
    # (they should match; prefer strip-phase entries since they have removed_fields)
    seen_paths = {e["relative_path"] for e in changed_file_entries}
    for ve in verify_entries:
        if ve["relative_path"] not in seen_paths:
            changed_file_entries.append(ve)

    record = BIDSCompatibilityRecord(
        {
            "schema": "ds000030-bids-compatibility-v1",
            "source_acquisition_evidence_reference": (
                "ds000030-pilot-acquisition-sha256:"
                "e2b194394687738f62b199539cdc7acca6627b40fcd6a4fbb45143891b7410ea"
            ),
            "source_raw_validation_evidence_reference": (
                "ds000030-pilot-raw-validation-sha256:"
                "b10cb77f6d2b8a5b3f9ca4154935b2d87eb2725d420f6e639d5bd9c0a9a51261"
            ),
            "source_census": {"files": src_census.file_count, "bytes": src_census.total_bytes},
            "destination_census": {
                "files": dest_census.file_count,
                "bytes": dest_census.total_bytes,
            },
            "source_tree_digest_before": src_digest_before,
            "source_tree_digest_after": src_digest_after,
            "source_tree_digest": src_digest,
            "destination_tree_digest": compute_tree_digest(destination),
            "json_files_changed": json_files_changed,
            "removed_field_counts": removed_field_counts,
            "changed_json_files": changed_file_entries,
            "non_json_hashes_unchanged": True,
            "no_voxel_array_access": True,
            "source_unchanged": source_unchanged,
            "tool_version": "0.1.0",
            "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )

    if evidence_path is not None:
        record.write(evidence_path)

    return CompatibilityResult(
        source_census_matched=True,
        destination_census=dest_census,
        json_files_changed=json_files_changed,
        removed_field_counts=removed_field_counts,
        non_json_hashes_unchanged=True,
        source_unchanged=source_unchanged,
        source_tree_digest_before=src_digest_before,
        source_tree_digest_after=src_digest_after,
        no_voxel_access=True,
        evidence_reference=record.reference,
        changed_file_count=len(changed_file_entries),
    )
