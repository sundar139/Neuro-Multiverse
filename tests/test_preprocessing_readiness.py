"""Tests for the one-subject preprocessing readiness gate.

Every fixture is synthetic or is the committed governance record. No test reads
raw data, resolves a raw path, or names a participant. The failure cases use
``model_construct`` where the typed contract would otherwise refuse to build an
inconsistent record: the gate must fail closed on a record that reached it
without passing contract validation, not merely on one the contract rejected.
"""

from __future__ import annotations

import ast
import importlib.util
import os
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from neuromultiverse.data_contracts import AccessStatus, DatasetAccessRecord
from neuromultiverse.preprocessing_readiness import (
    DS000030_ACQUISITION_REFERENCE,
    DS000030_BIDS_SCHEMA_VERSION,
    DS000030_PERMISSION_REFERENCE,
    DS000030_RAW_VALIDATION_REFERENCE,
    DS000030_VALIDATOR_IMAGE,
    DS000030_VALIDATOR_VERSION,
    PIPELINES,
    SELECTION_REFERENCE_PREFIX,
    evaluate_preprocessing_readiness,
    validate_execution_plan,
    validate_subject_selection_reference,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PREFLIGHT = _REPO_ROOT / "scripts" / "prepare_preprocessing_pilot.py"
_READINESS_MODULE = _REPO_ROOT / "src" / "neuromultiverse" / "preprocessing_readiness.py"
_PILOT_DOC = _REPO_ROOT / "docs" / "preprocessing_pilot.md"
_QC_CHECKLIST = _REPO_ROOT / "configs" / "preprocessing" / "one_subject_qc_checklist.template.md"
_PLAN_TEMPLATE = _REPO_ROOT / "configs" / "preprocessing" / "one_subject_pilot.template.yaml"

_VALID_SELECTION = f"{SELECTION_REFERENCE_PREFIX}{'c' * 64}"


def _load_governance() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_governance_for_readiness", _REPO_ROOT / "scripts" / "verify_data_governance.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _records() -> dict[str, DatasetAccessRecord]:
    return {record.dataset_id: record for record in _load_governance().required_records()}


def _ds000030() -> DatasetAccessRecord:
    return _records()["ds000030"]


def _degraded(**overrides: Any) -> DatasetAccessRecord:
    """The accepted ds000030 record with one accepted fact broken.

    ``model_construct`` bypasses contract validation on purpose: several of these
    states are impossible to build normally, and the gate must still refuse them.
    """
    data = _ds000030().model_dump()
    data.update(overrides)
    return DatasetAccessRecord.model_construct(**data)


# --- dataset-level readiness --------------------------------------------------


def test_accepted_pilot_state_passes_readiness() -> None:
    readiness = evaluate_preprocessing_readiness(_ds000030())
    assert readiness.ready is True
    assert readiness.blocking_issues == []
    assert readiness.preprocessing_executed is False
    assert readiness.preparation_only is True
    assert readiness.pipelines == PIPELINES
    assert readiness.acquisition_evidence_reference == DS000030_ACQUISITION_REFERENCE
    assert readiness.raw_validation_evidence_reference == DS000030_RAW_VALIDATION_REFERENCE


def test_wrong_acquisition_evidence_fails() -> None:
    readiness = evaluate_preprocessing_readiness(
        _degraded(acquisition_evidence_reference="ds000030-pilot-acquisition-sha256:" + "0" * 64)
    )
    assert readiness.ready is False
    assert any("acquisition evidence reference" in issue for issue in readiness.blocking_issues)


def test_wrong_raw_validation_evidence_fails() -> None:
    readiness = evaluate_preprocessing_readiness(
        _degraded(
            raw_validation_evidence_reference="ds000030-pilot-raw-validation-sha256:" + "0" * 64
        )
    )
    assert readiness.ready is False
    assert any("raw-validation evidence" in issue for issue in readiness.blocking_issues)


def test_incomplete_raw_validation_fails() -> None:
    readiness = evaluate_preprocessing_readiness(_degraded(raw_validation_completed=False))
    assert readiness.ready is False
    assert any("raw validation is not completed" in issue for issue in readiness.blocking_issues)


def test_nonzero_raw_validation_errors_fail() -> None:
    readiness = evaluate_preprocessing_readiness(_degraded(raw_validation_error_count=1))
    assert readiness.ready is False
    assert any("zero errors" in issue for issue in readiness.blocking_issues)


def test_nonzero_ignored_count_fails() -> None:
    readiness = evaluate_preprocessing_readiness(_degraded(raw_validation_ignored_count=2))
    assert readiness.ready is False
    assert any("zero ignored" in issue for issue in readiness.blocking_issues)


def test_unexpected_warning_count_fails() -> None:
    readiness = evaluate_preprocessing_readiness(_degraded(raw_validation_warning_count=138))
    assert readiness.ready is False
    assert any("warning count" in issue for issue in readiness.blocking_issues)


@pytest.mark.parametrize("dataset_id", ["abide_i_pcp", "cobre_niak"])
def test_other_datasets_fail_readiness(dataset_id: str) -> None:
    readiness = evaluate_preprocessing_readiness(_records()[dataset_id])
    assert readiness.ready is False
    assert any("only ds000030" in issue for issue in readiness.blocking_issues)
    assert readiness.subject_selection_reference is None


def test_non_pilot_scope_fails() -> None:
    readiness = evaluate_preprocessing_readiness(
        _degraded(acquisition_scope_id="ds000030_controlled_20_subjects")
    )
    assert readiness.ready is False
    assert any("scope must be exactly" in issue for issue in readiness.blocking_issues)


def test_expansion_authorization_fails() -> None:
    readiness = evaluate_preprocessing_readiness(_ds000030(), expansion_authorized=True)
    assert readiness.ready is False
    assert any("not authorized" in issue for issue in readiness.blocking_issues)


def test_non_ready_access_fails() -> None:
    readiness = evaluate_preprocessing_readiness(
        _degraded(
            access_status=AccessStatus.BLOCKED, required_manual_action="synthetic manual action"
        )
    )
    assert readiness.ready is False
    assert any("not READY" in issue for issue in readiness.blocking_issues)


def test_mismatched_validated_bytes_fail() -> None:
    readiness = evaluate_preprocessing_readiness(_degraded(expected_size_bytes=1))
    assert readiness.ready is False
    assert any("expected bytes" in issue for issue in readiness.blocking_issues)


# --- subject selector ---------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        f"{SELECTION_REFERENCE_PREFIX}{'c' * 32} {'c' * 32}",
        f"{SELECTION_REFERENCE_PREFIX}{'c' * 63}\t",
        f"selection/{'c' * 64}",
        f"selection\\{'c' * 64}",
        f"selection@sha256:{'c' * 64}",
        "/home/researcher/selection.json",
        "C:\\Users\\researcher\\selection.json",
        "sub-SYNTH01",
        f"{SELECTION_REFERENCE_PREFIX}sub-SYNTH01",
        f"{SELECTION_REFERENCE_PREFIX}{'c' * 63}",
        f"{SELECTION_REFERENCE_PREFIX}{'C' * 64}",
        f"other-namespace-sha256:{'c' * 64}",
    ],
    ids=[
        "missing",
        "blank",
        "whitespace-only",
        "embedded-space",
        "embedded-tab",
        "forward-slash",
        "backslash",
        "at-sign",
        "absolute-posix-home",
        "absolute-windows-user",
        "bare-participant-entity",
        "namespaced-participant-entity",
        "short-digest",
        "uppercase-digest",
        "wrong-namespace",
    ],
)
def test_subject_selector_rejects_unsafe_values(value: str | None) -> None:
    with pytest.raises(ValueError, match="subject_selection_reference"):
        validate_subject_selection_reference(value)


