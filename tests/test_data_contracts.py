"""Tests for the typed data-governance contracts.

Every fixture uses obviously synthetic values. No value here resembles a real
provider-issued participant identifier: subject ids carry a ``SYNTH-`` prefix
and are asserted against known real-identifier shapes in
``test_no_fixture_resembles_real_participant_id``.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from neuromultiverse.data_contracts import (
    SUBJECT_MANIFEST_COLUMNS,
    AccessStatus,
    AcquisitionEvent,
    DatasetAccessRecord,
    DatasetRole,
    SubjectManifest,
    SubjectManifestRecord,
)

_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "data" / "manifests" / "subject_manifest.template.tsv"
)


def _access_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dataset_id": "synthetic_dataset",
        "dataset_name": "Synthetic Dataset",
        "role": DatasetRole.REPLICATION,
        "provider": "Synthetic Provider",
        "authoritative_sources": ["https://example.org/synthetic"],
        "version": "1.0.0",
        "license_id": "CC0",
        "access_status": AccessStatus.READY,
        "registration_required": False,
        "approval_required": False,
        "redistribution_allowed": True,
        "commercial_use_allowed": True,
        "reidentification_prohibited": True,
        "expected_size_bytes": 1024,
        "expected_size_source": "provider metadata API",
        "verification_date": date(2026, 7, 17),
        "citation_ids": ["synthetic-cite"],
        "target_root": "$HOME/neuromultiverse-data/synthetic",
        "hash_algorithm": "sha256",
        "acquisition_permitted": False,
    }
    base.update(overrides)
    return base


def _subject_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dataset": "synthetic_dataset",
        "subject_id": "SYNTH-0001",
        "session_id": None,
        "site": "SYNTH_SITE",
        "diagnosis": "control",
        "age": 30.0,
        "sex": "F",
        "raw_t1w_path": "synthetic/sub-SYNTH0001/anat/t1w.nii.gz",
        "raw_bold_path": "synthetic/sub-SYNTH0001/func/bold.nii.gz",
        "pipeline_availability": "ccs,cpac",
        "included": True,
        "exclusion_reason": None,
        "raw_file_checksum": None,
        "manifest_version": "v0",
    }
    base.update(overrides)
    return base


def _event_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dataset_id": "synthetic_dataset",
        "version": "1.0.0",
        "started_at": datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 7, 17, 12, 5, 0, tzinfo=UTC),
        "source": "https://example.org/synthetic",
        "target_root": "$HOME/neuromultiverse-data/synthetic",
        "file_count": 3,
        "total_bytes": 4096,
        "hash_manifest": "$HOME/neuromultiverse-data/synthetic/hashes.sha256",
        "git_commit": "dc96c76",
        "tool_version": "0.1.0",
        "status": "completed",
        "error_category": None,
    }
    base.update(overrides)
    return base


def test_valid_records_construct() -> None:
    assert DatasetAccessRecord(**_access_kwargs()).access_status is AccessStatus.READY
    assert SubjectManifestRecord(**_subject_kwargs()).included is True
    assert AcquisitionEvent(**_event_kwargs()).status == "completed"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        DatasetAccessRecord(**_access_kwargs(surprise="x"))


def test_invalid_access_status_rejected() -> None:
    with pytest.raises(ValidationError):
        DatasetAccessRecord(**_access_kwargs(access_status="OPEN"))


def test_acquisition_cannot_be_permitted_while_pending() -> None:
    with pytest.raises(ValidationError, match="access_status is READY"):
        DatasetAccessRecord(
            **_access_kwargs(
                access_status=AccessStatus.AUTHORIZATION_PENDING,
                acquisition_permitted=True,
            )
        )


def test_permitted_requires_verified_size() -> None:
    with pytest.raises(ValidationError, match="expected_size_bytes"):
        DatasetAccessRecord(**_access_kwargs(acquisition_permitted=True, expected_size_bytes=None))


def test_permitted_ready_with_size_is_allowed() -> None:
    record = DatasetAccessRecord(**_access_kwargs(acquisition_permitted=True))
    assert record.acquisition_permitted is True


def test_negative_size_fails() -> None:
    with pytest.raises(ValidationError):
        DatasetAccessRecord(**_access_kwargs(expected_size_bytes=-1))


def test_negative_counts_fail() -> None:
    with pytest.raises(ValidationError):
        AcquisitionEvent(**_event_kwargs(file_count=-1))
    with pytest.raises(ValidationError):
        AcquisitionEvent(**_event_kwargs(total_bytes=-5))


def test_naive_timestamp_fails() -> None:
    with pytest.raises(ValidationError):
        AcquisitionEvent(**_event_kwargs(started_at=datetime(2026, 7, 17, 12, 0, 0)))


def test_unsupported_hash_algorithm_fails() -> None:
    with pytest.raises(ValidationError):
        DatasetAccessRecord(**_access_kwargs(hash_algorithm="md5"))


def test_absolute_home_path_rejected() -> None:
    with pytest.raises(ValidationError, match="portable"):
        DatasetAccessRecord(**_access_kwargs(target_root="/home/someone/data"))
    with pytest.raises(ValidationError, match="portable"):
        DatasetAccessRecord(**_access_kwargs(target_root=r"C:\Users\someone\data"))


def test_included_false_requires_exclusion_reason() -> None:
    with pytest.raises(ValidationError, match="exclusion_reason"):
        SubjectManifestRecord(**_subject_kwargs(included=False, exclusion_reason=None))


def test_included_true_rejects_unexplained_exclusion_reason() -> None:
    with pytest.raises(ValidationError, match="must not carry an exclusion_reason"):
        SubjectManifestRecord(**_subject_kwargs(included=True, exclusion_reason="motion"))


def test_excluded_subject_with_reason_is_valid() -> None:
    record = SubjectManifestRecord(
        **_subject_kwargs(included=False, exclusion_reason="excess motion")
    )
    assert record.included is False


def test_bad_checksum_rejected() -> None:
    with pytest.raises(ValidationError, match="checksum"):
        SubjectManifestRecord(**_subject_kwargs(raw_file_checksum="not-a-hash"))


def test_valid_sha256_checksum_accepted() -> None:
    record = SubjectManifestRecord(**_subject_kwargs(raw_file_checksum="a" * 64))
    assert record.raw_file_checksum == "a" * 64


def test_duplicate_subject_keys_detected() -> None:
    rows = [SubjectManifestRecord(**_subject_kwargs()), SubjectManifestRecord(**_subject_kwargs())]
    with pytest.raises(ValidationError, match="duplicate subject key"):
        SubjectManifest(records=rows)


def test_duplicate_raw_paths_detected() -> None:
    rows = [
        SubjectManifestRecord(**_subject_kwargs(subject_id="SYNTH-0001")),
        SubjectManifestRecord(
            **_subject_kwargs(
                subject_id="SYNTH-0002",
                raw_bold_path="synthetic/sub-SYNTH0001/func/bold.nii.gz",
            )
        ),
    ]
    with pytest.raises(ValidationError, match="duplicate raw path"):
        SubjectManifest(records=rows)


def test_duplicate_checksums_flagged_not_fatal() -> None:
    shared = "b" * 64
    rows = [
        SubjectManifestRecord(
            **_subject_kwargs(
                subject_id="SYNTH-0001",
                raw_t1w_path="synthetic/a1.nii.gz",
                raw_bold_path="synthetic/a2.nii.gz",
                raw_file_checksum=shared,
            )
        ),
        SubjectManifestRecord(
            **_subject_kwargs(
                subject_id="SYNTH-0002",
                raw_t1w_path="synthetic/b1.nii.gz",
                raw_bold_path="synthetic/b2.nii.gz",
                raw_file_checksum=shared,
            )
        ),
    ]
    manifest = SubjectManifest(records=rows)  # does not raise
    flagged = manifest.duplicate_checksums()
    assert shared in flagged
    assert len(flagged[shared]) == 2


def test_failed_event_requires_error_category() -> None:
    with pytest.raises(ValidationError, match="error_category"):
        AcquisitionEvent(**_event_kwargs(status="failed", completed_at=None, error_category=None))


def test_completed_before_started_rejected() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        AcquisitionEvent(
            **_event_kwargs(
                started_at=datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC),
                completed_at=datetime(2026, 7, 17, 11, 0, 0, tzinfo=UTC),
            )
        )


def test_template_matches_model_column_order() -> None:
    header = _TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
    assert tuple(header.split("\t")) == SUBJECT_MANIFEST_COLUMNS


def test_template_is_header_only() -> None:
    lines = [ln for ln in _TEMPLATE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1, "the manifest template must contain headers only, no data rows"


def test_no_fixture_resembles_real_participant_id() -> None:
    """Synthetic ids must not match known real provider-id shapes."""
    real_shapes = [
        re.compile(r"^\d{7}$"),  # ABIDE / COBRE numeric FILE_ID
        re.compile(r"^sub-\d{5}$"),  # ds000030 BIDS subject label
    ]
    for subject_id in ("SYNTH-0001", "SYNTH-0002"):
        assert subject_id.startswith("SYNTH-")
        assert not any(shape.match(subject_id) for shape in real_shapes)
