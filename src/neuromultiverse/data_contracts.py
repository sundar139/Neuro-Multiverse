"""Typed governance contracts for dataset access, manifests, and acquisitions.

These models validate governance and provenance records *before* any dataset is
acquired. They encode the standing prohibitions in ``docs/data_usage.md`` as
type-level invariants so that a malformed or unsafe record fails loudly instead
of silently authorizing an acquisition:

* Acquisition can never be permitted while access is not ``READY``.
* Sizes and counts can never be negative.
* Timestamps must be timezone-aware.
* Checksums use SHA-256 (or a stronger, compatible SHA-2 variant).
* An excluded subject must carry a reason; an included one must not carry an
  unexplained reason.
* No absolute user-home path or username may appear in a portable target root.

The models are strict and forbid unknown fields: a typo in a field name is an
error, not a silently dropped value. They hold no real participant data; the
subject-manifest model is a schema for a future manifest, not a manifest.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    model_validator,
)

__all__ = [
    "SUBJECT_MANIFEST_COLUMNS",
    "AccessStatus",
    "AcquisitionEvent",
    "DatasetAccessRecord",
    "DatasetRole",
    "HashAlgorithm",
    "SubjectManifest",
    "SubjectManifestRecord",
]

# A conservative strict base: every model rejects unknown fields and validates
# on assignment as well as construction.
_STRICT = ConfigDict(extra="forbid", validate_assignment=True, frozen=False)

# Portable-path guards. A committed governance record must never carry a
# machine-specific home path or a username. ``$HOME`` is an allowed placeholder;
# a literal ``/home/<name>`` or ``C:\\Users\\<name>`` is not.
_ABSOLUTE_HOME_PATTERNS = (
    re.compile(r"/home/(?!\$)[^/\s]+"),
    re.compile(r"/Users/(?!\$)[^/\s]+"),
    re.compile(r"[A-Za-z]:[\\/]"),
    re.compile(r"\\Users\\", re.IGNORECASE),
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA512_RE = re.compile(r"^[0-9a-f]{128}$")

HashAlgorithm = Literal["sha256", "sha512"]


class AccessStatus(StrEnum):
    """Provider-access classification for a dataset."""

    READY = "READY"
    MANUAL_AUTHORIZATION_REQUIRED = "MANUAL_AUTHORIZATION_REQUIRED"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    SOURCE_AMBIGUOUS = "SOURCE_AMBIGUOUS"
    BLOCKED = "BLOCKED"


class DatasetRole(StrEnum):
    """Scientific role of a dataset in the study, per the protocol."""

    MAIN_MULTIVERSE = "main_multiverse"
    RAW_PIPELINE_COMPARISON = "raw_pipeline_comparison"
    REPLICATION = "replication"
    OPTIONAL_EXTENSION = "optional_extension"
    OPTIONAL_SENSITIVITY = "optional_sensitivity"


def _reject_home_paths(value: str, field: str) -> str:
    for pattern in _ABSOLUTE_HOME_PATTERNS:
        if pattern.search(value):
            raise ValueError(
                f"{field} must be portable: an absolute user-home path or username "
                f"is not allowed (use a $HOME-relative or dataset-relative path)"
            )
    return value


class DatasetAccessRecord(BaseModel):
    """Governance record for one dataset's access terms and acquisition gate."""

    model_config = _STRICT

    dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    role: DatasetRole
    provider: str = Field(min_length=1)
    authoritative_sources: Annotated[list[str], Field(min_length=1)]
    version: str = Field(min_length=1)
    license_id: str = Field(min_length=1)
    access_status: AccessStatus
    registration_required: bool
    approval_required: bool
    redistribution_allowed: bool
    commercial_use_allowed: bool
    reidentification_prohibited: bool
    # ``None`` means the size is not yet verified. A READY, acquisition-permitted
    # dataset must supply it; a gated dataset may legitimately leave it open.
    expected_size_bytes: NonNegativeInt | None = None
    expected_size_source: str = Field(min_length=1)
    verification_date: date
    citation_ids: Annotated[list[str], Field(min_length=1)]
    target_root: str = Field(min_length=1)
    hash_algorithm: HashAlgorithm = "sha256"
    acquisition_permitted: bool

    @model_validator(mode="after")
    def _check_invariants(self) -> DatasetAccessRecord:
        _reject_home_paths(self.target_root, "target_root")
        for src in self.authoritative_sources:
            if not src.strip():
                raise ValueError("authoritative_sources must not contain blank entries")
        if self.acquisition_permitted and self.access_status is not AccessStatus.READY:
            raise ValueError(
                "acquisition_permitted cannot be true unless access_status is READY "
                f"(got {self.access_status.value})"
            )
        if self.acquisition_permitted and self.expected_size_bytes is None:
            raise ValueError("acquisition_permitted requires a verified expected_size_bytes")
        return self


