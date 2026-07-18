"""Strict typed models for the ds000030 five-subject pilot acquisition.

These models validate the *external* pilot plan and approval record before any
transfer. They never carry a signed or temporary download URL: URLs are resolved
from trusted provider metadata at execution time, never persisted. Model errors
and any aggregate summary avoid printing selected participant identifiers.

The models hold no imaging content and no phenotype. They exist so that a
malformed, over-broad, or unapproved plan fails loudly instead of silently
authorizing a download.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

__all__ = [
    "CONTROLLED_RESERVE_BYTES",
    "DS000030_ACCESSION",
    "DS000030_DOI",
    "DS000030_PILOT_EXPECTED_BYTES",
    "DS000030_PILOT_FILE_COUNT",
    "DS000030_PILOT_PLAN_REFERENCE",
    "DS000030_PLAN_CANONICAL_SHA256",
    "DS000030_SCOPE",
    "DS000030_SNAPSHOT",
    "DS000030_STORAGE_REFERENCE",
    "FILE_ROLES",
    "PILOT_BASE_SEED",
    "PILOT_SELECTION_VERSION",
    "PILOT_SUBJECT_COUNT",
    "ROOT_METADATA_ALLOWLIST",
    "PilotAcquisitionPlan",
    "PilotApprovalRecord",
    "PilotFileEntry",
]

DS000030_ACCESSION = "ds000030"
DS000030_SNAPSHOT = "1.0.0"
DS000030_DOI = "10.18112/openneuro.ds000030.v1.0.0"
DS000030_SCOPE = "ds000030_pilot_5_subjects"
PILOT_BASE_SEED = "20260717"
PILOT_SELECTION_VERSION = "pilot-selection-v1"
PILOT_SUBJECT_COUNT = 5

# Aggregate, disclosure-safe pilot evidence (schema v2 plan, URL-free). The plan
# and storage-readiness records live outside Git, mode 600; only these opaque
# digests and counts are committed. Regeneration under the hardened schema
# changed the plan digest solely because URL-bearing fields were removed.
DS000030_PILOT_FILE_COUNT = 22
DS000030_PILOT_EXPECTED_BYTES = 187570603
DS000030_PLAN_CANONICAL_SHA256 = "fb7f62583f00ade72dcba6f85a394c0413516bf949913f31ea68471c3cda0709"
DS000030_PILOT_PLAN_REFERENCE = f"ds000030-pilot-plan-sha256:{DS000030_PLAN_CANONICAL_SHA256}"
DS000030_STORAGE_REFERENCE = (
    "storage-readiness-sha256:3d28205a55ed386c8b5f5ac1bbb123c8d5efc505e11ee55a612d52ce90fd6acd"
)
CONTROLLED_RESERVE_BYTES = 268435456000  # 250 GiB

FileRole = Literal[
    "dataset_metadata",
    "t1w_image",
    "t1w_sidecar",
    "rest_bold_image",
    "rest_bold_sidecar",
]
FILE_ROLES: frozenset[str] = frozenset(FileRole.__args__)  # type: ignore[attr-defined]

#: The only root-level BIDS metadata files the pilot may transfer.
ROOT_METADATA_ALLOWLIST: frozenset[str] = frozenset(
    {"dataset_description.json", "task-rest_bold.json"}
)

_SUBJECT_RE = re.compile(r"^sub-[A-Za-z0-9]+$")
# Anything participant-table, phenotype, behavioural, events, confound, or a task
# other than rest is out of scope for this pilot.
_FORBIDDEN_TOKENS = (
    "participants.tsv",
    "phenotype",
    "_beh",
    "_events",
    "confound",
    "regressor",
)
_STRICT = ConfigDict(extra="forbid", frozen=False)


def _reject_traversal(value: str, field: str) -> str:
    if not value or value.startswith("/") or value.startswith("\\"):
        raise ValueError(f"{field} must be a non-empty relative path")
    parts = re.split(r"[/\\]", value)
    if ".." in parts or "" in parts[1:]:
        raise ValueError(f"{field} must not contain path traversal")
    return value


class PilotFileEntry(BaseModel):
    """One planned file. Never holds a download URL."""

    model_config = _STRICT

    provider_path: str = Field(min_length=1)
    provider_object_id: str = Field(min_length=1)
    local_relative_target: str = Field(min_length=1)
    file_role: FileRole
    # The selected subject this file belongs to, or None for dataset_metadata.
    subject: str | None = None
    provider_size_bytes: PositiveInt
    provider_checksum: str | None = None
    provider_checksum_algorithm: str | None = None
    provider_checksum_suitable_for_content_integrity: bool = False

    @model_validator(mode="after")
    def _check_entry(self) -> PilotFileEntry:
        _reject_traversal(self.local_relative_target, "local_relative_target")
        lowered = f"{self.provider_path} {self.local_relative_target}".lower()
        for token in _FORBIDDEN_TOKENS:
            if token in lowered:
                raise ValueError(f"file matches a forbidden token ({token})")
        if self.file_role == "dataset_metadata":
            if self.subject is not None:
                raise ValueError("dataset_metadata must not be tied to a subject")
        else:
            if not (self.subject and _SUBJECT_RE.match(self.subject)):
                raise ValueError("a subject file requires a valid subject id")
            if not self.local_relative_target.startswith(self.subject + "/"):
                raise ValueError("a subject file target must live under its subject directory")
        if self.provider_checksum is not None and not self.provider_checksum_algorithm:
            raise ValueError("provider_checksum requires provider_checksum_algorithm")
        if self.provider_checksum is None and self.provider_checksum_suitable_for_content_integrity:
            raise ValueError("cannot mark an absent checksum as suitable")
        return self


class PilotAcquisitionPlan(BaseModel):
    """The full five-subject pilot plan. Every invariant is machine-enforced."""

    model_config = _STRICT

    schema_version: str = Field(min_length=1)
    dataset_accession: Literal["ds000030"]
    snapshot: Literal["1.0.0"]
    doi: Literal["10.18112/openneuro.ds000030.v1.0.0"]
    acquisition_scope_id: Literal["ds000030_pilot_5_subjects"]
    base_seed: Literal["20260717"]
    selection_algorithm_version: Literal["pilot-selection-v1"]
    selected_subject_count: int
    selected_subject_ids: list[str]
    files: list[PilotFileEntry] = Field(min_length=1)
    expected_file_count: int
    expected_transfer_bytes: int
    created_at_utc: str = Field(min_length=1)
    starting_git_commit: str = Field(min_length=1)
    metadata_endpoint: str = Field(min_length=1)
    no_download_assertion: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_plan(self) -> PilotAcquisitionPlan:
        ids = self.selected_subject_ids
        if len(ids) != PILOT_SUBJECT_COUNT:
            raise ValueError(f"exactly {PILOT_SUBJECT_COUNT} selected subjects are required")
        if len(set(ids)) != len(ids):
            raise ValueError("selected subject ids must be unique")
        if self.selected_subject_count != PILOT_SUBJECT_COUNT:
            raise ValueError("selected_subject_count must equal five")
        if not all(_SUBJECT_RE.match(sid) for sid in ids):
            raise ValueError("a selected subject id is malformed")

        if self.expected_file_count != len(self.files):
            raise ValueError("expected_file_count must equal the number of files")
        if self.expected_transfer_bytes != sum(f.provider_size_bytes for f in self.files):
            raise ValueError("expected_transfer_bytes must equal the sum of file sizes")

        for attr in ("provider_path", "provider_object_id", "local_relative_target"):
            values = [getattr(f, attr) for f in self.files]
            if len(set(values)) != len(values):
                raise ValueError(f"{attr} values must be unique")

        selected = set(ids)
        t1w_by_subject: set[str] = set()
        bold_by_subject: set[str] = set()
        for entry in self.files:
            if entry.file_role == "dataset_metadata":
                if entry.provider_path not in ROOT_METADATA_ALLOWLIST:
                    raise ValueError("dataset_metadata limited to the root-level allowlist")
                continue
            if entry.subject not in selected:
                raise ValueError("a file belongs to an unselected subject")
            if entry.file_role == "t1w_image":
                t1w_by_subject.add(entry.subject)
            elif entry.file_role == "rest_bold_image":
                bold_by_subject.add(entry.subject)

        missing_t1w = selected - t1w_by_subject
        missing_bold = selected - bold_by_subject
        if missing_t1w:
            raise ValueError("every selected subject requires a T1w image")
        if missing_bold:
            raise ValueError("every selected subject requires a resting-state BOLD image")
        return self


class PilotApprovalRecord(BaseModel):
    """A separate, external, independent-approval record for one exact plan."""

    model_config = _STRICT

    schema_version: str = Field(min_length=1)
    decision: Literal["approved", "not_approved"]
    dataset_accession: Literal["ds000030"]
    acquisition_scope_id: Literal["ds000030_pilot_5_subjects"]
    snapshot: Literal["1.0.0"]
    doi: Literal["10.18112/openneuro.ds000030.v1.0.0"]
    canonical_plan_sha256: str
    expected_file_count: int
    expected_transfer_bytes: int
    size_evidence_reference: str = Field(min_length=1)
    storage_evidence_reference: str = Field(min_length=1)
    approved_code_commit: str
    approval_timestamp_utc: str
    approval_id: str
    reviewer_role: str

    @model_validator(mode="after")
    def _check_approval(self) -> PilotApprovalRecord:
        if self.decision == "approved":
            required = {
                "canonical_plan_sha256": self.canonical_plan_sha256,
                "approved_code_commit": self.approved_code_commit,
                "approval_timestamp_utc": self.approval_timestamp_utc,
                "approval_id": self.approval_id,
                "reviewer_role": self.reviewer_role,
            }
            blank = [name for name, value in required.items() if not value.strip()]
            if blank:
                raise ValueError(f"an approved record requires nonblank fields: {blank}")
            if self.expected_file_count <= 0 or self.expected_transfer_bytes <= 0:
                raise ValueError("an approved record requires positive counts")
        return self
