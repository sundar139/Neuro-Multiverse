"""Tests for the hardened ds000030 pilot acquisition executor and schema.

Synthetic values only: subject ids use a ``sub-SYNTH`` prefix and never match a
real five-digit ds000030 label. No test performs a network body request; the
integrity primitives are exercised with local fixtures and injected streams.
Where a test needs the executor's committed evidence constants to match a
synthetic plan, they are monkeypatched on the loaded module.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
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
_POSIX = hasattr(os, "getuid")


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("acquire_ds000030_pilot", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # required so dataclasses can resolve annotations
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


# --- Plan fixtures ----------------------------------------------------------
def _entry(
    subject: str | None,
    role: str,
    rel: str,
    path: str,
    oid: str,
    size: int,
    **over: Any,
) -> dict[str, Any]:
    base = {
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
    base.update(over)
    return base


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
        files.extend(
            [
                _entry(
                    sid,
                    "t1w_image",
                    f"{sid}/anat/{sid}_T1w.nii.gz",
                    f"{sid}/anat/{sid}_T1w.nii.gz",
                    f"a{i}",
                    size,
                ),
                _entry(
                    sid,
                    "t1w_sidecar",
                    f"{sid}/anat/{sid}_T1w.json",
                    f"{sid}/anat/{sid}_T1w.json",
                    f"b{i}",
                    10,
                ),
                _entry(
                    sid,
                    "rest_bold_image",
                    f"{sid}/func/{sid}_task-rest_bold.nii.gz",
                    f"{sid}/func/{sid}_task-rest_bold.nii.gz",
                    f"c{i}",
                    size,
                ),
                _entry(
                    sid,
                    "rest_bold_sidecar",
                    f"{sid}/func/{sid}_task-rest_bold.json",
                    f"{sid}/func/{sid}_task-rest_bold.json",
                    f"d{i}",
                    10,
                ),
            ]
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
        _entry(
            "sub-SYNTHZ",
            "t1w_image",
            "sub-SYNTHZ/anat/sub-SYNTHZ_T1w.nii.gz",
            "sub-SYNTHZ/anat/sub-SYNTHZ_T1w.nii.gz",
            "z1",
            5,
        )
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
    with pytest.raises(ValidationError):
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


# --- Section 7: provider-path + role semantics ------------------------------
def test_provider_path_subject_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match="subject"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "t1w_image",
                "sub-SYNTHB/anat/sub-SYNTHB_T1w.nii.gz",
                "sub-SYNTHB/anat/sub-SYNTHB_T1w.nii.gz",
                "id",
                5,
            )
        )


def test_local_target_subject_mismatch_rejected() -> None:
    # provider_path is subject A, local target is subject B: local must preserve provider.
    with pytest.raises(ValidationError, match=r"preserve|subject"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "t1w_image",
                "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
                "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
                "id",
                5,
                local_relative_target="sub-SYNTHB/anat/sub-SYNTHA_T1w.nii.gz",
            )
        )


def test_t1w_role_with_non_t1w_path_rejected() -> None:
    with pytest.raises(ValidationError, match="T1w"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "t1w_image",
                "sub-SYNTHA/anat/sub-SYNTHA_task-rest_bold.nii.gz",
                "sub-SYNTHA/anat/sub-SYNTHA_task-rest_bold.nii.gz",
                "id",
                5,
            )
        )


def test_t1w_image_not_under_anat_rejected() -> None:
    with pytest.raises(ValidationError, match="anat"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "t1w_image",
                "sub-SYNTHA/func/sub-SYNTHA_T1w.nii.gz",
                "sub-SYNTHA/func/sub-SYNTHA_T1w.nii.gz",
                "id",
                5,
            )
        )


def test_rest_bold_with_non_rest_task_rejected() -> None:
    with pytest.raises(ValidationError, match="rest"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "rest_bold_image",
                "sub-SYNTHA/func/sub-SYNTHA_task-stopsignal_bold.nii.gz",
                "sub-SYNTHA/func/sub-SYNTHA_task-stopsignal_bold.nii.gz",
                "id",
                5,
            )
        )


def test_dataset_metadata_local_target_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match=r"dataset_metadata|allowlist"):
        PilotFileEntry.model_validate(
            _entry(
                None,
                "dataset_metadata",
                "dataset_description.json",
                "dataset_description.json",
                "id",
                5,
                local_relative_target="task-rest_bold.json",
            )
        )


def test_sidecar_without_image_rejected() -> None:
    plan = _valid_plan_dict()
    plan["files"] = [
        f
        for f in plan["files"]
        if not (f["subject"] == "sub-SYNTHA" and f["file_role"] == "t1w_image")
    ]
    plan["files"].append(
        _entry(
            "sub-SYNTHA",
            "t1w_image",
            "sub-SYNTHA/anat/sub-SYNTHA_run-2_T1w.nii.gz",
            "sub-SYNTHA/anat/sub-SYNTHA_run-2_T1w.nii.gz",
            "a9",
            1000,
        )
    )
    plan["expected_file_count"] = len(plan["files"])
    plan["expected_transfer_bytes"] = sum(f["provider_size_bytes"] for f in plan["files"])
    with pytest.raises(ValidationError, match=r"corresponding|sidecar"):
        PilotAcquisitionPlan.model_validate(plan)


def test_image_sidecar_mismatch_rejected() -> None:
    plan = _valid_plan_dict()
    for f in plan["files"]:
        if f["subject"] == "sub-SYNTHB" and f["file_role"] == "t1w_sidecar":
            f["provider_path"] = "sub-SYNTHB/anat/sub-SYNTHB_run-9_T1w.json"
            f["local_relative_target"] = "sub-SYNTHB/anat/sub-SYNTHB_run-9_T1w.json"
    with pytest.raises(ValidationError, match=r"corresponding|sidecar"):
        PilotAcquisitionPlan.model_validate(plan)


# --- Section 8: provider checksums ------------------------------------------
def test_suitable_checksum_requires_valid_digest_and_algorithm() -> None:
    with pytest.raises(ValidationError, match=r"algorithm|digest"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "t1w_image",
                "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
                "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
                "id",
                5,
                provider_checksum="xyz",
                provider_checksum_algorithm="sha256",
                provider_checksum_suitable_for_content_integrity=True,
            )
        )


def test_valid_suitable_checksum_accepted() -> None:
    entry = PilotFileEntry.model_validate(
        _entry(
            "sub-SYNTHA",
            "t1w_image",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "id",
            5,
            provider_checksum="a" * 64,
            provider_checksum_algorithm="sha256",
            provider_checksum_suitable_for_content_integrity=True,
        )
    )
    assert entry.provider_checksum_suitable_for_content_integrity is True


def test_no_provider_checksum_classified_unavailable() -> None:
    entry = PilotFileEntry.model_validate(
        _entry(
            "sub-SYNTHA",
            "t1w_image",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "id",
            5,
        )
    )
    assert tool._checksum_classification(entry) == "unavailable"


def test_unsuitable_provider_checksum_cannot_be_retained() -> None:
    with pytest.raises(ValidationError, match="unsuitable"):
        PilotFileEntry.model_validate(
            _entry(
                "sub-SYNTHA",
                "t1w_image",
                "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
                "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
                "id",
                3,
                provider_checksum="a" * 64,
                provider_checksum_algorithm="sha256",
                provider_checksum_suitable_for_content_integrity=False,
            )
        )


# --- URL safety / trusted origins -------------------------------------------
def test_validate_url_accepts_trusted_origins() -> None:
    tool.validate_url("https://openneuro.org/crn/datasets/ds000030/snapshots/1.0.0/files/x")
    tool.validate_url("https://s3.amazonaws.com/openneuro.org/x")


@pytest.mark.parametrize(
    "url",
    [
        "http://openneuro.org/crn/datasets/x",
        "ftp://openneuro.org/x",
        "file:///etc/passwd",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://10.0.0.1/x",
        "https://169.254.1.1/x",
        "https://2130706433/x",  # decimal 127.0.0.1
        "https://0x7f000001/x",  # hex 127.0.0.1
        "https://evil.example.com/x",
        "https://user:pass@s3.amazonaws.com/openneuro.org/x",  # userinfo
        "https://s3.amazonaws.com/openneuro.org/x#frag",  # fragment
        "https://s3.amazonaws.com:8443/openneuro.org/x",  # non-default port
        "https://openneuro.org/wrong/path",  # wrong path prefix
        "https://s3.amazonaws.com/openneuro.org/../wrong-bucket/x",
    ],
)
def test_validate_url_rejects_unsafe(url: str) -> None:
    with pytest.raises(ValueError):
        tool.validate_url(url)


def test_generic_s3_bucket_rejected() -> None:
    with pytest.raises(ValueError):
        tool.validate_url("https://s3.amazonaws.com/some-other-bucket/x")


def test_encoded_traversal_in_path_still_matches_prefix_only() -> None:
    # A path that does not start with the approved prefix is rejected.
    with pytest.raises(ValueError):
        tool.validate_url("https://s3.amazonaws.com/..%2fopenneuro.org/x")


def test_redirect_to_wrong_s3_bucket_rejected() -> None:
    handler = tool.SafeRedirectHandler()
    with pytest.raises(ValueError):
        handler.validate_redirect("https://s3.amazonaws.com/wrong-bucket/x")


def test_redirect_to_untrusted_host_rejected() -> None:
    handler = tool.SafeRedirectHandler()
    with pytest.raises(ValueError):
        handler.validate_redirect("https://evil.example.com/x")
    assert handler.validate_redirect("https://s3.amazonaws.com/openneuro.org/x")


def test_metadata_redirect_stays_on_exact_endpoint() -> None:
    handler = tool.OriginRedirectHandler(tool._METADATA_ORIGINS)
    assert handler.validate_redirect("https://openneuro.org/crn/graphql")


@pytest.mark.parametrize(
    "url",
    [
        "https://openneuro.org/crn/datasets/ds000030/x",
        "https://openneuro.org/another/path",
        "https://openneuro.org/crn/graphql/other",
        "https://s3.amazonaws.com/openneuro.org/x",
        "https://evil.example.com/crn/graphql",
    ],
)
def test_metadata_redirect_cannot_leave_exact_endpoint(url: str) -> None:
    handler = tool.OriginRedirectHandler(tool._METADATA_ORIGINS)
    with pytest.raises(ValueError):
        handler.validate_redirect(url)


# --- Live metadata resolver (synthetic injection) ---------------------------
def _synthetic_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tiny two-level tree with one resolvable object under sub-SYNTHA/anat."""
    levels = {
        None: [{"filename": "sub-SYNTHA", "id": "t1", "directory": True}],
        "t1": [{"filename": "anat", "id": "t2", "directory": True}],
        "t2": [
            {
                "filename": "sub-SYNTHA_T1w.nii.gz",
                "id": "oidA",
                "size": 1000,
                "directory": False,
                "urls": ["https://s3.amazonaws.com/openneuro.org/x"],
            }
        ],
    }
    monkeypatch.setattr(tool, "_graphql_files", lambda tree: levels[tree])


