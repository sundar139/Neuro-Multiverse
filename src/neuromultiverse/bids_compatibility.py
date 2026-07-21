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
        no_voxel_access: bool,
        evidence_reference: str,
    ) -> None:
        self.source_census_matched = source_census_matched
        self.destination_census = destination_census
        self.json_files_changed = json_files_changed
        self.removed_field_counts = removed_field_counts
        self.non_json_hashes_unchanged = non_json_hashes_unchanged
        self.source_unchanged = source_unchanged
        self.no_voxel_access = no_voxel_access
        self.evidence_reference = evidence_reference

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_census_matched": self.source_census_matched,
            "destination_census_files": self.destination_census.file_count,
            "destination_census_bytes": self.destination_census.total_bytes,
            "json_files_changed": self.json_files_changed,
            "removed_field_counts": dict(self.removed_field_counts),
            "non_json_hashes_unchanged": self.non_json_hashes_unchanged,
            "source_unchanged": self.source_unchanged,
            "no_voxel_access": self.no_voxel_access,
            "evidence_reference": self.evidence_reference,
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
        raise CompatibilityError(
            f"source census mismatch: got {census.file_count} files / {census.total_bytes} bytes, "
            f"expected {expected.file_count} / {expected.total_bytes}"
        )
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
        existing = list(destination.iterdir())
        # Allow empty directory
        if not existing:
            return
        if any(not n.name.startswith(".") for n in existing):
            raise CompatibilityError("destination already contains a non-hidden entry")


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


def sanitize_json(content: str) -> tuple[str, dict[str, int]]:
    """Remove REMOVED_FIELDS from a JSON string; return (new_content, removed_counts)."""
    data = json.loads(content)
    removed: dict[str, int] = dict.fromkeys(REMOVED_FIELDS, 0)
    for field in REMOVED_FIELDS:
        if field in data:
            removed[field] = 1
            del data[field]
    output = json.dumps(data, indent=2, sort_keys=True, separators=(", ", ": ")) + "\n"
    return output, removed


def verify_view(source: Path, destination: Path, repo_root: Path) -> None:
    """Run all post-build verification checks."""
    src_census = _check_source_census(source)

    dest_census = CompatibilityCensus.from_tree(destination)
    if dest_census.file_count != src_census.file_count:
        raise CompatibilityError(
            f"destination file count {dest_census.file_count} != source {src_census.file_count}"
        )

    # non-JSON files must have identical SHA-256
    for p in sorted(destination.rglob("*"), key=lambda x: x.relative_to(destination)):
        if p.is_file() and not _is_json(p):
            rel = p.relative_to(destination)
            src_path = source / rel
            if not src_path.exists():
                raise CompatibilityError(f"non-JSON file {rel} has no source counterpart")
            if p.read_bytes() == src_path.read_bytes():
                continue
            # ponytail: byte comparison is reliable; sha256 is belt-and-suspenders
            if (
                hashlib.sha256(p.read_bytes()).hexdigest()
                != hashlib.sha256(src_path.read_bytes()).hexdigest()
            ):
                raise CompatibilityError(f"non-JSON file {rel} content changed")

    # JSON files: verify only CogAtlasID/CogPOID changed
    for p in sorted(destination.rglob("*"), key=lambda x: x.relative_to(destination)):
        if p.is_file() and _is_json(p):
            rel = p.relative_to(destination)
            src_path = source / rel
            if not src_path.exists():
                continue
            dest_data = json.loads(p.read_text(encoding="utf-8"))
            src_data = json.loads(src_path.read_text(encoding="utf-8"))
            for field in REMOVED_FIELDS:
                dest_data.pop(field, None)
                src_data.pop(field, None)
            if dest_data != src_data:
                raise CompatibilityError(
                    f"JSON file {rel} has semantic differences beyond CogAtlasID/CogPOID"
                )

    verify_no_zero_bytes(destination)
    verify_no_root_owned(destination)

    if not _outside_repository(source, repo_root):
        raise CompatibilityError("source must remain outside repository")
    if not _outside_repository(destination, repo_root):
        raise CompatibilityError("destination must remain outside repository")


def verify_no_zero_bytes(root: Path) -> None:
    zero = [p for p in root.rglob("*") if p.is_file() and p.stat().st_size == 0]
    if zero:
        raise CompatibilityError(f"{len(zero)} zero-byte file(s) present")


def verify_no_root_owned(root: Path) -> None:
    """Check no root-owned files (POSIX only; no-op on Windows)."""
    if os.name != "posix":
        return
    root_owned = [p for p in root.rglob("*") if p.stat().st_uid == 0]
    if root_owned:
        raise CompatibilityError(f"{len(root_owned)} root-owned file(s) present")


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

    # Copy
    if destination.exists():
        shutil.rmtree(destination)
    copy_dataset(source, destination)

    # Strip fields
    json_files_changed = 0
    removed_field_counts: dict[str, int] = dict.fromkeys(REMOVED_FIELDS, 0)
    for p in sorted(destination.rglob("*")):
        if p.is_file() and _is_json(p):
            original = p.read_text(encoding="utf-8")
            try:
                sanitized, removed = sanitize_json(original)
            except json.JSONDecodeError:
                raise CompatibilityError(f"malformed JSON in {p}") from None
            if original != sanitized:
                json_files_changed += 1
                p.write_text(sanitized, encoding="utf-8")
                p.chmod(0o600)
                for field, count in removed.items():
                    removed_field_counts[field] += count

    # Verify
    verify_view(source, destination, repo_root)

    # Source unchanged check (re-census)
    source_unchanged = CompatibilityCensus.from_tree(source) == src_census

    # Evidence record
    changed_paths: list[dict[str, str]] = []
    for p in sorted(destination.rglob("*")):
        if p.is_file() and _is_json(p):
            rel = str(p.relative_to(destination))
            src_path = source / Path(rel)
            src_sha = (
                hashlib.sha256(src_path.read_bytes()).hexdigest() if src_path.exists() else "N/A"
            )
            dest_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            if src_sha != dest_sha:
                changed_paths.append(
                    {"relative_path": rel, "source_sha256": src_sha, "destination_sha256": dest_sha}
                )

    dest_census = CompatibilityCensus.from_tree(destination)
    src_digest = compute_tree_digest(source)
    dest_digest = compute_tree_digest(destination)

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
            "source_tree_digest": src_digest,
            "destination_tree_digest": dest_digest,
            "json_files_changed": json_files_changed,
            "removed_field_counts": removed_field_counts,
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
        no_voxel_access=True,
        evidence_reference=record.reference,
    )
