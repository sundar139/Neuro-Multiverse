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
    "APPROVED_DATA_ROOT_PREFIX",
    "SUBJECT_MANIFEST_COLUMNS",
    "USE_RESTRICTIONS",
    "AccessStatus",
    "AcquisitionEvent",
    "DatasetAccessRecord",
    "DatasetRole",
    "HashAlgorithm",
    "LicenseStatus",
    "SubjectManifest",
    "SubjectManifestRecord",
    "openneuro_doi_is_valid",
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

#: The only approved portable external data root. A verified hash manifest and
#: target root must live beneath it; never inside the Git repository.
APPROVED_DATA_ROOT_PREFIX = "$HOME/neuromultiverse-data/"


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


class LicenseStatus(StrEnum):
    """Whether a dataset's governing license is conclusively established.

    A derivative can carry a repository-displayed license that conflicts with
    the license of the upstream data it was built from. That layering is a
    ``CONFLICT`` until an authoritative source reconciles it, and a conflicted
    or unverified license can never authorize acquisition.
    """

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICT = "CONFLICT"


#: Controlled short values for conservative effective use restrictions.
USE_RESTRICTIONS: frozenset[str] = frozenset(
    {
        "no_commercial_use",
        "no_redistribution",
        "attribution_required",
        "share_alike",
        "registration_required",
    }
)


_OPENNEURO_DOI_RE = re.compile(r"^10\.18112/openneuro\.(ds\d{6})\.v(\d+\.\d+\.\d+)$")