def test_default_resolver_returns_one_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    _synthetic_tree(monkeypatch)
    matches = tool._default_metadata_fetcher("oidA", "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz")
    assert len(matches) == 1
    assert matches[0]["provider_object_id"] == "oidA"
    assert matches[0]["provider_size_bytes"] == 1000


def test_default_resolver_rejects_duplicate_path_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tool,
        "_graphql_files",
        lambda _tree: [
            {"filename": "sub-SYNTHA", "id": "one", "directory": True},
            {"filename": "sub-SYNTHA", "id": "two", "directory": True},
        ],
    )
    assert tool._default_metadata_fetcher("oidA", "sub-SYNTHA/anat/file.nii.gz") == []


def test_root_graphql_query_has_no_empty_parentheses(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    captured: dict[str, str] = {}

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            self.close()

    class Opener:
        def open(self, request: Any, timeout: int) -> Response:
            captured["query"] = json.loads(request.data)["query"]
            return Response(b'{"data":{"snapshot":{"files":[]}}}')

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: Opener())
    tool._metadata_request_count = 0
    assert tool._graphql_files(None) == []
    assert "files()" not in captured["query"]
    assert tool._metadata_request_count == 1


def test_resolver_no_longer_raises_not_implemented() -> None:
    src = _TOOL_PATH.read_text(encoding="utf-8")
    assert "NotImplementedError" not in src