class SubjectManifestRecord(BaseModel):
    """One row of a future subject manifest. Holds no real participant data.

    Only a provider-issued research identifier may ever populate ``subject_id``;
    the model does not and cannot enforce that a value is synthetic, so callers
    remain responsible for the disclosure rules in ``data/README.md``.
    """

    model_config = _STRICT

    dataset: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    session_id: str | None = None
    site: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    age: Annotated[float, Field(ge=0.0, le=120.0)] | None = None
    sex: Literal["M", "F", "other", "unknown"]
    raw_t1w_path: str = Field(min_length=1)
    raw_bold_path: str = Field(min_length=1)
    # Delimited pipeline tokens with available derivatives, e.g. "ccs,cpac".
    pipeline_availability: str = Field(min_length=1)
    included: bool
    exclusion_reason: str | None = None
    raw_file_checksum: str | None = None
    manifest_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_invariants(self) -> SubjectManifestRecord:
        _reject_home_paths(self.raw_t1w_path, "raw_t1w_path")
        _reject_home_paths(self.raw_bold_path, "raw_bold_path")
        if not self.included and not (self.exclusion_reason and self.exclusion_reason.strip()):
            raise ValueError("an excluded subject (included=false) requires an exclusion_reason")
        if self.included and self.exclusion_reason is not None:
            raise ValueError(
                "an included subject (included=true) must not carry an exclusion_reason"
            )
        if self.raw_file_checksum is not None and not _SHA256_RE.match(self.raw_file_checksum):
            if _SHA512_RE.match(self.raw_file_checksum):
                return self
            raise ValueError("raw_file_checksum must be a lowercase SHA-256 or SHA-512 hex digest")
        return self


class SubjectManifest(BaseModel):
    """A collection of subject rows with manifest-level integrity checks."""

    model_config = _STRICT

    records: list[SubjectManifestRecord]

    def _subject_key(self, record: SubjectManifestRecord) -> tuple[str, str, str | None]:
        return (record.dataset, record.subject_id, record.session_id)

    @model_validator(mode="after")
    def _check_uniqueness(self) -> SubjectManifest:
        seen_keys: set[tuple[str, str, str | None]] = set()
        seen_paths: set[str] = set()
        for record in self.records:
            key = self._subject_key(record)
            if key in seen_keys:
                raise ValueError(f"duplicate subject key detected: {key}")
            seen_keys.add(key)
            for path in (record.raw_t1w_path, record.raw_bold_path):
                if path in seen_paths:
                    raise ValueError(f"duplicate raw path detected: {path}")
                seen_paths.add(path)
        return self

    def duplicate_checksums(self) -> dict[str, list[tuple[str, str, str | None]]]:
        """Group subject keys by shared checksum.

        A shared checksum is *flagged for review*, never auto-treated as a
        duplicate participant: two subjects can legitimately share a checksum
        only if a file was duplicated, which a human must adjudicate. Returns a
        mapping of checksum to the subject keys that carry it, for checksums
        that appear more than once.
        """
        by_checksum: dict[str, list[tuple[str, str, str | None]]] = {}
        for record in self.records:
            if record.raw_file_checksum is None:
                continue
            by_checksum.setdefault(record.raw_file_checksum, []).append(self._subject_key(record))
        return {digest: keys for digest, keys in by_checksum.items() if len(keys) > 1}


class AcquisitionEvent(BaseModel):
    """Provenance record for a completed or attempted acquisition."""

    model_config = _STRICT

    dataset_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    source: str = Field(min_length=1)
    target_root: str = Field(min_length=1)
    file_count: NonNegativeInt
    total_bytes: NonNegativeInt
    hash_manifest: str = Field(min_length=1)
    git_commit: str = Field(min_length=7)
    tool_version: str = Field(min_length=1)
    status: Literal["started", "completed", "failed"]
    error_category: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> AcquisitionEvent:
        _reject_home_paths(self.target_root, "target_root")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.status == "failed" and not (self.error_category and self.error_category.strip()):
            raise ValueError("a failed acquisition requires an error_category")
        if self.status == "completed" and self.completed_at is None:
            raise ValueError("a completed acquisition requires completed_at")
        return self


#: Export column order for a subject manifest. The header-only template file and
#: any future manifest writer derive their columns from this single source.
SUBJECT_MANIFEST_COLUMNS: tuple[str, ...] = tuple(SubjectManifestRecord.model_fields)
