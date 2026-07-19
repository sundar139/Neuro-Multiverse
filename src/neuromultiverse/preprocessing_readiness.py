"""Fail-closed readiness gate for the future one-subject ds000030 pilot.

This module prepares nothing more than a decision. It answers one question —
*may a later, separately authorized unit run one already-acquired ds000030
subject through fMRIPrep, FSL, and AFNI?* — and refuses unless the accepted
governance state holds exactly.

It never executes a pipeline, never opens a raw file, never resolves a raw
path, and never learns a participant identifier. The subject a later unit would
process is named only by an opaque external selection reference: a namespaced
digest whose preimage lives outside Git with the rest of the private evidence.

The accepted evidence identities below are the single source of truth for both
this gate and ``scripts/verify_data_governance.py``, which imports them.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from neuromultiverse.data_contracts import (
    AccessStatus,
    DatasetAccessRecord,
    _require_opaque_reference,
)
from neuromultiverse.ds000030_pilot import (
    DS000030_ACCESSION,
    DS000030_PILOT_EXPECTED_BYTES,
    DS000030_PILOT_FILE_COUNT,
    DS000030_SCOPE,
)

__all__ = [
    "DS000030_ACQUISITION_REFERENCE",
    "DS000030_BIDS_SCHEMA_VERSION",
    "DS000030_PERMISSION_REFERENCE",
    "DS000030_RAW_VALIDATION_RECEIPT_SHA256",
    "DS000030_RAW_VALIDATION_REFERENCE",
    "DS000030_RAW_VALIDATION_WARNING_COUNT",
    "DS000030_VALIDATED_FILE_COUNT",
    "DS000030_VALIDATOR_IMAGE",
    "DS000030_VALIDATOR_VERSION",
    "DS000030_WARNING_COUNTS",
    "PIPELINES",
    "SELECTION_REFERENCE_PREFIX",
    "PreprocessingReadiness",
    "evaluate_preprocessing_readiness",
    "validate_subject_selection_reference",
]

# --- Accepted ds000030 pilot evidence identities ------------------------------
#
# The public identity of each accepted result is an opaque namespaced digest.
# The artifacts they name (receipts, reports, manifests, plans) stay outside Git
# at mode 600 and are never read by this module.

DS000030_ACQUISITION_REFERENCE = (
    "ds000030-pilot-acquisition-sha256:"
    "e2b194394687738f62b199539cdc7acca6627b40fcd6a4fbb45143891b7410ea"
)
DS000030_RAW_VALIDATION_RECEIPT_SHA256 = (
    "b10cb77f6d2b8a5b3f9ca4154935b2d87eb2725d420f6e639d5bd9c0a9a51261"
)
DS000030_RAW_VALIDATION_REFERENCE = (
    f"ds000030-pilot-raw-validation-sha256:{DS000030_RAW_VALIDATION_RECEIPT_SHA256}"
)
DS000030_PERMISSION_REFERENCE = (
    "ds000030-pilot-permissions-sha256:"
    "aeb62b14a73926783543311e3953a1542f2dde5f57cb1b9a7e0216407157680e"
)
DS000030_VALIDATOR_IMAGE = (
    "bids/validator@sha256:8ef7bf22a5e62430c98c0f3e62627f400c62e85c20db3f691e370ddfdc9963c7"
)
DS000030_VALIDATOR_VERSION = "3.0.0"
DS000030_BIDS_SCHEMA_VERSION = "1.2.4"
DS000030_VALIDATED_FILE_COUNT = DS000030_PILOT_FILE_COUNT
DS000030_RAW_VALIDATION_WARNING_COUNT = 139
DS000030_WARNING_COUNTS: dict[str, int] = {
    "JSON_KEY_RECOMMENDED": 3,
    "SIDECAR_KEY_RECOMMENDED": 135,
    "README_FILE_MISSING": 1,
}

#: The three preprocessing implementations a later unit must compare on the same
#: single subject and the same raw inputs.
PIPELINES: tuple[str, ...] = ("fmriprep", "fsl", "afni")

#: Namespace for the opaque reference to the externally recorded single-subject
#: selection. The preimage (which subject) never enters Git or any log.
SELECTION_REFERENCE_PREFIX = "ds000030-one-subject-selection-sha256:"

_SELECTION_RE = re.compile(rf"^{re.escape(SELECTION_REFERENCE_PREFIX)}[0-9a-f]{{64}}$")

# A BIDS subject entity betrays a participant rather than naming an opaque
# record. A well-formed reference cannot contain one: the namespace spells
# "subject" without the entity hyphen, and the digest is hexadecimal.
_PARTICIPANT_SHAPE_RE = re.compile(r"(?i)sub-")


def validate_subject_selection_reference(value: str | None) -> str:
    """Return ``value`` if it is an opaque, external single-subject reference.

    The reference must be a namespaced SHA-256 (``<namespace>:<64 hex>``). It
    carries no path, no address, no whitespace, and nothing shaped like a
    participant identifier, so neither a log line nor a committed plan can leak
    who was selected.
    """
    reference = _require_opaque_reference(value, "subject_selection_reference")
    if _PARTICIPANT_SHAPE_RE.search(reference):
        raise ValueError(
            "subject_selection_reference must be an opaque digest, not a participant identifier"
        )
    if not _SELECTION_RE.match(reference):
        raise ValueError(
            f"subject_selection_reference must match {SELECTION_REFERENCE_PREFIX}<64 lowercase hex>"
        )
    return reference


class PreprocessingReadiness(BaseModel):
    """The outcome of the readiness gate. Aggregate and disclosure-safe.

    Every field is either a fixed fact, a count, or an opaque reference. No
    field can hold a raw path, a participant identifier, or a command line.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    #: Always ``False`` here: this gate prepares a decision, it never runs a
    #: pipeline. The later execution unit needs its own explicit authorization.
    preprocessing_executed: Literal[False] = False
    preparation_only: Literal[True] = True

    ready: bool
    blocking_issues: list[str] = Field(default_factory=list)

    dataset_id: str
    acquisition_scope_id: str
    acquisition_evidence_reference: str | None = None
    raw_validation_evidence_reference: str | None = None
    permission_evidence_reference: str = DS000030_PERMISSION_REFERENCE
    validator_image: str = DS000030_VALIDATOR_IMAGE
    validator_version: str = DS000030_VALIDATOR_VERSION
    bids_schema_version: str = DS000030_BIDS_SCHEMA_VERSION
    validated_file_count: NonNegativeInt = DS000030_VALIDATED_FILE_COUNT
    validated_total_bytes: NonNegativeInt = DS000030_PILOT_EXPECTED_BYTES
    raw_validation_error_count: NonNegativeInt | None = None
    raw_validation_warning_count: NonNegativeInt | None = None
    raw_validation_ignored_count: NonNegativeInt | None = None
    subject_selection_reference: str | None = None
    pipelines: tuple[str, ...] = PIPELINES