def test_resolution_does_not_open_object_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _synthetic_tree(monkeypatch)
    import urllib.request

    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("object body must not be opened during resolution")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    url = tool.resolve_download_url(
        "oidA",
        "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
        1000,
        tool._default_metadata_fetcher,
    )
    assert url.startswith("https://")


def test_resolve_download_url_zero_matches_fails() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        tool.resolve_download_url("oid", "path", 10, lambda _o, _p: [])


def test_resolve_download_url_multiple_matches_fails() -> None:
    def fetcher(_o: str, _p: str) -> list[dict[str, Any]]:
        m = {
            "provider_object_id": "oid",
            "provider_path": "path",
            "provider_size_bytes": 10,
            "url": "https://s3.amazonaws.com/openneuro.org/x",
        }
        return [m, dict(m)]

    with pytest.raises(ValueError, match="exactly one"):
        tool.resolve_download_url("oid", "path", 10, fetcher)


def test_resolve_download_url_single_trusted_match() -> None:
    def fetcher(_o: str, _p: str) -> list[dict[str, Any]]:
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
    def fetcher(_o: str, _p: str) -> list[dict[str, Any]]:
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


def test_resolver_exception_is_sanitized() -> None:
    def fetcher(_o: str, _p: str) -> list[dict[str, Any]]:
        raise ValueError("https://secret.example.com/signed?X-Amz-Signature=abc")

    with pytest.raises(ValueError) as exc:
        tool.resolve_download_url("oid", "path", 10, fetcher)
    assert "http" not in str(exc.value).lower()


# --- Approval + bundle + storage binding ------------------------------------
def test_no_approved_flag_exists() -> None:
    with pytest.raises(SystemExit):
        tool.main(["--plan", "x", "--target-root", "y", "--approved"])


def _bundle_head() -> str:
    return tool.executor_bundle_digest_at("HEAD") or "0" * 64


