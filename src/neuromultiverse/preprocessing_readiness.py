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

import os
import re
import stat
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

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
    "AUTHORIZED_GRANTOR",
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
    "PlanValidation",
    "PreprocessingReadiness",
    "ValidationMode",
    "evaluate_preprocessing_readiness",
    "validate_execution_plan",
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


# --- Execution-plan validation (dry-run only) ---------------------------------
#
# The filled execution plan lives outside Git. This validator reads that plan —
# and nothing else. It never opens a raw file, never lists a raw directory,
# never reads the FreeSurfer license, and never echoes an external path into its
# own output: a path appears in the result only as a boolean about its shape.

#: Keys whose presence in a plan would assert an authorization nobody granted.
_FORBIDDEN_AUTHORIZATIONS = (
    "authorizes_expansion",
    "authorizes_acquisition",
    "authorizes_push",
    "authorizes_abide",
    "authorizes_cobre",
)

#: ``dry-run`` proves a plan is well formed while authorizing nothing.
#: ``execution`` additionally requires a filled, human-signed authorization
#: block. Neither mode runs a pipeline; the second only permits one.
ValidationMode = Literal["dry-run", "execution"]

#: The only person who may sign an execution authorization for this project.
AUTHORIZED_GRANTOR = "Rohith Sundar Jonnalagadda"

#: Authorization references are opaque, filesystem-safe, and namespaced to this
#: exact unit, so one unit's signature cannot be replayed for another.
_AUTHORIZATION_REFERENCE_RE = re.compile(r"^nm-ds000030-one-subject-exec-[A-Za-z0-9._-]{1,64}$")