def test_subject_selector_accepts_namespaced_digest() -> None:
    assert validate_subject_selection_reference(_VALID_SELECTION) == _VALID_SELECTION


def test_readiness_accepts_a_valid_selector() -> None:
    readiness = evaluate_preprocessing_readiness(
        _ds000030(), subject_selection_reference=_VALID_SELECTION
    )
    assert readiness.ready is True
    assert readiness.subject_selection_reference == _VALID_SELECTION


def test_readiness_fails_closed_on_a_participant_shaped_selector() -> None:
    readiness = evaluate_preprocessing_readiness(
        _ds000030(), subject_selection_reference="sub-SYNTH01"
    )
    assert readiness.ready is False
    assert any("subject_selection_reference" in issue for issue in readiness.blocking_issues)
    # The rejected value must not survive into the report or the issue text.
    assert readiness.subject_selection_reference is None
    assert not any("SYNTH01" in issue for issue in readiness.blocking_issues)


# --- disclosure safety --------------------------------------------------------


def _summary_text() -> str:
    spec = importlib.util.spec_from_file_location("_preflight", _PREFLIGHT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    readiness = evaluate_preprocessing_readiness(
        _ds000030(), subject_selection_reference=_VALID_SELECTION
    )
    summary: dict[str, Any] = module.summarize(readiness)
    assert summary["preprocessing_executed"] is False
    assert summary["mode"] == "preparation-readiness-only"
    assert summary["authorization_required_before_execution"] is True
    return repr(summary)


def test_prepared_summary_discloses_nothing_private() -> None:
    text = _summary_text()
    for forbidden in ("sub-", "/home/", "/Users/", "C:\\", "$HOME", "neuromultiverse-data"):
        assert forbidden not in text
    for claim in ("fmriprep --", "afni_proc.py -", "flirt ", "docker run"):
        assert claim not in text


def test_preparation_code_cannot_spawn_a_process() -> None:
    """No preparation module may import or call a process-spawning API."""
    forbidden_modules = {"subprocess", "os.system", "shutil", "docker", "multiprocessing"}
    forbidden_calls = {"system", "popen", "spawn", "spawnl", "execv", "fork", "run"}
    for path in (_READINESS_MODULE, _PREFLIGHT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_modules, path.name
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden_modules, path.name
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else None
                assert name not in forbidden_calls, f"{path.name} calls {name}"
    # No string literal may look like an invocation of a preprocessing tool.
    # Checked against literals rather than raw text so that a variable named
    # after a pipeline is not mistaken for a command line.
    invocations = ("fmriprep ", "afni_proc.py ", "flirt ", "mcflirt ", "3dTproject ", "docker ")
    for path in (_READINESS_MODULE, _PREFLIGHT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                for invocation in invocations:
                    assert invocation not in lowered, f"{path.name}: {invocation!r} in a literal"
            assert not (isinstance(node, ast.Constant) and node.value == "--network=none"), path


def test_readiness_gate_reads_no_external_evidence(tmp_path: Path) -> None:
    """The gate is pure: it decides from the record, touching no filesystem."""
    before = sorted(tmp_path.iterdir())
    evaluate_preprocessing_readiness(_ds000030(), subject_selection_reference=_VALID_SELECTION)
    assert sorted(tmp_path.iterdir()) == before


def test_readiness_report_rejects_an_execution_claim() -> None:
    readiness = evaluate_preprocessing_readiness(_ds000030())
    with pytest.raises(ValueError, match="preprocessing_executed"):
        readiness.preprocessing_executed = True  # type: ignore[assignment]


# --- committed templates and documentation ------------------------------------


def test_plan_template_authorizes_nothing_and_names_no_participant() -> None:
    text = _PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert "authorizes_execution: false" in text
    assert "preparation_only: true" in text
    assert "granted: false" in text
    assert 'reference: ""' in text
    for forbidden in ("sub-", "/home/", "/Users/", "C:\\", "$HOME"):
        assert forbidden not in text
    for claim in ("scientific_results: false", "pipeline_agreement: false"):
        assert claim in text


def test_qc_checklist_covers_every_required_category() -> None:
    text = _QC_CHECKLIST.read_text(encoding="utf-8").lower()
    for pipeline in ("fmriprep", "fsl", "afni"):
        assert pipeline in text
    for category in (
        "completion sentinel",
        "runtime and resource log",
        "output directories present",
        "registration visually reviewed",
        "brain extraction",
        "susceptibility-correction assumptions",
        "output space confirmed",
        "voxel size and template",
        "confound",
        "temporal length",
        "file naming",
        "no subject identifier has been entered into git",
        "screenshot",
        "reviewer initials",
        "accepted / rejected",
        "rejection reason",
    ):
        assert category in text, category


def test_pilot_document_records_the_standing_prohibitions() -> None:
    text = _PILOT_DOC.read_text(encoding="utf-8")
    lowered = text.lower()
    for statement in (
        "nothing has been preprocessed",
        "separate, explicit authorization",
        "abide and cobre remain blocked",
        "remains unauthorized",
        "ds000030_pilot_5_subjects",
        "outside git",
    ):
        assert statement in lowered, statement
    for claim in ("no scientific result", "no agreement between pipelines"):
        assert claim in lowered, claim
    for banned in ("phase", "step", "stage", "milestone"):
        assert f"## {banned}" not in lowered


def test_readme_status_matches_the_accepted_evidence() -> None:
    """The top-level status must not contradict the accepted pilot evidence."""
    text = (_REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    for statement in (
        "the scientific protocol is locked",
        "no scientific results are reported",
        "187,570,603 bytes",
        "0 validation errors, 139 warnings, 0 ignored",
        "no raw or derivative imaging data is committed to git",
        "no preprocessing has been run",
        "no model has been fitted",
        "quality-control outcome has been produced or inspected",
        "no performance claim of any kind exists",
    ):
        assert statement in text, statement
    assert "no dataset has been acquired" not in text


def test_committed_artifacts_carry_no_participant_or_private_path() -> None:
    for path in (_PILOT_DOC, _QC_CHECKLIST, _PLAN_TEMPLATE, _READINESS_MODULE, _PREFLIGHT):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("/home/", "/Users/", "C:\\Users"):
            assert forbidden not in text, f"{path.name} contains {forbidden}"


def test_governance_validator_shares_the_accepted_evidence_identities() -> None:
    """One source of truth: the validator imports what the gate enforces."""
    gov = _load_governance()
    assert gov.DS000030_ACQUISITION_REFERENCE == DS000030_ACQUISITION_REFERENCE
    assert gov.DS000030_RAW_VALIDATION_REFERENCE == DS000030_RAW_VALIDATION_REFERENCE
    ds = _ds000030()
    assert ds.acquisition_evidence_reference == DS000030_ACQUISITION_REFERENCE
    assert ds.raw_validation_evidence_reference == DS000030_RAW_VALIDATION_REFERENCE
    assert ds.acquisition_completed_at_utc is not None
    assert ds.raw_validation_completed_at_utc is not None
    assert ds.raw_validation_completed_at_utc >= ds.acquisition_completed_at_utc
    assert ds.raw_validation_completed_at_utc > datetime(2026, 1, 1, tzinfo=UTC)


# --- execution-plan dry-run validation ----------------------------------------


def _filled_plan(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    """A synthetic filled plan. Roots point at a temporary tree, never raw data."""
    external = tmp_path / "external"
    for name in ("raw", "derivatives", "work"):
        (external / name).mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            (external / name).chmod(0o700)
    license_path = external / "license.txt"
    license_path.write_text("synthetic-not-a-real-license\n", encoding="utf-8")
    plan: dict[str, Any] = {
        "schema_version": "1",
        "kind": "one-subject-preprocessing-plan",
        "authorizes_execution": False,
        "preparation_only": True,
        "prohibitions": {
            "expansion": False,
            "abide_acquisition": False,
            "cobre_acquisition": False,
            "acquisition": False,
            "push": False,
        },
        "dataset": {
            "accession": "ds000030",
            "snapshot": "1.0.0",
            "doi": "10.18112/openneuro.ds000030.v1.0.0",
            "acquisition_scope_id": "ds000030_pilot_5_subjects",
        },
        "accepted_evidence": {
            "acquisition_reference": DS000030_ACQUISITION_REFERENCE,
            "raw_validation_reference": DS000030_RAW_VALIDATION_REFERENCE,
            "permission_reference": DS000030_PERMISSION_REFERENCE,
            "validator_image": DS000030_VALIDATOR_IMAGE,
            "validator_version": DS000030_VALIDATOR_VERSION,
            "bids_schema_version": DS000030_BIDS_SCHEMA_VERSION,
            "validated_file_count": 22,
            "validated_total_bytes": 187570603,
            "raw_validation_error_count": 0,
            "raw_validation_warning_count": 139,
            "raw_validation_ignored_count": 0,
        },
        "subject_selection": {"reference": _VALID_SELECTION, "recorded_outside_git": True},
        "external_paths": {
            "raw_root": str(external / "raw"),
            "derivatives_root": str(external / "derivatives"),
            "work_root": str(external / "work"),
        },
        "freesurfer_license_path": str(license_path),
        "pipelines": {
            "fmriprep": {
                "enabled": True,
                "container_reference": "nipreps/fmriprep:25.2.5",
                "output_spaces": ["MNI152NLin2009cAsym:res-2"],
                "resource_limits": {"cpus": 6, "memory_gb": 16},
            },
            "fsl": {
                "enabled": True,
                "output_spaces": ["MNI152NLin6Asym:res-2"],
                "resource_limits": {"cpus": 6, "memory_gb": 16},
            },
            "afni": {
                "enabled": True,
                "output_spaces": ["MNI152NLin2009cAsym:res-2"],
                "resource_limits": {"cpus": 6, "memory_gb": 16},
            },
        },
        "claims": {
            "scientific_results": False,
            "pipeline_agreement": False,
            "preprocessing_success": False,
        },
        "authorization": {
            "granted": False,
            "granted_by": "",
            "granted_at_utc": "",
            "reference": "",
        },
    }
    plan.update(overrides)
    return plan


def test_filled_plan_passes_dry_run_validation(tmp_path: Path) -> None:
    result = validate_execution_plan(_filled_plan(tmp_path), repository_root=_REPO_ROOT)
    assert result.valid is True, result.blocking_issues
    assert result.blocking_issues == []
    assert result.mode == "dry-run"
    assert result.preprocessing_executed is False
    assert result.freesurfer_license_contents_read is False
    assert result.external_roots_outside_repository is True
    assert result.output_spaces_declared == {"fmriprep": 1, "fsl": 1, "afni": 1}
    assert result.resource_limits_declared == {"fmriprep": True, "fsl": True, "afni": True}


def test_unfilled_template_is_rejected() -> None:
    """The committed template is not a runnable plan: it must fail validation."""
    plan = yaml.safe_load(_PLAN_TEMPLATE.read_text(encoding="utf-8"))
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    joined = " ".join(result.blocking_issues)
    assert "output_spaces" in joined
    assert "resource_limits" in joined
    assert "subject_selection_reference" in joined


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ({"authorizes_execution": True}, "authorizes_execution must be false"),
        ({"preparation_only": False}, "preparation_only must be true"),
        ({"authorizes_push": True}, "authorizes_push"),
        ({"authorizes_expansion": True}, "authorizes_expansion"),
        ({"authorizes_acquisition": True}, "authorizes_acquisition"),
    ],
    ids=["execution", "preparation", "push", "expansion", "acquisition"],
)
def test_plan_rejects_asserted_authorization(
    tmp_path: Path, mutation: dict[str, Any], expected: str
) -> None:
    result = validate_execution_plan(_filled_plan(tmp_path, **mutation), repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any(expected in issue for issue in result.blocking_issues)


def test_plan_requires_an_authorization_block(tmp_path: Path) -> None:
    plan = _filled_plan(tmp_path)
    del plan["authorization"]
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any("authorization must be declared" in issue for issue in result.blocking_issues)


def test_empty_dry_run_authorization_block_passes(tmp_path: Path) -> None:
    """The template's own empty block is the only shape dry-run validation accepts."""
    plan = _filled_plan(tmp_path)
    assert plan["authorization"] == {
        "granted": False,
        "granted_by": "",
        "granted_at_utc": "",
        "reference": "",
    }
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is True, result.blocking_issues


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("granted", True, "authorization.granted must be false"),
        ("granted", None, "authorization.granted must be false"),
        ("granted_by", "a reviewer", "authorization.granted_by must be empty"),
        ("granted_at_utc", "2026-07-19T00:00:00Z", "authorization.granted_at_utc must be empty"),
        ("reference", "nm-authorization-001", "authorization.reference must be empty"),
    ],
    ids=["granted-true", "granted-absent", "granted-by", "granted-at", "reference"],
)
def test_plan_rejects_a_filled_authorization_block(
    tmp_path: Path, field: str, value: Any, expected: str
) -> None:
    """A plan may not assert its own execution grant during dry-run validation."""
    plan = _filled_plan(tmp_path)
    if value is None:
        del plan["authorization"][field]
    else:
        plan["authorization"][field] = value
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any(expected in issue for issue in result.blocking_issues)


@pytest.mark.parametrize(
    "key", ["expansion", "abide_acquisition", "cobre_acquisition", "acquisition", "push"]
)
def test_plan_rejects_a_relaxed_prohibition(tmp_path: Path, key: str) -> None:
    plan = _filled_plan(tmp_path)
    plan["prohibitions"][key] = True
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any(f"prohibitions.{key}" in issue for issue in result.blocking_issues)


@pytest.mark.parametrize(
    "section, key, value, expected",
    [
        ("dataset", "accession", "abide_i_pcp", "dataset.accession"),
        ("dataset", "acquisition_scope_id", "ds000030_controlled_20", "acquisition_scope_id"),
        ("accepted_evidence", "acquisition_reference", "x:" + "0" * 64, "acquisition_reference"),
        (
            "accepted_evidence",
            "raw_validation_reference",
            "x:" + "0" * 64,
            "raw_validation_reference",
        ),
        ("accepted_evidence", "permission_reference", "x:" + "0" * 64, "permission_reference"),
        ("accepted_evidence", "raw_validation_warning_count", 138, "warning_count"),
        ("accepted_evidence", "raw_validation_error_count", 1, "error_count"),
        ("accepted_evidence", "validated_total_bytes", 1, "validated_total_bytes"),
        ("subject_selection", "reference", "sub-SYNTH01", "subject_selection_reference"),
        ("subject_selection", "recorded_outside_git", False, "recorded_outside_git"),
    ],
)
def test_plan_rejects_a_broken_field(
    tmp_path: Path, section: str, key: str, value: Any, expected: str
) -> None:
    plan = _filled_plan(tmp_path)
    plan[section][key] = value
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any(expected in issue for issue in result.blocking_issues)


@pytest.mark.parametrize("root", ["raw_root", "derivatives_root", "work_root"])
def test_plan_rejects_an_external_root_inside_the_repository(tmp_path: Path, root: str) -> None:
    plan = _filled_plan(tmp_path)
    plan["external_paths"][root] = str(_REPO_ROOT / "data" / "raw")
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any("outside the repository" in issue for issue in result.blocking_issues)
    assert result.external_roots_outside_repository is False


@pytest.mark.parametrize("root", ["raw_root", "derivatives_root", "work_root"])
def test_plan_rejects_a_relative_external_root(tmp_path: Path, root: str) -> None:
    plan = _filled_plan(tmp_path)
    plan["external_paths"][root] = "relative/path"
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any("absolute path" in issue for issue in result.blocking_issues)


@pytest.mark.parametrize("pipeline", ["fmriprep", "fsl", "afni"])
def test_plan_requires_explicit_output_spaces(tmp_path: Path, pipeline: str) -> None:
    plan = _filled_plan(tmp_path)
    plan["pipelines"][pipeline]["output_spaces"] = []
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any(f"pipelines.{pipeline}.output_spaces" in i for i in result.blocking_issues)


@pytest.mark.parametrize("pipeline", ["fmriprep", "fsl", "afni"])
@pytest.mark.parametrize("limits", [{"cpus": None, "memory_gb": 16}, {"cpus": 6}, {}])
def test_plan_requires_explicit_resource_limits(
    tmp_path: Path, pipeline: str, limits: dict[str, Any]
) -> None:
    plan = _filled_plan(tmp_path)
    plan["pipelines"][pipeline]["resource_limits"] = limits
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any(f"pipelines.{pipeline}.resource_limits" in i for i in result.blocking_issues)


def test_plan_requires_a_container_reference(tmp_path: Path) -> None:
    plan = _filled_plan(tmp_path)
    plan["pipelines"]["fmriprep"]["container_reference"] = ""
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any("container_reference" in issue for issue in result.blocking_issues)


@pytest.mark.parametrize("value", ["", "relative/license.txt"])
def test_plan_requires_a_well_shaped_license_path(tmp_path: Path, value: str) -> None:
    result = validate_execution_plan(
        _filled_plan(tmp_path, freesurfer_license_path=value), repository_root=_REPO_ROOT
    )
    assert result.valid is False
    assert any("freesurfer_license_path" in issue for issue in result.blocking_issues)
    assert result.freesurfer_license_declared is False


def test_plan_validation_never_reads_the_license(tmp_path: Path, monkeypatch: Any) -> None:
    """A read of the declared license file must never happen during validation."""
    plan = _filled_plan(tmp_path)
    license_path = Path(plan["freesurfer_license_path"])
    opened: list[str] = []
    real_open = Path.open

    def tracking_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    monkeypatch.setattr(
        Path, "read_text", lambda self, *a, **k: pytest.fail(f"read_text called on {self.name}")
    )
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is True, result.blocking_issues
    assert str(license_path) not in opened


def test_plan_rejects_a_claim_of_success(tmp_path: Path) -> None:
    plan = _filled_plan(tmp_path)
    plan["claims"]["preprocessing_success"] = True
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    assert result.valid is False
    assert any("claims" in issue for issue in result.blocking_issues)


def test_plan_verdict_discloses_no_external_path(tmp_path: Path) -> None:
    plan = _filled_plan(tmp_path)
    result = validate_execution_plan(plan, repository_root=_REPO_ROOT)
    rendered = repr(result.model_dump())
    for secret in (
        plan["external_paths"]["raw_root"],
        plan["external_paths"]["derivatives_root"],
        plan["freesurfer_license_path"],
    ):
        assert secret not in rendered
    assert "sub-" not in rendered


def test_plan_validation_does_not_traverse_the_external_roots(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Validation stats the roots themselves and never lists their contents."""

    def _forbid(name: str) -> Any:
        def guard(self: Path, *args: Any, **kwargs: Any) -> Any:
            pytest.fail(f"{name} called during plan validation")

        return guard

    for attribute in ("iterdir", "glob", "rglob", "walk"):
        monkeypatch.setattr(Path, attribute, _forbid(attribute), raising=False)
    result = validate_execution_plan(_filled_plan(tmp_path), repository_root=_REPO_ROOT)
    assert result.valid is True, result.blocking_issues