def openneuro_doi_is_valid(doi: str, accession: str, version: str) -> bool:
    """Return whether ``doi`` is a well-formed OpenNeuro snapshot DOI.

    The DOI must encode both the accession and the pinned snapshot version, e.g.
    ``10.18112/openneuro.ds000030.v1.0.0``. An unversioned DOI, a version
    mismatch, or an accession mismatch all return False, so a pinned snapshot can
    never be recorded against a DOI that names a different thing.
    """
    match = _OPENNEURO_DOI_RE.match(doi.strip())
    if match is None:
        return False
    return match.group(1) == accession and match.group(2) == version


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
    # ``license_id`` is the single effective/governing identifier for display and
    # cross-checks. The layered fields below carry the full picture when a
    # derivative's repository license differs from its upstream data license.
    license_id: str = Field(min_length=1)
    license_status: LicenseStatus
    repository_license_id: str | None = None
    upstream_license_ids: list[str] = Field(default_factory=list)
    effective_use_restrictions: list[str] = Field(default_factory=list)
    access_status: AccessStatus
    registration_required: bool
    approval_required: bool
    redistribution_allowed: bool
    commercial_use_allowed: bool
    # Whether the *provider or repository* license/terms explicitly restrict
    # re-identification. This is a fact about the source, not the project's own
    # standing prohibition, which is unconditional and lives in the protocol.
    provider_reidentification_restricted: bool
    # Identifies the exact file set the next acquisition event would retrieve.
    # Size evidence is only valid for this same scope: a full-dataset total can
    # never authorize a subset download.
    acquisition_scope_id: str = Field(min_length=1)
    # ``expected_size_bytes`` is the size of the set named by ``size_scope_id``;
    # it is authorization evidence only when that scope equals the acquisition
    # scope. A provider-wide total is informational, recorded in
    # ``expected_size_source`` prose, never as verified subset evidence.
    expected_size_bytes: NonNegativeInt | None = None
    size_scope_id: str | None = None
    # Opaque, non-secret reference to the external evidence backing the size (a
    # digest of the pilot plan, never an absolute path). Present iff size_verified.
    size_evidence_reference: str | None = None
    expected_size_source: str = Field(min_length=1)
    verification_date: date
    citation_ids: Annotated[list[str], Field(min_length=1)]
    target_root: str = Field(min_length=1)
    hash_algorithm: HashAlgorithm = "sha256"
    # Portable, outside-Git path to the checksum manifest for this dataset. When
    # verified it must live under target_root, which must be under the approved
    # data root; the extension must match the hash algorithm. Not created here.
    hash_manifest_location: str | None = None
    # Numeric storage evidence. All present together (and satisfying the capacity
    # inequality) exactly when storage_verified is true; all None otherwise.
    storage_available_bytes: NonNegativeInt | None = None
    storage_required_bytes: NonNegativeInt | None = None
    storage_margin_bytes: NonNegativeInt | None = None
    # Non-secret pointer to an external acquisition log / approval record. Never a
    # user path, username, token, account email, or credential.
    storage_evidence_reference: str | None = None
    # Binds storage evidence to a scope: measured capacity for one scope must not
    # authorize another. Present iff storage_verified.
    storage_scope_id: str | None = None
    # Explicit acquisition-checklist prerequisites, each machine-enforced. They
    # are separate booleans rather than one "verified" flag so that a single
    # unmet item cannot be papered over. ``storage_verified`` is only true after
    # the external directory is provisioned, its path recorded outside Git, and
    # measured free capacity exceeds the expected acquisition with margin; it is
    # never inferred from a non-empty ``target_root``.
    citation_verified: bool
    size_verified: bool
    storage_verified: bool
    hash_strategy_verified: bool
    # A separate human approval gate. Acquisition can only be permitted after an
    # independent reviewer has approved this governance record; a preflight that
    # merely satisfies the technical prerequisites is never that approval.
    independent_approval_verified: bool
    independent_approval_reference: str | None = None
    # Present (nonblank) exactly when access is gated; ``None`` when READY.
    required_manual_action: str | None = None
    acquisition_permitted: bool

    @model_validator(mode="after")
    def _check_invariants(self) -> DatasetAccessRecord:
        _reject_home_paths(self.target_root, "target_root")
        for src in self.authoritative_sources:
            if not src.strip():
                raise ValueError("authoritative_sources must not contain blank entries")

        unknown = set(self.effective_use_restrictions) - USE_RESTRICTIONS
        if unknown:
            raise ValueError(f"unknown effective_use_restrictions: {sorted(unknown)}")

        # Conservative effective restrictions must bind the boolean flags.
        if "no_commercial_use" in self.effective_use_restrictions and self.commercial_use_allowed:
            raise ValueError("no_commercial_use restriction conflicts with commercial_use_allowed")
        if "no_redistribution" in self.effective_use_restrictions and self.redistribution_allowed:
            raise ValueError("no_redistribution restriction conflicts with redistribution_allowed")

        # A conflicted license cannot present as READY: reachable but ambiguous.
        if (
            self.license_status is LicenseStatus.CONFLICT
            and self.access_status is AccessStatus.READY
        ):
            raise ValueError(
                "a CONFLICT license cannot be READY; use SOURCE_AMBIGUOUS until reconciled"
            )

        # Size evidence must belong to the acquisition scope, not a wider set,
        # and must cite an opaque external evidence reference.
        if self.size_verified:
            if self.expected_size_bytes is None:
                raise ValueError("size_verified cannot be true while expected_size_bytes is None")
            if not (self.size_scope_id and self.size_scope_id.strip()):
                raise ValueError("size_verified requires a nonblank size_scope_id")
            if self.size_scope_id != self.acquisition_scope_id:
                raise ValueError(
                    "size_verified evidence is for a different scope "
                    f"({self.size_scope_id!r} != {self.acquisition_scope_id!r})"
                )
            if not (self.size_evidence_reference and self.size_evidence_reference.strip()):
                raise ValueError("size_verified requires a nonblank size_evidence_reference")
            _reject_home_paths(self.size_evidence_reference, "size_evidence_reference")
        else:
            if self.size_scope_id is not None:
                raise ValueError("size_scope_id must be None while size_verified is false")
            if self.size_evidence_reference is not None:
                raise ValueError(
                    "size_evidence_reference must be None while size_verified is false"
                )

        # Hash strategy must point at a portable, algorithm-matched manifest that
        # lives under the target root, which itself is under the approved root.
        if self.hash_strategy_verified:
            location = self.hash_manifest_location
            if not (location and location.strip()):
                raise ValueError("hash_strategy_verified requires a hash_manifest_location")
            _reject_home_paths(location, "hash_manifest_location")
            expected_ext = f".{self.hash_algorithm}"
            if not location.endswith(expected_ext):
                raise ValueError(
                    f"hash_manifest_location must end with {expected_ext} for {self.hash_algorithm}"
                )
            if not self.target_root.startswith(APPROVED_DATA_ROOT_PREFIX):
                raise ValueError(f"target_root must be under {APPROVED_DATA_ROOT_PREFIX}")
            if not location.startswith(self.target_root + "/"):
                raise ValueError("hash_manifest_location must be under target_root")
            if location == self.target_root:
                raise ValueError("hash_manifest_location must not equal target_root")

        # Storage evidence is all-or-nothing, scope-bound, and margin-satisfying.
        available = self.storage_available_bytes
        required = self.storage_required_bytes
        margin = self.storage_margin_bytes
        ref = self.storage_evidence_reference
        scope = self.storage_scope_id
        storage_fields = (available, required, margin, ref, scope)
        if self.storage_verified:
            if (
                available is None
                or required is None
                or margin is None
                or ref is None
                or scope is None
            ):
                raise ValueError("storage_verified requires all storage-evidence fields")
            if not ref.strip():
                raise ValueError("storage_verified requires a nonblank storage_evidence_reference")
            _reject_home_paths(ref, "storage_evidence_reference")
            if "@" in ref:
                raise ValueError("storage_evidence_reference must not contain an email address")
            if scope != self.acquisition_scope_id:
                raise ValueError("storage_scope_id must equal acquisition_scope_id")
            if not self.size_verified or self.size_scope_id != self.acquisition_scope_id:
                raise ValueError("storage_verified requires scope-matched verified size")
            if self.expected_size_bytes is None or required < self.expected_size_bytes:
                raise ValueError("storage_required_bytes must be >= expected_size_bytes")
            if margin <= 0:
                raise ValueError("storage_margin_bytes must be greater than zero")
            if available < required + margin:
                raise ValueError("storage_available_bytes must exceed required + margin")
        elif any(f is not None for f in storage_fields):
            raise ValueError(
                "storage-evidence fields must all be None while storage_verified is false"
            )

        # required_manual_action must track the access state, not float free of it.
        blocking = self.access_status is not AccessStatus.READY
        action = self.required_manual_action
        if blocking and not (action and action.strip()):
            raise ValueError(
                f"access_status {self.access_status.value} is gating and requires a "
                "nonblank required_manual_action"
            )
        if not blocking and action is not None:
            raise ValueError("a READY dataset must not carry a required_manual_action")

        approval_ref = self.independent_approval_reference
        if self.independent_approval_verified:
            if not (approval_ref and approval_ref.strip()):
                raise ValueError("independent approval requires a nonblank approval reference")
            _reject_home_paths(approval_ref, "independent_approval_reference")
        elif approval_ref is not None:
            raise ValueError(
                "independent_approval_reference must be None without verified approval"
            )
        if blocking and approval_ref is not None:
            raise ValueError("a blocked access state cannot carry an approval reference")

        # Acquisition is gated on every prerequisite being verified at once.
        if self.acquisition_permitted:
            if self.access_status is not AccessStatus.READY:
                raise ValueError(
                    "acquisition_permitted cannot be true unless access_status is READY "
                    f"(got {self.access_status.value})"
                )
            if self.license_status is not LicenseStatus.VERIFIED:
                raise ValueError(
                    "acquisition_permitted requires license_status VERIFIED "
                    f"(got {self.license_status.value})"
                )
            missing = [
                name
                for name, ok in (
                    ("citation_verified", self.citation_verified),
                    ("size_verified", self.size_verified),
                    ("storage_verified", self.storage_verified),
                    ("hash_strategy_verified", self.hash_strategy_verified),
                    ("independent_approval_verified", self.independent_approval_verified),
                )
                if not ok
            ]
            if missing:
                raise ValueError(f"acquisition_permitted requires all prerequisites: {missing}")
            if self.expected_size_bytes is None:
                raise ValueError("acquisition_permitted requires a verified expected_size_bytes")
            if self.required_manual_action is not None:
                raise ValueError("acquisition_permitted requires required_manual_action is None")
            if not self.independent_approval_reference:
                raise ValueError("acquisition_permitted requires an independent approval reference")
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
