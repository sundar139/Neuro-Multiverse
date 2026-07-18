"""Tests for the hardened ds000030 pilot acquisition executor and schema.

Synthetic values only: subject ids use a ``sub-SYNTH`` prefix and never match a
real five-digit ds000030 label. No test performs a network body request; the
integrity primitives are exercised with local fixtures. Where a test needs the
executor's committed evidence constants to match a synthetic plan, they are
monkeypatched on the loaded module.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from neuromultiverse.ds000030_pilot import (
    PilotAcquisitionPlan,
    PilotApprovalRecord,
    PilotFileEntry,
)

_TOOL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "acquire_ds000030_pilot.py"
_SUBJECTS = ["sub-SYNTHA", "sub-SYNTHB", "sub-SYNTHC", "sub-SYNTHD", "sub-SYNTHE"]


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("acquire_ds000030_pilot", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


# --- Plan fixtures ----------------------------------------------------------
def _entry(
    subject: str | None, role: str, rel: str, path: str, oid: str, size: int
) -> dict[str, Any]:
    return {
        "provider_path": path,
        "provider_object_id": oid,
        "local_relative_target": rel,
        "file_role": role,
        "subject": subject,
        "provider_size_bytes": size,
        "provider_checksum": None,
        "provider_checksum_algorithm": None,
        "provider_checksum_suitable_for_content_integrity": False,
    }


def _valid_plan_dict() -> dict[str, Any]:
    files: list[dict[str, Any]] = [
        _entry(
            None,
            "dataset_metadata",
            "dataset_description.json",
            "dataset_description.json",
            "o0",
            100,
        ),
        _entry(None, "dataset_metadata", "task-rest_bold.json", "task-rest_bold.json", "o1", 200),
    ]
    size = 1000
    for i, sid in enumerate(_SUBJECTS):
        files.append(
            _entry(
                sid,
                "t1w_image",
                f"{sid}/anat/{sid}_T1w.nii.gz",
                f"{sid}/anat/{sid}_T1w.nii.gz",
                f"a{i}",
                size,
            )
        )
        files.append(
            _entry(
                sid,
                "t1w_sidecar",
                f"{sid}/anat/{sid}_T1w.json",
                f"{sid}/anat/{sid}_T1w.json",
                f"b{i}",
                10,
            )
        )
        files.append(
            _entry(
                sid,
                "rest_bold_image",
                f"{sid}/func/{sid}_task-rest_bold.nii.gz",
                f"{sid}/func/{sid}_task-rest_bold.nii.gz",
                f"c{i}",
                size,
            )
        )
        files.append(
            _entry(
                sid,
                "rest_bold_sidecar",
                f"{sid}/func/{sid}_task-rest_bold.json",
                f"{sid}/func/{sid}_task-rest_bold.json",
                f"d{i}",
                10,
            )
        )
    total = sum(f["provider_size_bytes"] for f in files)
    return {
        "schema_version": "2",
        "dataset_accession": "ds000030",
        "snapshot": "1.0.0",
        "doi": "10.18112/openneuro.ds000030.v1.0.0",
        "acquisition_scope_id": "ds000030_pilot_5_subjects",
        "base_seed": "20260717",
        "selection_algorithm_version": "pilot-selection-v1",
        "selected_subject_count": 5,
        "selected_subject_ids": list(_SUBJECTS),
        "files": files,
        "expected_file_count": len(files),
        "expected_transfer_bytes": total,
        "created_at_utc": "2026-07-18T00:00:00Z",
        "starting_git_commit": "0" * 40,
        "metadata_endpoint": "https://openneuro.org/crn/graphql",
        "no_download_assertion": "metadata only",
    }


# --- Schema: subject/file completeness --------------------------------------
def test_valid_plan_model_accepts() -> None:
    assert PilotAcquisitionPlan.model_validate(_valid_plan_dict()).expected_file_count == 22


def test_files_for_only_two_subjects_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"] = [f for f in plan["files"] if f["subject"] in (None, "sub-SYNTHA", "sub-SYNTHB")]
    plan["expected_file_count"] = len(plan["files"])
    plan["expected_transfer_bytes"] = sum(f["provider_size_bytes"] for f in plan["files"])
    with pytest.raises(ValidationError):
        PilotAcquisitionPlan.model_validate(plan)


def test_duplicate_selected_ids_rejected() -> None:
    plan = _valid_plan_dict()
    plan["selected_subject_ids"][1] = "sub-SYNTHA"
    with pytest.raises(ValidationError, match="unique"):
        PilotAcquisitionPlan.model_validate(plan)


def test_missing_t1w_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"] = [
        f
        for f in plan["files"]
        if not (f["subject"] == "sub-SYNTHA" and f["file_role"] == "t1w_image")
    ]
    plan["expected_file_count"] = len(plan["files"])
    plan["expected_transfer_bytes"] = sum(f["provider_size_bytes"] for f in plan["files"])
    with pytest.raises(ValidationError, match="T1w"):
        PilotAcquisitionPlan.model_validate(plan)


def test_missing_bold_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"] = [
        f
        for f in plan["files"]
        if not (f["subject"] == "sub-SYNTHB" and f["file_role"] == "rest_bold_image")
    ]
    plan["expected_file_count"] = len(plan["files"])
    plan["expected_transfer_bytes"] = sum(f["provider_size_bytes"] for f in plan["files"])
    with pytest.raises(ValidationError, match="BOLD"):
        PilotAcquisitionPlan.model_validate(plan)


def test_unselected_subject_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"].append(
        _entry("sub-SYNTHZ", "t1w_image", "sub-SYNTHZ/anat/x_T1w.nii.gz", "p", "z1", 5)
    )
    plan["expected_file_count"] = len(plan["files"])
    plan["expected_transfer_bytes"] = sum(f["provider_size_bytes"] for f in plan["files"])
    with pytest.raises(ValidationError, match="unselected"):
        PilotAcquisitionPlan.model_validate(plan)


def test_file_count_mismatch_rejected() -> None:
    plan = _valid_plan_dict()
    plan["expected_file_count"] = 21
    with pytest.raises(ValidationError, match="expected_file_count"):
        PilotAcquisitionPlan.model_validate(plan)


def test_byte_mismatch_rejected() -> None:
    plan = _valid_plan_dict()
    plan["expected_transfer_bytes"] += 1
    with pytest.raises(ValidationError, match="expected_transfer_bytes"):
        PilotAcquisitionPlan.model_validate(plan)


def test_zero_and_negative_sizes_rejected() -> None:
    for bad in (0, -5):
        plan = _valid_plan_dict()
        plan["files"][2]["provider_size_bytes"] = bad
        with pytest.raises(ValidationError):
            PilotAcquisitionPlan.model_validate(plan)


def test_unknown_role_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"][2]["file_role"] = "dwi_image"
    with pytest.raises(ValidationError):
        PilotAcquisitionPlan.model_validate(plan)


def test_duplicate_provider_path_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"][3]["provider_path"] = plan["files"][2]["provider_path"]
    with pytest.raises(ValidationError, match="provider_path"):
        PilotAcquisitionPlan.model_validate(plan)


def test_duplicate_object_id_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"][3]["provider_object_id"] = plan["files"][2]["provider_object_id"]
    with pytest.raises(ValidationError, match="provider_object_id"):
        PilotAcquisitionPlan.model_validate(plan)


def test_url_field_rejected_by_schema() -> None:
    plan = _valid_plan_dict()
    plan["files"][2]["provider_download_url"] = "https://openneuro.org/x?versionId=abc"
    with pytest.raises(ValidationError):
        PilotAcquisitionPlan.model_validate(plan)


def test_traversal_target_rejected() -> None:
    with pytest.raises(ValidationError):
        PilotFileEntry.model_validate(
            _entry("sub-SYNTHA", "t1w_image", "../escape.nii.gz", "p", "id", 5)
        )


def test_participant_and_events_files_rejected() -> None:
    for bad in ("participants.tsv", "sub-SYNTHA/func/sub-SYNTHA_task-rest_events.tsv"):
        with pytest.raises(ValidationError):
            PilotFileEntry.model_validate(_entry(None, "dataset_metadata", bad, bad, "id", 5))


# --- URL safety -------------------------------------------------------------
def test_validate_url_accepts_trusted_https() -> None:
    tool.validate_url("https://openneuro.org/crn/x", tool._ALLOWED_OBJECT_HOSTS)
    tool.validate_url("https://s3.amazonaws.com/openneuro.org/x", tool._ALLOWED_OBJECT_HOSTS)


@pytest.mark.parametrize(
    "url",
    [
        "http://openneuro.org/x",
        "ftp://openneuro.org/x",
        "file:///etc/passwd",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://10.0.0.1/x",
        "https://169.254.1.1/x",
        "https://evil.example.com/x",
    ],
)
def test_validate_url_rejects_unsafe(url: str) -> None:
    with pytest.raises(ValueError):
        tool.validate_url(url, tool._ALLOWED_OBJECT_HOSTS)


def test_redirect_to_untrusted_host_rejected() -> None:
    handler = tool.SafeRedirectHandler()
    with pytest.raises(ValueError):
        handler.validate_redirect("https://evil.example.com/x")
    assert handler.validate_redirect("https://s3.amazonaws.com/openneuro.org/x")


def test_resolve_download_url_fails_closed_on_ambiguous() -> None:
    def fetcher(_oid: str, _path: str) -> list[dict[str, Any]]:
        return []

    with pytest.raises(ValueError, match="exactly one"):
        tool.resolve_download_url("oid", "path", 10, fetcher)


def test_resolve_download_url_single_trusted_match() -> None:
    def fetcher(_oid: str, _path: str) -> list[dict[str, Any]]:
        return [
            {
                "provider_object_id": "oid",
                "provider_path": "path",
                "provider_size_bytes": 10,
                "url": "https://s3.amazonaws.com/openneuro.org/x",
            }
        ]

    assert tool.resolve_download_url("oid", "path", 10, fetcher).startswith("https://")


def test_resolve_download_url_rejects_untrusted_host() -> None:
    def fetcher(_oid: str, _path: str) -> list[dict[str, Any]]:
        return [
            {
                "provider_object_id": "oid",
                "provider_path": "path",
                "provider_size_bytes": 10,
                "url": "https://evil.example.com/x",
            }
        ]

    with pytest.raises(ValueError):
        tool.resolve_download_url("oid", "path", 10, fetcher)


# --- Approval and dry-run gating --------------------------------------------
def test_no_approved_flag_exists() -> None:
    with pytest.raises(SystemExit):
        tool.main(["--plan", "x", "--target-root", "y", "--approved"])


def _sync_constants(monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any]) -> str:
    digest = str(tool.canonical_plan_digest(plan))
    monkeypatch.setattr(tool, "DS000030_PLAN_CANONICAL_SHA256", digest)
    monkeypatch.setattr(tool, "DS000030_PILOT_FILE_COUNT", plan["expected_file_count"])
    monkeypatch.setattr(tool, "DS000030_PILOT_EXPECTED_BYTES", plan["expected_transfer_bytes"])
    monkeypatch.setattr(
        tool, "DS000030_PILOT_PLAN_REFERENCE", f"ds000030-pilot-plan-sha256:{digest}"
    )
    monkeypatch.setattr(tool, "DS000030_STORAGE_REFERENCE", "storage-readiness-sha256:abc")
    return digest


def _approval(digest: str, plan: dict[str, Any], **over: Any) -> dict[str, Any]:
    base = {
        "schema_version": "1",
        "decision": "approved",
        "dataset_accession": "ds000030",
        "acquisition_scope_id": "ds000030_pilot_5_subjects",
        "snapshot": "1.0.0",
        "doi": "10.18112/openneuro.ds000030.v1.0.0",
        "canonical_plan_sha256": digest,
        "expected_file_count": plan["expected_file_count"],
        "expected_transfer_bytes": plan["expected_transfer_bytes"],
        "size_evidence_reference": f"ds000030-pilot-plan-sha256:{digest}",
        "storage_evidence_reference": "storage-readiness-sha256:abc",
        "approved_code_commit": "HEAD",
        "approval_timestamp_utc": "2026-07-18T00:00:00Z",
        "approval_id": "appr-1",
        "reviewer_role": "study-lead",
    }
    base.update(over)
    return base


def test_approval_problems_clean_for_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    digest = _sync_constants(monkeypatch, plan)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan))
    assert tool.approval_problems(plan, approval) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("canonical_plan_sha256", "0" * 64),
        ("expected_file_count", 21),
        ("expected_transfer_bytes", 1),
        ("storage_evidence_reference", "storage-readiness-sha256:zzz"),
    ],
)
def test_approval_mismatch_blocks(monkeypatch: pytest.MonkeyPatch, field: str, value: Any) -> None:
    plan = _valid_plan_dict()
    digest = _sync_constants(monkeypatch, plan)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan, **{field: value}))
    assert tool.approval_problems(plan, approval) != []


def test_not_approved_record_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    digest = _sync_constants(monkeypatch, plan)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan, decision="not_approved"))
    assert any("not 'approved'" in p for p in tool.approval_problems(plan, approval))


def test_dry_run_returns_zero_when_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    _sync_constants(monkeypatch, plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])
    assert rc == 0


def test_dry_run_returns_nonzero_on_precondition_failure(tmp_path: Path) -> None:
    # No monkeypatch: the synthetic plan digest cannot match the committed one.
    plan = _valid_plan_dict()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])
    assert rc == 1


def test_dry_run_makes_no_network_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no net"))
    )
    plan = _valid_plan_dict()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])


def test_execute_without_approval_record_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _valid_plan_dict()
    _sync_constants(monkeypatch, plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--execute"])
    assert rc == 1


# --- Integrity primitives ---------------------------------------------------
def test_same_size_without_checksum_is_not_complete(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    target.write_bytes(b"1234")
    assert tool.completion_status(target, 4, {}, "a.bin") == "size_only_unverified"


def test_matching_checksum_is_complete(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    target.write_bytes(b"1234")
    manifest = {"a.bin": hashlib.sha256(b"1234").hexdigest()}
    assert tool.completion_status(target, 4, manifest, "a.bin") == "complete"


def test_mismatching_checksum_rejected(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    target.write_bytes(b"1234")
    assert tool.completion_status(target, 4, {"a.bin": "0" * 64}, "a.bin") == "checksum_mismatch"


def test_manifest_roundtrip_relative_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "checksums.sha256"
    tool.append_manifest(manifest, "sub-SYNTHA/anat/x.nii.gz", "a" * 64)
    tool.append_manifest(manifest, "sub-SYNTHB/func/y.nii.gz", "b" * 64)
    read = tool.read_manifest(manifest)
    assert read == {"sub-SYNTHA/anat/x.nii.gz": "a" * 64, "sub-SYNTHB/func/y.nii.gz": "b" * 64}


def test_event_rejects_url_or_credential(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="URL or credential"):
        tool.append_event(tmp_path, {"event": "x", "download_url": "https://s3/x"})


def test_event_written_without_secrets(tmp_path: Path) -> None:
    tool.append_event(tmp_path, {"event": "run_started", "scope": "ds000030_pilot_5_subjects"})
    text = (tmp_path / "acquisition-events.jsonl").read_text(encoding="utf-8")
    assert "run_started" in text
    assert "http" not in text.lower()


# --- Selection --------------------------------------------------------------
def test_selection_digest_is_sha256_not_builtin_hash() -> None:
    expected = hashlib.sha256(b"20260717|ds000030|1.0.0|pilot-selection-v1|sub-SYNTHA").hexdigest()
    assert tool.selection_digest("sub-SYNTHA", "20260717") == expected


def test_selection_deterministic_order_independent() -> None:
    ids = [*_SUBJECTS, "sub-SYNTHF", "sub-SYNTHG"]
    a = tool.select_pilot_subjects(ids, "20260717", 5)
    b = tool.select_pilot_subjects(list(reversed(ids)), "20260717", 5)
    assert a == b and len(a) == 5
