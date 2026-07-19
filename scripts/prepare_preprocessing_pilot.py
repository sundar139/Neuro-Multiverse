#!/usr/bin/env python
"""Deterministic preflight for the future one-subject ds000030 preprocessing pilot.

This command decides readiness and prints an aggregate, disclosure-safe summary.
It runs no pipeline: it imports no process-spawning module, opens no raw file,
resolves no raw path, and learns no participant identifier. Running it can never
start fMRIPrep, FSL, AFNI, or a container.

The governance record it evaluates is the committed one in
``scripts/verify_data_governance.py``; readiness is recomputed from the accepted
evidence identities in :mod:`neuromultiverse.preprocessing_readiness` rather than
inferred from that record's own construction, so drift fails closed.

Exit codes: ``0`` when the later pilot may be prepared, ``1`` when it may not.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from neuromultiverse.data_contracts import DatasetAccessRecord  # noqa: E402
from neuromultiverse.ds000030_pilot import DS000030_ACCESSION  # noqa: E402
from neuromultiverse.preprocessing_readiness import (  # noqa: E402
    PIPELINES,
    SELECTION_REFERENCE_PREFIX,
    PlanValidation,
    PreprocessingReadiness,
    evaluate_preprocessing_readiness,
    validate_execution_plan,
)

GOVERNANCE_VALIDATOR = REPO_ROOT / "scripts" / "verify_data_governance.py"


def _governance_records() -> list[DatasetAccessRecord]:
    """Load the committed governance records without running the validator's main."""
    spec = importlib.util.spec_from_file_location("_governance", GOVERNANCE_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("the governance validator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records: list[DatasetAccessRecord] = module.required_records()
    return records


def _record_for(dataset_id: str) -> DatasetAccessRecord:
    for record in _governance_records():
        if record.dataset_id == dataset_id:
            return record
    raise SystemExit(f"no governance record exists for {dataset_id}")


def summarize(readiness: PreprocessingReadiness) -> dict[str, Any]:
    """The printable summary. Aggregate only; nothing here identifies a person."""
    return {
        "mode": "preparation-readiness-only",
        "preprocessing_executed": readiness.preprocessing_executed,
        "ready_to_prepare": readiness.ready,
        "dataset_id": readiness.dataset_id,
        "acquisition_scope_id": readiness.acquisition_scope_id,
        "acquisition_evidence_reference": readiness.acquisition_evidence_reference,
        "raw_validation_evidence_reference": readiness.raw_validation_evidence_reference,
        "permission_evidence_reference": readiness.permission_evidence_reference,
        "validator_image": readiness.validator_image,
        "validator_version": readiness.validator_version,
        "bids_schema_version": readiness.bids_schema_version,
        "validated_file_count": readiness.validated_file_count,
        "validated_total_bytes": readiness.validated_total_bytes,
        "raw_validation_error_count": readiness.raw_validation_error_count,
        "raw_validation_warning_count": readiness.raw_validation_warning_count,
        "raw_validation_ignored_count": readiness.raw_validation_ignored_count,
        "subject_selection_reference": readiness.subject_selection_reference,
        "pipelines_to_compare": list(readiness.pipelines),
        "authorization_required_before_execution": True,
        "blocking_issues": readiness.blocking_issues,
    }


def _load_plan(path: Path) -> dict[str, Any]:
    """Parse the external plan. Only this one file is read."""
    if not path.is_file():
        raise SystemExit("the execution plan is not a readable file at the supplied location")
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise SystemExit("the execution plan must parse to a mapping")
    return parsed


def summarize_plan(validation: PlanValidation) -> dict[str, Any]:
    """The printable plan verdict. Paths appear only as booleans."""
    return {
        "mode": validation.mode,
        "preprocessing_executed": validation.preprocessing_executed,
        "plan_valid": validation.valid,
        "dataset_accession": validation.dataset_accession,
        "acquisition_scope_id": validation.acquisition_scope_id,
        "subject_selection_reference": validation.subject_selection_reference,
        "external_roots_outside_repository": validation.external_roots_outside_repository,
        "output_spaces_declared": validation.output_spaces_declared,
        "resource_limits_declared": validation.resource_limits_declared,
        "freesurfer_license_declared": validation.freesurfer_license_declared,
        "freesurfer_license_contents_read": validation.freesurfer_license_contents_read,
        "fmriprep_container_declared": validation.fmriprep_container_declared,
        "advisories": validation.advisories,
        "blocking_issues": validation.blocking_issues,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--dataset-id",
        default=DS000030_ACCESSION,
        help="governance record to evaluate (only the ds000030 pilot can be ready)",
    )
    result.add_argument(
        "--subject-selection-reference",
        default=None,
        help=(
            "optional opaque external selection reference "
            f"({SELECTION_REFERENCE_PREFIX}<64 lowercase hex>); never a participant identifier"
        ),
    )
    result.add_argument(
        "--expansion-authorized",
        action="store_true",
        help="assert the broader controlled subset is authorized (it is not; this must fail)",
    )
    result.add_argument(
        "--plan",
        type=Path,
        default=None,
        help=(
            "path to a filled execution plan outside the repository; validates it in dry-run "
            "mode. No pipeline, container, or raw file is touched either way."
        ),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    readiness = evaluate_preprocessing_readiness(
        _record_for(args.dataset_id),
        subject_selection_reference=args.subject_selection_reference,
        expansion_authorized=args.expansion_authorized,
    )
    print(json.dumps(summarize(readiness), indent=2, sort_keys=True))
    if not readiness.ready:
        print(
            "RESULT: NOT READY — the one-subject pilot cannot be prepared "
            f"({len(readiness.blocking_issues)} blocking issue(s))"
        )
        return 1

    if args.plan is not None:
        validation = validate_execution_plan(
            _load_plan(args.plan), repository_root=REPO_ROOT, mode="dry-run"
        )
        print(json.dumps(summarize_plan(validation), indent=2, sort_keys=True))
        if not validation.valid:
            print(
                "RESULT: PLAN REJECTED — dry-run validation failed "
                f"({len(validation.blocking_issues)} blocking issue(s)). Nothing was executed."
            )
            return 1
        print(
            "RESULT: PLAN VALID (DRY RUN) — no preprocessing was run. "
            f"Execution across {', '.join(PIPELINES)} still requires separate explicit "
            "authorization."
        )
        return 0

    print(
        "RESULT: READY TO PREPARE — no preprocessing was run. "
        f"Execution across {', '.join(PIPELINES)} still requires separate explicit authorization."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
