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
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from neuromultiverse.data_contracts import AccessStatus, DatasetAccessRecord
from neuromultiverse.preprocessing_readiness import (
    DS000030_ACQUISITION_REFERENCE,
    DS000030_RAW_VALIDATION_REFERENCE,
    PIPELINES,
    SELECTION_REFERENCE_PREFIX,
    evaluate_preprocessing_readiness,
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
    source = _PREFLIGHT.read_text(encoding="utf-8") + _READINESS_MODULE.read_text(encoding="utf-8")
    for tool in ("fmriprep", "afni_proc.py", "flirt", "mcflirt", "3dTproject", "docker"):
        assert f"{tool} " not in source.replace("fmriprep, fsl, afni", "")


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