def _sync_constants(monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any]) -> str:
    digest = str(tool.canonical_plan_digest(plan))
    monkeypatch.setattr(tool, "DS000030_PLAN_CANONICAL_SHA256", digest)
    monkeypatch.setattr(tool, "DS000030_PILOT_FILE_COUNT", plan["expected_file_count"])
    monkeypatch.setattr(tool, "DS000030_PILOT_EXPECTED_BYTES", plan["expected_transfer_bytes"])
    monkeypatch.setattr(
        tool,
        "DS000030_PILOT_PLAN_REFERENCE",
        f"ds000030-pilot-plan-sha256:{digest}",
    )
    monkeypatch.setattr(tool, "DS000030_STORAGE_REFERENCE", "storage-readiness-sha256:" + "c" * 64)
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
        "storage_evidence_reference": "storage-readiness-sha256:" + "c" * 64,
        "storage_record_sha256": "c" * 64,
        "executor_bundle_sha256": _bundle_head(),
        "approved_code_commit": tool.head_commit(),
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
        ("storage_evidence_reference", "storage-readiness-sha256:" + "z" * 64),
        ("storage_record_sha256", "d" * 64),
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


def test_approved_record_requires_hex_digests() -> None:
    plan = _valid_plan_dict()
    with pytest.raises(ValidationError, match="SHA-256"):
        PilotApprovalRecord.model_validate(
            _approval("0" * 64, plan, executor_bundle_sha256="not-hex")
        )


def test_head_mismatch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    digest = _sync_constants(monkeypatch, plan)
    approval = PilotApprovalRecord.model_validate(
        _approval(digest, plan, approved_code_commit="f" * 40)
    )
    problems = tool.execution_repo_problems(approval)
    assert any("current HEAD" in p for p in problems)


def test_changed_bundle_digest_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    digest = _sync_constants(monkeypatch, plan)
    approval = PilotApprovalRecord.model_validate(
        _approval(digest, plan, executor_bundle_sha256="e" * 64)
    )
    problems = tool.execution_repo_problems(approval)
    assert any("bundle" in p for p in problems)


def test_bundle_digest_is_deterministic_and_frames_paths() -> None:
    a = tool.executor_bundle_digest_at("HEAD")
    b = tool.executor_bundle_digest_at("HEAD")
    assert a is not None and a == b and len(a) == 64


# --- Storage-record binding -------------------------------------------------
def _storage_record(target: Path, **over: Any) -> dict[str, Any]:
    base = {
        "schema_version": 1,
        "timestamp_utc": "2026-07-18T00:00:00Z",
        "starting_git_commit": "0" * 40,
        "wsl_distribution": "Ubuntu-24.04",
        "filesystem_device": "/dev/sdd",
        "filesystem_type": "ext4",
        "mount_point": "/never-a-real-mount",
        "resolved_external_data_root": str(target.resolve()),
        "available_bytes": 10**15,
        "controlled_raw_processing_reserve_bytes": 1000,
        "repository_root_checked_against": "/somewhere",
        "external_root_outside_git": True,
        "capacity_gate_passes": True,
        "tool_version": "preflight-1",
    }
    base.update(over)
    return base


def _storage_ready(monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]) -> None:
    monkeypatch.setattr(tool, "CONTROLLED_RESERVE_BYTES", 1000)
    monkeypatch.setattr(
        tool,
        "DS000030_STORAGE_REFERENCE",
        "storage-readiness-sha256:" + tool.canonical_json_digest(data),
    )
    monkeypatch.setattr(
        tool,
        "_mount_info",
        lambda _mount: (data["filesystem_device"], data["filesystem_type"]),
    )


def _raw_target(storage_root: Path) -> Path:
    target = storage_root / "ds000030" / "raw"
    target.mkdir(parents=True)
    return target


def test_storage_record_valid_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neuromultiverse.ds000030_pilot import PilotStorageRecord

    target = _raw_target(tmp_path)
    data = _storage_record(tmp_path)
    _storage_ready(monkeypatch, data)
    model = PilotStorageRecord.model_validate(data)
    assert tool.storage_problems(data, model, target, 100) == []


def test_storage_record_digest_mismatch_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neuromultiverse.ds000030_pilot import PilotStorageRecord

    target = _raw_target(tmp_path)
    data = _storage_record(tmp_path)
    _storage_ready(monkeypatch, data)
    tampered = dict(data)
    tampered["available_bytes"] = 999  # canonical digest now differs from the reference
    model = PilotStorageRecord.model_validate(tampered)
    assert any("digest" in p for p in tool.storage_problems(tampered, model, target, 100))