class PlanValidation(BaseModel):
    """The outcome of validating a filled execution plan. Path-free by design."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: ValidationMode = "dry-run"
    preprocessing_executed: Literal[False] = False
    valid: bool
    blocking_issues: list[str] = Field(default_factory=list)
    #: Non-fatal notes. An external root that this host cannot see is an
    #: advisory, not a failure: the Windows side cannot stat a WSL path.
    advisories: list[str] = Field(default_factory=list)

    dataset_accession: str | None = None
    acquisition_scope_id: str | None = None
    subject_selection_reference: str | None = None
    external_roots_outside_repository: bool = False
    output_spaces_declared: dict[str, int] = Field(default_factory=dict)
    resource_limits_declared: dict[str, bool] = Field(default_factory=dict)
    freesurfer_license_declared: bool = False
    freesurfer_license_contents_read: Literal[False] = False
    fmriprep_container_declared: bool = False
    #: True only in execution mode with a well-formed signed authorization. The
    #: signature's contents (who, when, which reference) are never echoed here.
    authorization_verified: bool = False


def _is_absolute_path(value: str) -> bool:
    """True for an absolute POSIX or Windows path, whatever host we run on."""
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _outside_repository(value: str, repository_root: Path) -> bool:
    """True when ``value`` cannot resolve to a location inside the repository.

    Compared lexically. A path this host cannot see (a WSL path read on
    Windows) still gets a verdict, and no filesystem walk is ever performed.
    """
    candidate = Path(value)
    try:
        resolved = candidate.expanduser()
    except (RuntimeError, ValueError):
        resolved = candidate
    root = repository_root.resolve()
    for base in (resolved, Path(os.path.normpath(str(resolved)))):
        try:
            if base.is_absolute() and (base == root or root in base.parents):
                return False
        except (OSError, ValueError):  # pragma: no cover - defensive
            continue
        if str(base).replace("\\", "/").startswith(str(root).replace("\\", "/") + "/"):
            return False
    return True


def _check_external_root(
    value: Any, field: str, repository_root: Path, issues: list[str], advisories: list[str]
) -> bool:
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{field} must be a nonblank external path")
        return False
    if not _is_absolute_path(value):
        issues.append(f"{field} must be an absolute path")
        return False
    if not _outside_repository(value, repository_root):
        issues.append(f"{field} must lie outside the repository")
        return False
    # Existence and mode are checked only when this host can see the path, and
    # only on the root itself: no child is listed, opened, or stat-ed.
    probe = Path(value)
    try:
        exists = probe.exists()
    except OSError:  # pragma: no cover - unreachable path syntax for this host
        advisories.append(f"{field} could not be inspected from this host")
        return True
    if not exists:
        advisories.append(f"{field} is not visible from this host and was not inspected")
        return True
    if not probe.is_dir():
        issues.append(f"{field} exists but is not a directory")
        return False
    if os.name == "posix" and stat.S_IMODE(probe.stat().st_mode) != 0o700:
        issues.append(f"{field} must be mode 700")
        return False
    return True


def _check_authorization(plan: Mapping[str, Any], mode: ValidationMode, issues: list[str]) -> bool:
    """Validate the authorization block for the requested mode.

    Dry-run demands the block be *empty*: a valid dry-run plan authorizes
    nothing, which is the property the whole gate exists to guarantee.
    Execution demands the block be filled and signed by the authorized grantor.
    Neither branch echoes the signature's contents.
    """
    authorization = plan.get("authorization")
    if not isinstance(authorization, Mapping):
        issues.append("authorization must be declared")
        return False

    if mode == "dry-run":
        if plan.get("authorizes_execution") is not False:
            issues.append("authorizes_execution must be false in dry-run validation")
        if plan.get("preparation_only") is not True:
            issues.append("preparation_only must be true in dry-run validation")
        if authorization.get("granted") is not False:
            issues.append("authorization.granted must be false in dry-run validation")
        for field in ("granted_by", "granted_at_utc", "reference"):
            if authorization.get(field) != "":
                issues.append(f"authorization.{field} must be empty in dry-run validation")
        return False

    if plan.get("authorizes_execution") is not True:
        issues.append("authorizes_execution must be true in execution validation")
    if plan.get("preparation_only") is not False:
        issues.append("preparation_only must be false in execution validation")
    if authorization.get("granted") is not True:
        issues.append("authorization.granted must be true in execution validation")

    granted_by = authorization.get("granted_by")
    if granted_by != AUTHORIZED_GRANTOR:
        issues.append("authorization.granted_by is not the authorized grantor")

    stamp = authorization.get("granted_at_utc")
    stamp_ok = False
    if not isinstance(stamp, str) or not stamp.strip():
        issues.append("authorization.granted_at_utc must be a nonblank UTC timestamp")
    elif not stamp.endswith("Z"):
        issues.append("authorization.granted_at_utc must be UTC and end with Z")
    else:
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            issues.append("authorization.granted_at_utc is not a valid ISO-8601 timestamp")
        else:
            if parsed.utcoffset() != timedelta(0):
                issues.append("authorization.granted_at_utc must have a zero UTC offset")
            else:
                stamp_ok = True

    reference = authorization.get("reference")
    reference_ok = isinstance(reference, str) and bool(_AUTHORIZATION_REFERENCE_RE.match(reference))
    if not reference_ok:
        issues.append(
            "authorization.reference must match nm-ds000030-one-subject-exec-<safe suffix>"
        )

    return bool(
        plan.get("authorizes_execution") is True
        and plan.get("preparation_only") is False
        and authorization.get("granted") is True
        and granted_by == AUTHORIZED_GRANTOR
        and stamp_ok
        and reference_ok
    )


def _check_pipeline(
    name: str,
    section: Any,
    issues: list[str],
    spaces: dict[str, int],
    limits: dict[str, bool],
) -> None:
    if not isinstance(section, Mapping):
        issues.append(f"pipelines.{name} must be a mapping")
        return
    declared = section.get("output_spaces")
    if not isinstance(declared, list) or not declared:
        issues.append(f"pipelines.{name}.output_spaces must be explicitly filled")
        spaces[name] = 0
    elif any(not isinstance(space, str) or not space.strip() for space in declared):
        issues.append(f"pipelines.{name}.output_spaces must not contain a blank entry")
        spaces[name] = 0
    else:
        spaces[name] = len(declared)

    resources = section.get("resource_limits")
    complete = isinstance(resources, Mapping) and all(
        isinstance(resources.get(key), int | float)
        and not isinstance(resources.get(key), bool)
        and float(resources[key]) > 0
        for key in ("cpus", "memory_gb")
    )
    limits[name] = complete
    if not complete:
        issues.append(f"pipelines.{name}.resource_limits must declare positive cpus and memory_gb")
    if section.get("enabled") is not True:
        issues.append(f"pipelines.{name} must be enabled for the three-way comparison")


def validate_execution_plan(
    plan: Mapping[str, Any],
    *,
    repository_root: Path,
    mode: ValidationMode = "dry-run",
) -> PlanValidation:
    """Validate a filled one-subject execution plan without running anything.

    ``plan`` is the parsed external YAML. Nothing in the returned value can
    identify a participant or disclose an external path: paths are reduced to
    booleans and the selection stays an opaque digest.

    ``mode`` selects the authorization contract. ``dry-run`` requires an empty
    authorization block, so a valid plan authorizes nothing. ``execution``
    requires a filled block signed by the authorized grantor. **Neither mode
    runs a pipeline**: execution validation only permits a later run, it never
    performs one.
    """
    issues: list[str] = []
    advisories: list[str] = []

    authorization_verified = _check_authorization(plan, mode, issues)
    for key in _FORBIDDEN_AUTHORIZATIONS:
        if plan.get(key):
            issues.append(f"{key} is not granted and must not be asserted")
    prohibitions = plan.get("prohibitions")
    if not isinstance(prohibitions, Mapping):
        issues.append("prohibitions must be declared")
    else:
        for key in ("expansion", "abide_acquisition", "cobre_acquisition", "push", "acquisition"):
            if prohibitions.get(key) is not False:
                issues.append(f"prohibitions.{key} must be declared false (not authorized)")

    dataset = plan.get("dataset")
    accession: str | None = None
    scope: str | None = None
    if not isinstance(dataset, Mapping):
        issues.append("dataset section is missing")
    else:
        accession = dataset.get("accession")
        scope = dataset.get("acquisition_scope_id")
        if accession != DS000030_ACCESSION:
            issues.append(f"dataset.accession must be {DS000030_ACCESSION}")
        if scope != DS000030_SCOPE:
            issues.append(f"dataset.acquisition_scope_id must be exactly {DS000030_SCOPE}")

    evidence = plan.get("accepted_evidence")
    if not isinstance(evidence, Mapping):
        issues.append("accepted_evidence section is missing")
    else:
        expected = {
            "acquisition_reference": DS000030_ACQUISITION_REFERENCE,
            "raw_validation_reference": DS000030_RAW_VALIDATION_REFERENCE,
            "permission_reference": DS000030_PERMISSION_REFERENCE,
            "validator_image": DS000030_VALIDATOR_IMAGE,
            "validator_version": DS000030_VALIDATOR_VERSION,
            "bids_schema_version": DS000030_BIDS_SCHEMA_VERSION,
            "validated_file_count": DS000030_VALIDATED_FILE_COUNT,
            "validated_total_bytes": DS000030_PILOT_EXPECTED_BYTES,
            "raw_validation_error_count": 0,
            "raw_validation_warning_count": DS000030_RAW_VALIDATION_WARNING_COUNT,
            "raw_validation_ignored_count": 0,
        }
        for key, accepted in expected.items():
            if evidence.get(key) != accepted:
                issues.append(f"accepted_evidence.{key} does not match the accepted evidence")

    selection: str | None = None
    selection_section = plan.get("subject_selection")
    if not isinstance(selection_section, Mapping):
        issues.append("subject_selection section is missing")
    else:
        try:
            selection = validate_subject_selection_reference(selection_section.get("reference"))
        except ValueError as exc:
            issues.append(str(exc))
        if selection_section.get("recorded_outside_git") is not True:
            issues.append("subject_selection.recorded_outside_git must be true")

    roots_ok = False
    paths = plan.get("external_paths")
    if not isinstance(paths, Mapping):
        issues.append("external_paths section is missing")
    else:
        verdicts = [
            _check_external_root(
                paths.get(field), f"external_paths.{field}", repository_root, issues, advisories
            )
            for field in ("raw_root", "derivatives_root", "work_root")
        ]
        roots_ok = all(verdicts)

    spaces: dict[str, int] = {}
    limits: dict[str, bool] = {}
    pipelines = plan.get("pipelines")
    if not isinstance(pipelines, Mapping):
        issues.append("pipelines section is missing")
    else:
        for name in PIPELINES:
            if name not in pipelines:
                issues.append(f"pipelines.{name} is missing")
                spaces[name] = 0
                limits[name] = False
                continue
            _check_pipeline(name, pipelines[name], issues, spaces, limits)

    fmriprep = pipelines.get("fmriprep") if isinstance(pipelines, Mapping) else None
    container = fmriprep.get("container_reference") if isinstance(fmriprep, Mapping) else None
    container_ok = isinstance(container, str) and bool(container.strip())
    if not container_ok:
        issues.append("pipelines.fmriprep.container_reference must be declared")

    # The license path is checked for shape and presence only. Its contents are
    # never opened: a FreeSurfer license is credential-like material.
    license_path = plan.get("freesurfer_license_path")
    license_ok = isinstance(license_path, str) and bool(license_path.strip())
    if not license_ok:
        issues.append("freesurfer_license_path must be declared")
    elif not _is_absolute_path(str(license_path)):
        issues.append("freesurfer_license_path must be an absolute path")
        license_ok = False
    elif not _outside_repository(str(license_path), repository_root):
        issues.append("freesurfer_license_path must lie outside the repository")
        license_ok = False

    claims = plan.get("claims")
    if not isinstance(claims, Mapping):
        issues.append("claims section is missing")
    elif any(claims.get(key) is not False for key in claims):
        issues.append("every entry in claims must be false before execution")

    return PlanValidation(
        mode=mode,
        valid=not issues,
        blocking_issues=issues,
        advisories=advisories,
        dataset_accession=accession if isinstance(accession, str) else None,
        acquisition_scope_id=scope if isinstance(scope, str) else None,
        subject_selection_reference=selection,
        external_roots_outside_repository=roots_ok,
        output_spaces_declared=spaces,
        resource_limits_declared=limits,
        freesurfer_license_declared=license_ok,
        fmriprep_container_declared=container_ok,
        authorization_verified=authorization_verified,
    )
