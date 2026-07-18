from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

nib: Any = pytest.importorskip("nibabel")
np: Any = pytest.importorskip("numpy")


def _load_tool() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "validate_ds000030_pilot.py"
    spec = importlib.util.spec_from_file_location("validate_ds000030_pilot", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def _nifti(path: Path, shape: tuple[int, ...], tr: float | None = None) -> None:
    image = nib.Nifti1Image(np.zeros(shape, dtype=np.int16), np.eye(4))
    if tr is not None:
        image.header.set_zooms((1.0, 1.0, 1.0, tr))
    nib.save(image, path)
    if os.name != "nt":
        path.chmod(0o600)


def _dataset(tmp_path: Path, *, tr: float = 2.0) -> Path:
    root = tmp_path / "raw"
    root.mkdir()
    _json(root / "dataset_description.json", {"Name": "Synthetic", "BIDSVersion": "1.8.0"})
    _json(root / "task-rest_bold.json", {"TaskName": "rest", "RepetitionTime": tr})
    for index in range(5):
        subject = f"sub-syn{index + 1}"
        anat = root / subject / "anat"
        func = root / subject / "func"
        anat.mkdir(parents=True)
        func.mkdir(parents=True)
        _nifti(anat / f"{subject}_T1w.nii.gz", (2, 2, 2))
        _json(anat / f"{subject}_T1w.json", {})
        _nifti(func / f"{subject}_task-rest_bold.nii.gz", (2, 2, 2, 120), tr)
        _json(func / f"{subject}_task-rest_bold.json", {})
    return root


def _structure(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = _dataset(tmp_path)
    structure = tool._validate_structure(root)
    tool._validate_metadata(root, structure)
    return root, structure


def test_valid_minimal_five_subject_structure_passes(tmp_path: Path) -> None:
    root, structure = _structure(tmp_path)
    result = tool._validate_headers(structure)
    assert result["t1w_count"] == result["bold_count"] == 5
    assert result["nifti_headers_parsed"] == 10
    assert len(list(root.rglob("*.nii.gz"))) == 10


def test_missing_dataset_description_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    (root / "dataset_description.json").unlink()
    with pytest.raises(tool.ValidationError, match="root metadata"):
        tool._validate_structure(root)


@pytest.mark.parametrize("invalid", ['{"Name":"a","Name":"b"}', '{"Name":NaN}'])
def test_strict_json_rejects_duplicate_or_nonfinite(tmp_path: Path, invalid: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(invalid, encoding="utf-8")
    with pytest.raises(tool.ValidationError):
        tool._strict_json(path)


def test_missing_bold_sidecar_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    next(root.rglob("*_task-rest_bold.json")).unlink()
    with pytest.raises(tool.ValidationError, match="file count"):
        tool._validate_structure(root)


def test_orphan_sidecar_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    next(root.rglob("*_task-rest_bold.nii.gz")).unlink()
    with pytest.raises(tool.ValidationError, match="file count"):
        tool._validate_structure(root)


def test_conflicting_inherited_repetition_time_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    _json(next(root.rglob("*_task-rest_bold.json")), {"RepetitionTime": 3.0})
    with pytest.raises(tool.ValidationError, match="conflict"):
        tool._validate_metadata(root, tool._validate_structure(root))


def test_nonpositive_repetition_time_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    _json(root / "task-rest_bold.json", {"TaskName": "rest", "RepetitionTime": 0})
    with pytest.raises(tool.ValidationError, match="repetition time"):
        tool._validate_metadata(root, tool._validate_structure(root))


def test_header_json_tr_mismatch_fails(tmp_path: Path) -> None:
    root, structure = _structure(tmp_path)
    _json(root / "task-rest_bold.json", {"TaskName": "rest", "RepetitionTime": 3.0})
    tool._validate_metadata(root, structure)
    with pytest.raises(tool.ValidationError, match="repetition times"):
        tool._validate_headers(structure)


@pytest.mark.parametrize(
    ("pattern", "shape", "message"),
    [
        ("*_T1w.nii.gz", (2, 2, 2, 2), "dimensionality"),
        ("*_bold.nii.gz", (2, 2, 2), "dimensionality"),
    ],
)
def test_wrong_nifti_dimensionality_fails(
    tmp_path: Path, pattern: str, shape: tuple[int, ...], message: str
) -> None:
    root = _dataset(tmp_path)
    _nifti(next(root.rglob(pattern)), shape, 2.0 if len(shape) == 4 else None)
    structure = tool._validate_structure(root)
    tool._validate_metadata(root, structure)
    with pytest.raises(tool.ValidationError, match=message):
        tool._validate_headers(structure)


def test_unreadable_nifti_header_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.nii.gz"
    path.write_bytes(b"not gzip")
    with pytest.raises(tool.ValidationError, match="unreadable"):
        tool._validate_header(path, 3)


def test_nonfinite_affine_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "image.nii.gz"
    _nifti(path, (2, 2, 2))
    image = nib.load(path)
    affine = np.eye(4)
    affine[0, 0] = np.nan
    fake = SimpleNamespace(shape=(2, 2, 2), header=image.header, affine=affine)
    monkeypatch.setattr(tool.nib, "load", lambda *_args, **_kwargs: fake)
    with pytest.raises(tool.ValidationError, match="affine"):
        tool._validate_header(path, 3)


def test_nonpositive_voxel_size_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "image.nii.gz"
    _nifti(path, (2, 2, 2))
    image = nib.load(path)
    monkeypatch.setattr(tool.nib, "load", lambda *_args, **_kwargs: image)
    monkeypatch.setattr(image.header, "get_zooms", lambda: (0.0, 1.0, 1.0))
    with pytest.raises(tool.ValidationError, match="spacing"):
        tool._validate_header(path, 3)


def test_gzip_corruption_fails(tmp_path: Path) -> None:
    root, structure = _structure(tmp_path)
    path = next(root.rglob("*_T1w.nii.gz"))
    path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(tool.ValidationError, match=r"gzip|unreadable"):
        tool._validate_headers(structure)


def test_manifest_hash_mismatch_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    manifest = {p.relative_to(root).as_posix(): "0" * 64 for p in root.rglob("*") if p.is_file()}
    with pytest.raises(tool.ValidationError, match="hash or size"):
        tool._snapshot(root, manifest)


def test_unexpected_file_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    (root / "README").write_text("unexpected")
    with pytest.raises(tool.ValidationError, match="root metadata"):
        tool._validate_structure(root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_symlink_escape_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("outside")
    link = next(root.rglob("*.json"))
    link.unlink()
    link.symlink_to(outside)
    manifest = {
        p.relative_to(root).as_posix(): tool._sha256(p) for p in root.rglob("*") if p.is_file()
    }
    with pytest.raises(tool.ValidationError, match=r"escapes|symbolic"):
        tool._snapshot(root, manifest)


def test_voxel_array_access_is_never_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _root, structure = _structure(tmp_path)
    monkeypatch.setattr(nib.Nifti1Image, "get_fdata", lambda *_: pytest.fail("voxel access"))
    result = tool._validate_headers(structure)
    assert result["nifti_headers_parsed"] == 10


def _validator_result(errors: int = 0, warnings: int = 0) -> str:
    issues = ([{"severity": "error", "code": "SYNTHETIC_ERROR"}] * errors) + (
        [{"severity": "warning", "code": "README_FILE_MISSING"}] * warnings
    )
    return json.dumps(
        {"issues": {"issues": issues}, "summary": {"schemaVersion": "1.2.4", "totalFiles": 22}}
    )


def test_validator_error_makes_gate_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = iter(
        [
            subprocess.CompletedProcess([], 0, "bids-validator 3.0.0", ""),
            subprocess.CompletedProcess([], 16, _validator_result(errors=1), ""),
        ]
    )
    monkeypatch.setattr(tool.subprocess, "run", lambda *_args, **_kwargs: next(results))
    with pytest.raises(tool.ValidationError, match="reported errors"):
        tool._run_validator(Path("validator"), tmp_path, tmp_path / "output.json", "3.0.0")


def test_validator_warning_is_retained_and_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = iter(
        [
            subprocess.CompletedProcess([], 0, "bids-validator 3.0.0", ""),
            subprocess.CompletedProcess([], 0, _validator_result(warnings=1), ""),
        ]
    )
    monkeypatch.setattr(tool.subprocess, "run", lambda *_args, **_kwargs: next(results))
    result = tool._run_validator(Path("validator"), tmp_path, tmp_path / "output.json", "3.0.0")
    assert result["warning_count"] == 1
    assert result["warning_classifications"]["README_FILE_MISSING"]


def test_subject_token_does_not_disclose_subject() -> None:
    token = tool._subject_token("sub-synthetic")
    assert "synthetic" not in token and len(token) == 12


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode enforcement")
def test_validator_output_is_created_mode_600(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = iter(
        [
            subprocess.CompletedProcess([], 0, "bids-validator 3.0.0", ""),
            subprocess.CompletedProcess([], 0, _validator_result(), ""),
        ]
    )
    monkeypatch.setattr(tool.subprocess, "run", lambda *_args, **_kwargs: next(results))
    output = tmp_path / "validator.json"
    tool._run_validator(Path("validator"), tmp_path, output, "3.0.0")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_snapshot_detects_file_change(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    manifest = {
        p.relative_to(root).as_posix(): tool._sha256(p) for p in root.rglob("*") if p.is_file()
    }
    before = tool._snapshot(root, manifest)
    path = next(root.rglob("*.json"))
    path.write_text(path.read_text() + " ")
    assert before
    with pytest.raises(tool.ValidationError, match="hash or size"):
        tool._snapshot(root, manifest)