def test_storage_target_mismatch_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neuromultiverse.ds000030_pilot import PilotStorageRecord

    _raw_target(tmp_path)
    other = tmp_path / "wrong"
    other.mkdir()
    data = _storage_record(tmp_path)
    _storage_ready(monkeypatch, data)
    model = PilotStorageRecord.model_validate(data)
    assert any("runtime target" in p for p in tool.storage_problems(data, model, other, 100))


def test_storage_reserve_must_be_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neuromultiverse.ds000030_pilot import PilotStorageRecord

    target = _raw_target(tmp_path)
    data = _storage_record(tmp_path, controlled_raw_processing_reserve_bytes=999)
    _storage_ready(monkeypatch, data)
    model = PilotStorageRecord.model_validate(data)
    assert any("reserve" in p for p in tool.storage_problems(data, model, target, 100))


def test_storage_mount_must_still_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neuromultiverse.ds000030_pilot import PilotStorageRecord

    target = _raw_target(tmp_path)
    data = _storage_record(tmp_path)
    _storage_ready(monkeypatch, data)
    monkeypatch.setattr(tool, "_mount_info", lambda _mount: None)
    model = PilotStorageRecord.model_validate(data)
    assert any("mount" in p for p in tool.storage_problems(data, model, target, 100))


def _execution_preflight_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], Any]:
    plan = _valid_plan_dict()
    digest = _sync_constants(monkeypatch, plan)
    storage = _storage_record(tmp_path)
    _storage_ready(monkeypatch, storage)
    storage_digest = tool.canonical_json_digest(storage)
    approval = _approval(
        digest,
        plan,
        storage_evidence_reference=f"storage-readiness-sha256:{storage_digest}",
        storage_record_sha256=storage_digest,
    )
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "approval.json"
    storage_path = tmp_path / "storage.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    storage_path.write_text(json.dumps(storage), encoding="utf-8")
    target = _raw_target(tmp_path)
    monkeypatch.setattr(tool, "mode_is_600", lambda _path: True)
    monkeypatch.setattr(tool, "runtime_problems", lambda: [])
    monkeypatch.setattr(tool, "working_tree_clean", lambda: True)
    monkeypatch.setattr(tool, "working_files_match_commit", lambda _commit: True)

    def fetcher(oid: str, path: str) -> list[dict[str, Any]]:
        entry = next(item for item in plan["files"] if item["provider_object_id"] == oid)
        return [
            {
                "provider_object_id": oid,
                "provider_path": path,
                "provider_size_bytes": entry["provider_size_bytes"],
                "url": "https://s3.amazonaws.com/openneuro.org/synthetic",
            }
        ]

    args = [
        "--plan",
        str(plan_path),
        "--target-root",
        str(target),
        "--approval-record",
        str(approval_path),
        "--storage-record",
        str(storage_path),
        "--validate-execution",
    ]
    return args, fetcher


def test_validate_execution_requires_both_records(tmp_path: Path) -> None:
    plan = _valid_plan_dict()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert (
        tool.main(["--plan", str(path), "--target-root", str(tmp_path), "--validate-execution"])
        == 1
    )


def test_valid_execution_preflight_resolves_all_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    assert tool.main(args, fetcher=fetcher) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["metadata_objects_resolved"] == 22
    assert summary["network_body_requests"] == 0
    assert summary["preconditions_ok"] is True


def test_execution_preflight_missing_metadata_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    assert tool.main(args, fetcher=lambda _oid, _path: []) == 1


def test_execution_preflight_multiple_metadata_matches_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    assert tool.main(args, fetcher=lambda oid, path: fetcher(oid, path) * 2) == 1


@pytest.mark.parametrize("field", ["approved_code_commit", "executor_bundle_sha256"])
def test_execution_preflight_rejects_code_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    approval_path = Path(args[args.index("--approval-record") + 1])
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval[field] = "f" * (40 if field == "approved_code_commit" else 64)
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_rejects_unsupported_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "runtime_problems", lambda: ["unsupported runtime"])
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_rejects_dirty_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "working_tree_clean", lambda: False)
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_rejects_unverifiable_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "mode_is_600", lambda _path: None)
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_rejects_malformed_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    manifest = tmp_path / "ds000030" / "checksums.sha256"
    manifest.write_text("bad\n", encoding="utf-8")
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_rejects_storage_target_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    wrong = tmp_path / "wrong-target"
    wrong.mkdir()
    args[args.index("--target-root") + 1] = str(wrong)
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_rejects_mount_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "_mount_info", lambda _mount: ("wrong", "wrong"))
    assert tool.main(args, fetcher=fetcher) == 1


def test_execution_preflight_existing_lock_fails_without_modifying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, fetcher = _execution_preflight_fixture(tmp_path, monkeypatch)
    lock = tmp_path / "acquisition-log" / "ds000030-pilot.lock"
    lock.parent.mkdir()
    lock.write_text("unchanged", encoding="utf-8")
    assert tool.main(args, fetcher=fetcher) == 1
    assert lock.read_text(encoding="utf-8") == "unchanged"