def evaluate_preprocessing_readiness(
    record: DatasetAccessRecord,
    *,
    subject_selection_reference: str | None = None,
    expansion_authorized: bool = False,
) -> PreprocessingReadiness:
    """Decide whether a later one-subject preprocessing pilot may be prepared.

    ``record`` is the governance record for the dataset under consideration.
    The gate re-checks every accepted fact rather than trusting the record's own
    construction, so a record built with ``model_construct`` — or one that drifts
    from the accepted evidence — still fails closed here.

    A ``subject_selection_reference`` is optional: readiness of the *dataset* is
    established without one, and supplying a malformed one is always fatal.
    """
    issues: list[str] = []

    if record.dataset_id != DS000030_ACCESSION:
        issues.append(f"only {DS000030_ACCESSION} may be prepared for preprocessing")
    if record.acquisition_scope_id != DS000030_SCOPE:
        issues.append(f"acquisition scope must be exactly {DS000030_SCOPE}")
    if record.access_status is not AccessStatus.READY:
        issues.append("dataset access is not READY")
    if not record.acquisition_permitted or not record.acquisition_completed:
        issues.append("preprocessing requires a permitted, completed acquisition")
    if record.acquisition_evidence_reference != DS000030_ACQUISITION_REFERENCE:
        issues.append("acquisition evidence reference does not match the accepted receipt")
    if not record.raw_validation_completed:
        issues.append("raw validation is not completed")
    if record.raw_validation_evidence_reference != DS000030_RAW_VALIDATION_REFERENCE:
        issues.append("raw-validation evidence reference does not match the accepted receipt")
    if record.raw_validation_error_count != 0:
        issues.append("raw validation must report zero errors")
    if record.raw_validation_ignored_count != 0:
        issues.append("raw validation must report zero ignored issues")
    warnings = record.raw_validation_warning_count
    if warnings is None or warnings < 0 or warnings != DS000030_RAW_VALIDATION_WARNING_COUNT:
        issues.append(
            f"raw-validation warning count must equal {DS000030_RAW_VALIDATION_WARNING_COUNT}"
        )
    if sum(DS000030_WARNING_COUNTS.values()) != DS000030_RAW_VALIDATION_WARNING_COUNT:
        issues.append("accepted warning-code counts do not sum to the accepted warning total")
    if record.expected_size_bytes != DS000030_PILOT_EXPECTED_BYTES:
        issues.append("expected bytes do not match the validated pilot")
    if DS000030_VALIDATED_FILE_COUNT != DS000030_PILOT_FILE_COUNT:
        issues.append("validated file count does not match the validated pilot")
    if expansion_authorized:
        issues.append("the broader controlled ds000030 subset is not authorized")

    selection: str | None = None
    if subject_selection_reference is not None:
        try:
            selection = validate_subject_selection_reference(subject_selection_reference)
        except ValueError as exc:
            # The message is our own and mentions no candidate value, so the
            # rejected input can never reach a log through this path.
            issues.append(str(exc))

    return PreprocessingReadiness(
        ready=not issues,
        blocking_issues=issues,
        dataset_id=record.dataset_id,
        acquisition_scope_id=record.acquisition_scope_id,
        acquisition_evidence_reference=record.acquisition_evidence_reference,
        raw_validation_evidence_reference=record.raw_validation_evidence_reference,
        raw_validation_error_count=record.raw_validation_error_count,
        raw_validation_warning_count=record.raw_validation_warning_count,
        raw_validation_ignored_count=record.raw_validation_ignored_count,
        subject_selection_reference=selection,
    )
