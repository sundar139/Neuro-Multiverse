"""Tests for the ds000030 pilot acquisition tool.

Synthetic values only: subject ids carry a ``sub-SYNTH`` prefix and never match a
real five-digit ds000030 label. No test performs a network body request; the
download primitives are exercised with local fixtures.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_TOOL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "acquire_ds000030_pilot.py"


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("acquire_ds000030_pilot", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()

_IDS = ["sub-SYNTHA", "sub-SYNTHB", "sub-SYNTHC", "sub-SYNTHD", "sub-SYNTHE", "sub-SYNTHF"]


def _valid_plan() -> dict[str, Any]:
    files: list[dict[str, Any]] = [
        {"local_relative_target": "dataset_description.json", "provider_size_bytes": 100},
        {
            "local_relative_target": "sub-SYNTHA/anat/sub-SYNTHA_T1w.nii.gz",
            "provider_size_bytes": 500,
        },
        {
            "local_relative_target": "sub-SYNTHB/func/sub-SYNTHB_task-rest_bold.nii.gz",
            "provider_size_bytes": 700,
        },
    ]
    total = sum(f["provider_size_bytes"] for f in files)
    return {
        "schema_version": "1",
        "dataset_accession": "ds000030",
        "snapshot": "1.0.0",
        "doi": "10.18112/openneuro.ds000030.v1.0.0",
        "acquisition_scope_id": "ds000030_pilot_5_subjects",
        "selection_algorithm_version": "pilot-selection-v1",
        "base_seed": "20260717",
        "selected_subject_count": 5,
        "selected_subject_ids": [
            "sub-SYNTHA",
            "sub-SYNTHB",
            "sub-SYNTHC",
            "sub-SYNTHD",
            "sub-SYNTHE",
        ],
        "files": files,
        "expected_file_count": len(files),
        "expected_transfer_bytes": total,
    }


def _write_plan(tmp_path: Path, plan: dict[str, Any]) -> Path:
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return p


# --- Deterministic selection ------------------------------------------------
def test_selection_digest_is_sha256_not_builtin_hash() -> None:
    expected = hashlib.sha256(b"20260717|ds000030|1.0.0|pilot-selection-v1|sub-SYNTHA").hexdigest()
    assert tool.selection_digest("sub-SYNTHA", "20260717") == expected


def test_selection_is_deterministic_and_exactly_five() -> None:
    picked = tool.select_pilot_subjects(_IDS, "20260717", 5)
    assert len(picked) == 5
    assert tool.select_pilot_subjects(_IDS, "20260717", 5) == picked


def test_selection_is_independent_of_input_order() -> None:
    a = tool.select_pilot_subjects(_IDS, "20260717", 5)
    b = tool.select_pilot_subjects(list(reversed(_IDS)), "20260717", 5)
    assert a == b


# --- Precondition checks ----------------------------------------------------
def _ok_kwargs(plan: dict[str, Any], target_root: Path) -> dict[str, Any]:
    return {
        "plan": plan,
        "expected_digest": tool.canonical_digest(plan),
        "target_root": target_root,
        "free_bytes": tool.RESERVE_BYTES + 10**9,
        "approved": True,
        "require_digest": True,
    }


def test_valid_plan_has_no_precondition_problems(tmp_path: Path) -> None:
    assert tool.check_preconditions(**_ok_kwargs(_valid_plan(), tmp_path)) == []


def test_scope_mismatch_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["acquisition_scope_id"] = "ds000030_full_snapshot"
    problems = tool.check_preconditions(**_ok_kwargs(plan, tmp_path))
    assert any("scope" in p for p in problems)


def test_snapshot_mismatch_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["snapshot"] = "2.0.0"
    assert any("snapshot" in p for p in tool.check_preconditions(**_ok_kwargs(plan, tmp_path)))


def test_doi_mismatch_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["doi"] = "10.0/wrong"
    assert any("DOI" in p for p in tool.check_preconditions(**_ok_kwargs(plan, tmp_path)))


def test_subject_count_mismatch_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["selected_subject_count"] = 4
    assert any("count" in p.lower() for p in tool.check_preconditions(**_ok_kwargs(plan, tmp_path)))


def test_plan_digest_mismatch_rejected(tmp_path: Path) -> None:
    kwargs = _ok_kwargs(_valid_plan(), tmp_path)
    kwargs["expected_digest"] = "0" * 64
    assert any("digest" in p for p in tool.check_preconditions(**kwargs))


def test_participant_table_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["files"].append({"local_relative_target": "participants.tsv", "provider_size_bytes": 10})
    plan["expected_transfer_bytes"] += 10
    problems = tool.check_preconditions(**_ok_kwargs(plan, tmp_path))
    assert any("participant/phenotype" in p for p in problems)


def test_phenotype_file_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["files"].append(
        {"local_relative_target": "phenotype/demographics.tsv", "provider_size_bytes": 10}
    )
    plan["expected_transfer_bytes"] += 10
    problems = tool.check_preconditions(**_ok_kwargs(plan, tmp_path))
    assert any("participant/phenotype" in p for p in problems)


def test_duplicate_target_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    dup = dict(plan["files"][1])
    plan["files"].append(dup)
    plan["expected_transfer_bytes"] += dup["provider_size_bytes"]
    assert any("duplicate" in p for p in tool.check_preconditions(**_ok_kwargs(plan, tmp_path)))


def test_path_traversal_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["files"].append({"local_relative_target": "../escape.nii.gz", "provider_size_bytes": 5})
    plan["expected_transfer_bytes"] += 5
    assert any("traversal" in p for p in tool.check_preconditions(**_ok_kwargs(plan, tmp_path)))


def test_target_root_inside_repo_rejected() -> None:
    plan = _valid_plan()
    inside = Path(__file__).resolve().parents[1] / "data"
    problems = tool.check_preconditions(**_ok_kwargs(plan, inside))
    assert any("outside the Git repository" in p for p in problems)


def test_insufficient_capacity_rejected(tmp_path: Path) -> None:
    kwargs = _ok_kwargs(_valid_plan(), tmp_path)
    kwargs["free_bytes"] = 10
    assert any("capacity" in p for p in tool.check_preconditions(**kwargs))


# --- Dry-run and execute gating ---------------------------------------------
def test_dry_run_makes_no_network_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("dry-run must not open the network")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    plan_path = _write_plan(tmp_path, _valid_plan())
    rc = tool.main(["--plan", str(plan_path), "--target-root", str(tmp_path), "--dry-run"])
    assert rc == 0


def test_execute_without_approval_fails(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path, _valid_plan())
    digest = tool.canonical_digest(_valid_plan())
    rc = tool.main(
        [
            "--plan",
            str(plan_path),
            "--target-root",
            str(tmp_path),
            "--execute",
            "--plan-digest",
            digest,
        ]
    )
    assert rc == 1


# --- Partial-file and atomic-rename primitives (local fixtures) --------------
def test_finalize_partial_atomically_promotes(tmp_path: Path) -> None:
    target = tmp_path / "sub-SYNTHA" / "x.nii.gz"
    target.parent.mkdir(parents=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.write_bytes(b"1234567890")
    tool.finalize_partial(partial, target, expected_size=10)
    assert target.exists() and not partial.exists()
    assert target.read_bytes() == b"1234567890"


def test_finalize_partial_refuses_to_overwrite_complete(tmp_path: Path) -> None:
    target = tmp_path / "x.bin"
    target.write_bytes(b"abc")
    partial = tmp_path / "x.bin.partial"
    partial.write_bytes(b"abc")
    with pytest.raises(RuntimeError, match="already-complete"):
        tool.finalize_partial(partial, target, expected_size=3)


def test_finalize_partial_rejects_size_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "y.bin"
    partial = tmp_path / "y.bin.partial"
    partial.write_bytes(b"abcd")
    with pytest.raises(RuntimeError, match="partial size"):
        tool.finalize_partial(partial, target, expected_size=99)


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    f = tmp_path / "z.bin"
    f.write_bytes(b"neuro")
    assert tool.sha256_file(f) == hashlib.sha256(b"neuro").hexdigest()


def test_is_complete(tmp_path: Path) -> None:
    f = tmp_path / "c.bin"
    f.write_bytes(b"1234")
    assert tool.is_complete(f, 4)
    assert not tool.is_complete(f, 5)
    assert not tool.is_complete(tmp_path / "missing", 4)