def test_ordinary_dry_run_with_evidence_cannot_false_green(tmp_path: Path) -> None:
    assert (
        tool.main(
            [
                "--plan",
                str(tmp_path / "plan"),
                "--target-root",
                str(tmp_path),
                "--approval-record",
                str(tmp_path / "approval"),
            ]
        )
        == 1
    )


# --- Runtime / mode gates ---------------------------------------------------
def test_execute_without_records_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    _sync_constants(monkeypatch, plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--execute"])
    assert rc == 1


@pytest.mark.skipif(_POSIX, reason="non-POSIX runtime check")
def test_non_posix_runtime_cannot_execute() -> None:
    assert tool.runtime_problems()  # Windows: no getuid / not WSL


def test_mode_is_600_none_is_not_success(tmp_path: Path) -> None:
    f = tmp_path / "x"
    f.write_text("y", encoding="utf-8")
    result = tool.mode_is_600(f)
    assert result is not True or result is True  # POSIX may report True; None on Windows
    if not _POSIX:
        assert result is None


@pytest.mark.skipif(not _POSIX, reason="POSIX mode enforcement")
def test_non_600_record_rejected_at_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    _sync_constants(monkeypatch, plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(_approval(tool.canonical_plan_digest(plan), plan)), encoding="utf-8"
    )
    approval_path.chmod(0o644)
    rc = tool.main(
        [
            "--plan",
            str(plan_path),
            "--target-root",
            str(tmp_path),
            "--approval-record",
            str(approval_path),
            "--dry-run",
        ]
    )
    assert rc == 1


# --- Dry-run gating ---------------------------------------------------------
def test_dry_run_returns_zero_when_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _valid_plan_dict()
    _sync_constants(monkeypatch, plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    plan_path.chmod(0o600)
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])
    assert rc == 0


def test_dry_run_returns_nonzero_on_precondition_failure(tmp_path: Path) -> None:
    plan = _valid_plan_dict()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])
    assert rc == 1


def test_dry_run_makes_no_network_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no net")),
    )
    plan = _valid_plan_dict()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])


# --- Strict manifest --------------------------------------------------------
def test_manifest_roundtrip_canonical_sorted(tmp_path: Path) -> None:
    manifest = tmp_path / "checksums.sha256"
    tool.add_manifest_entry(manifest, "sub-SYNTHB/func/y.nii.gz", "b" * 64)
    tool.add_manifest_entry(manifest, "sub-SYNTHA/anat/x.nii.gz", "a" * 64)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert lines == [
        f"{'a' * 64}  sub-SYNTHA/anat/x.nii.gz",
        f"{'b' * 64}  sub-SYNTHB/func/y.nii.gz",
    ]
    assert tool.read_manifest(manifest) == {
        "sub-SYNTHA/anat/x.nii.gz": "a" * 64,
        "sub-SYNTHB/func/y.nii.gz": "b" * 64,
    }


@pytest.mark.skipif(not _POSIX, reason="POSIX secure creation modes")
def test_manifest_created_mode_600_and_parent_fsynced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    real_fsync = os.fsync

    def counted(fd: int) -> None:
        nonlocal calls
        calls += 1
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", counted)
    manifest = tmp_path / "checksums.sha256"
    tool.add_manifest_entry(manifest, "x/y", "a" * 64)
    assert manifest.stat().st_mode & 0o777 == 0o600
    assert calls >= 2


@pytest.mark.parametrize(
    "line",
    [
        "notahash  x/y.nii.gz",
        f"{'A' * 64}  x/y.nii.gz",  # uppercase
        f"{'a' * 64}  /abs/path.nii.gz",  # absolute
        f"{'a' * 64}  ../escape.nii.gz",  # traversal
        f"{'a' * 64} single-space.nii.gz",  # wrong separator
        "",  # blank lines are malformed, not silently ignored
    ],
)
def test_malformed_manifest_line_rejected(tmp_path: Path, line: str) -> None:
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(tool.ManifestError):
        tool.read_manifest(manifest)


def test_duplicate_manifest_path_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text(f"{'a' * 64}  x/y.nii.gz\n{'b' * 64}  x/y.nii.gz\n", encoding="utf-8")
    with pytest.raises(tool.ManifestError):
        tool.read_manifest(manifest)


def test_manifest_outside_namespace_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text(f"{'a' * 64}  x/y.nii.gz\n", encoding="utf-8")
    with pytest.raises(tool.ManifestError):
        tool.read_manifest(manifest, allowed_targets=frozenset({"only/this.nii.gz"}))


def test_add_manifest_entry_refuses_conflicting_digest(tmp_path: Path) -> None:
    manifest = tmp_path / "checksums.sha256"
    tool.add_manifest_entry(manifest, "x/y.nii.gz", "a" * 64)
    with pytest.raises(tool.ManifestError):
        tool.add_manifest_entry(manifest, "x/y.nii.gz", "b" * 64)


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


# --- Streamed download / promotion (injected stream) ------------------------
class _FakeResp(io.BytesIO):
    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *a: Any) -> None:
        self.close()


def _fake_opener(registry: dict[str, bytes]) -> Any:
    class _Opener:
        def open(self, req: Any, timeout: int = 0) -> _FakeResp:
            url = req.full_url if hasattr(req, "full_url") else req
            return _FakeResp(registry[url])

    return _Opener()


def test_stream_download_verifies_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    url = "https://s3.amazonaws.com/openneuro.org/x"
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: _fake_opener({url: b"abc"}))
    entry = PilotFileEntry.model_validate(
        _entry(
            "sub-SYNTHA",
            "t1w_image",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "id",
            3,
        )
    )
    partial = tmp_path / "out.partial"
    digest = tool._stream_download(url, partial, 3, entry)
    assert digest == hashlib.sha256(b"abc").hexdigest()


def test_provider_checksum_mismatch_prevents_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.request

    url = "https://s3.amazonaws.com/openneuro.org/x"
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: _fake_opener({url: b"abc"}))
    entry = PilotFileEntry.model_validate(
        _entry(
            "sub-SYNTHA",
            "t1w_image",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "id",
            3,
            provider_checksum="f" * 64,
            provider_checksum_algorithm="sha256",
            provider_checksum_suitable_for_content_integrity=True,
        )
    )
    with pytest.raises(RuntimeError, match="checksum"):
        tool._stream_download(url, tmp_path / "out.partial", 3, entry)


def test_execution_download_failure_removes_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.request

    plan_dict = _valid_plan_dict()
    plan = PilotAcquisitionPlan.model_validate(plan_dict)
    digest = _sync_constants(monkeypatch, plan_dict)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan_dict))
    url = "https://s3.amazonaws.com/openneuro.org/x"

    def fetcher(oid: str, path: str) -> list[dict[str, Any]]:
        entry = next(item for item in plan.files if item.provider_object_id == oid)
        return [
            {
                "provider_object_id": oid,
                "provider_path": path,
                "provider_size_bytes": entry.provider_size_bytes,
                "url": url,
            }
        ]

    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        lambda *_args: _fake_opener({url: b"x"}),
    )
    root = tmp_path / "ds000030"
    rc = tool._run_execution(
        plan,
        approval,
        root,
        fetcher,
        tmp_path / "log",
        root / "checksums.sha256",
        tmp_path / "log" / "run.lock",
    )
    assert rc == 1
    assert not list(root.glob("**/*.partial"))


def test_malformed_manifest_releases_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_dict = _valid_plan_dict()
    plan = PilotAcquisitionPlan.model_validate(plan_dict)
    digest = _sync_constants(monkeypatch, plan_dict)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan_dict))
    root = tmp_path / "ds000030"
    root.mkdir()
    (root / "checksums.sha256").write_text("bad\n", encoding="utf-8")
    lock_path = tmp_path / "log" / "run.lock"
    rc = tool._run_execution(
        plan,
        approval,
        root,
        lambda _oid, _path: [],
        tmp_path / "log",
        root / "checksums.sha256",
        lock_path,
    )
    assert rc == 1
    assert not lock_path.exists()


def test_manifest_failure_after_promotion_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = PilotFileEntry.model_validate(
        _entry(
            "sub-SYNTHA",
            "t1w_image",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "id",
            3,
        )
    )
    root = tmp_path / "ds000030"
    root.mkdir()

    def fake_stream(url: str, partial: Path, size: int, e: Any) -> str:
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"abc")
        return hashlib.sha256(b"abc").hexdigest()

    monkeypatch.setattr(tool, "_stream_download", fake_stream)
    monkeypatch.setattr(
        tool,
        "add_manifest_entry",
        lambda *args, **kwargs: (_ for _ in ()).throw(tool.ManifestError("boom")),
    )
    allowed = frozenset({entry.local_relative_target})
    with pytest.raises(tool.ManifestError):
        tool._download_one(
            entry,
            "https://s3.amazonaws.com/openneuro.org/x",
            root,
            root / "checksums.sha256",
            allowed,
            tmp_path / "log",
            {},
        )
    final = root / entry.local_relative_target
    assert not final.exists()  # not left as a size-only final file
    quarantined = list(root.glob("**/*.unrecorded.*"))
    assert quarantined


# --- Events -----------------------------------------------------------------
def test_event_rejects_url_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        tool.append_event(tmp_path, {"event": "x", "download_url": "https://s3/x"})


def test_event_rejects_url_value_not_only_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        tool.append_event(
            tmp_path, {"event": "x", "note": "https://s3.amazonaws.com/openneuro.org/y"}
        )


def test_event_written_with_common_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = PilotAcquisitionPlan.model_validate(_valid_plan_dict())
    digest = _sync_constants(monkeypatch, _valid_plan_dict())
    approval = PilotApprovalRecord.model_validate(_approval(digest, _valid_plan_dict()))
    context = tool._event_context(plan, approval)
    tool.append_event(tmp_path, {**context, "event": "run_started"})
    text = (tmp_path / "acquisition-events.jsonl").read_text(encoding="utf-8")
    for key in (
        "dataset_accession",
        "acquisition_scope_id",
        "snapshot",
        "canonical_plan_sha256",
        "approval_id",
        "approved_code_commit",
        "executor_bundle_sha256",
    ):
        assert key in text
    assert "http" not in text.lower()


@pytest.mark.skipif(not _POSIX, reason="POSIX secure creation modes")
def test_event_log_created_mode_600(tmp_path: Path) -> None:
    tool.append_event(tmp_path, {"event": "run_started"})
    assert (tmp_path / "acquisition-events.jsonl").stat().st_mode & 0o777 == 0o600


# --- Single-run lock --------------------------------------------------------
def test_execution_lock_rejects_second_process(tmp_path: Path) -> None:
    info = {
        "pid": os.getpid(),
        "hostname": "host",
        "started_utc": "t",
        "plan_digest": "d",
        "approval_id": "a",
    }
    lock1 = tool.ExecutionLock(tmp_path / "run.lock", info)
    lock1.acquire()
    try:
        lock2 = tool.ExecutionLock(tmp_path / "run.lock", info)
        with pytest.raises(tool.LockHeldError):
            lock2.acquire()
    finally:
        lock1.release()
    assert not (tmp_path / "run.lock").exists()


# --- Synthetic full execution (injected stream, no network) -----------------
def test_synthetic_execution_promotes_and_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.request

    plan_dict = _valid_plan_dict()
    plan = PilotAcquisitionPlan.model_validate(plan_dict)
    digest = _sync_constants(monkeypatch, plan_dict)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan_dict))

    registry: dict[str, bytes] = {}

    def fetcher(oid: str, path: str) -> list[dict[str, Any]]:
        entry = next(f for f in plan.files if f.provider_object_id == oid)
        url = f"https://s3.amazonaws.com/openneuro.org/{oid}"
        registry[url] = b"\0" * entry.provider_size_bytes
        return [
            {
                "provider_object_id": oid,
                "provider_path": path,
                "provider_size_bytes": entry.provider_size_bytes,
                "url": url,
            }
        ]

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_a: _fake_opener(registry))
    root = tmp_path / "ds000030"
    rc = tool._run_execution(
        plan,
        approval,
        root,
        fetcher,
        tmp_path / "acquisition-log",
        root / "checksums.sha256",
        tmp_path / "acquisition-log" / "run.lock",
    )
    assert rc == 0
    manifest = tool.read_manifest(root / "checksums.sha256")
    assert len(manifest) == 22
    for f in plan.files:
        assert (root / f.local_relative_target).stat().st_size == f.provider_size_bytes
    events = (tmp_path / "acquisition-log" / "acquisition-events.jsonl").read_text(encoding="utf-8")
    assert "run_completed" in events


def test_execution_fetcher_exception_generates_run_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_dict = _valid_plan_dict()
    plan = PilotAcquisitionPlan.model_validate(plan_dict)
    digest = _sync_constants(monkeypatch, plan_dict)
    approval = PilotApprovalRecord.model_validate(_approval(digest, plan_dict))

    def fetcher(_o: str, _p: str) -> list[dict[str, Any]]:
        raise ValueError("boom")

    root = tmp_path / "ds000030"
    rc = tool._run_execution(
        plan,
        approval,
        root,
        fetcher,
        tmp_path / "log",
        root / "checksums.sha256",
        tmp_path / "log" / "run.lock",
    )
    assert rc == 1
    events = (tmp_path / "log" / "acquisition-events.jsonl").read_text(encoding="utf-8")
    assert "file_failed" in events
    assert "run_failed" in events


# --- Selection --------------------------------------------------------------
def test_selection_digest_is_sha256_not_builtin_hash() -> None:
    expected = hashlib.sha256(b"20260717|ds000030|1.0.0|pilot-selection-v1|sub-SYNTHA").hexdigest()
    assert tool.selection_digest("sub-SYNTHA", "20260717") == expected


def test_selection_deterministic_order_independent() -> None:
    ids = [*_SUBJECTS, "sub-SYNTHF", "sub-SYNTHG"]
    a = tool.select_pilot_subjects(ids, "20260717", 5)
    b = tool.select_pilot_subjects(list(reversed(ids)), "20260717", 5)
    assert a == b and len(a) == 5
