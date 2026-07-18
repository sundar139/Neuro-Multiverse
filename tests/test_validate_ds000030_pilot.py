from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

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
    root.mkdir(mode=0o700)
    _json(root / "dataset_description.json", {"Name": "Synthetic", "BIDSVersion": "1.8.0"})
    _json(root / "task-rest_bold.json", {"TaskName": "rest", "RepetitionTime": tr})
    for index in range(5):
        subject = f"sub-syn{index + 1}"
        anat = root / subject / "anat"
        func = root / subject / "func"
        subject_dir = root / subject
        subject_dir.mkdir(mode=0o700)
        anat.mkdir(mode=0o700)
        func.mkdir(mode=0o700)
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


@pytest.mark.parametrize(
    "invalid",
    ['{"value":"\\u0000"}', '{"value":"\\u0001"}', '{"PatientID":"private"}'],
)
def test_strict_json_rejects_decoded_controls_and_participant_fields(
    tmp_path: Path, invalid: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(invalid, encoding="utf-8")
    with pytest.raises(tool.ValidationError):
        tool._strict_json(path)


def test_strict_json_accepts_legitimate_scanner_metadata(tmp_path: Path) -> None:
    path = tmp_path / "scanner.json"
    _json(path, {"Manufacturer": "Synthetic Scanner", "MagneticFieldStrength": 3})
    assert tool._strict_json(path)["MagneticFieldStrength"] == 3


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


def test_direct_override_is_accepted_but_heterogeneous_effective_tr_fails(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    _json(next(root.rglob("*_task-rest_bold.json")), {"RepetitionTime": 3.0})
    with pytest.raises(tool.ValidationError, match="controlled pilot"):
        tool._validate_metadata(root, tool._validate_structure(root))


def test_uniform_direct_override_is_effective(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    for sidecar in root.rglob("*_task-rest_bold.json"):
        _json(sidecar, {"RepetitionTime": 3.0})
    structure = tool._validate_structure(root)
    tool._validate_metadata(root, structure)
    assert {
        item["effective_bold_metadata"]["RepetitionTime"] for item in structure["subjects"]
    } == {3.0}


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


def _docker_runner(validator_output: str, returncode: int = 0) -> Any:
    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[-1] == "info":
            return subprocess.CompletedProcess(command, 0, "ok", "")
        if command[-3:-1] == ["image", "inspect"]:
            inspected = [
                {
                    "RepoDigests": [tool.VALIDATOR_IMAGE],
                    "Architecture": "amd64",
                    "Os": "linux",
                }
            ]
            return subprocess.CompletedProcess(command, 0, json.dumps(inspected), "")
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, tool.VALIDATOR_VERSION, "")
        return subprocess.CompletedProcess(command, returncode, validator_output, "")

    return run


def test_validator_error_makes_gate_fail(tmp_path: Path) -> None:
    with pytest.raises(tool.ValidationError, match="reported errors"):
        tool._run_validator(
            Path("docker"),
            tool.VALIDATOR_IMAGE,
            tmp_path,
            tmp_path / "output.json",
            _docker_runner(_validator_result(errors=1), 16),
        )


def test_validator_warning_is_retained_and_classified(tmp_path: Path) -> None:
    result = tool._run_validator(
        Path("docker"),
        tool.VALIDATOR_IMAGE,
        tmp_path,
        tmp_path / "output.json",
        _docker_runner(_validator_result(warnings=1)),
    )
    assert result["warning_count"] == 1
    assert result["warning_classifications"]["README_FILE_MISSING"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"summary": {"schemaVersion": "1.2.4", "totalFiles": 22}}, "issues"),
        ({"issues": [], "summary": {"schemaVersion": "1.2.4", "totalFiles": 22}}, "issues"),
        ({"issues": {}, "summary": {"schemaVersion": "1.2.4", "totalFiles": 22}}, "issue list"),
        (
            {"issues": {"issues": [None]}, "summary": {"schemaVersion": "1.2.4", "totalFiles": 22}},
            "issue",
        ),
        ({"issues": {"issues": []}}, "summary"),
        (
            {"issues": {"issues": []}, "summary": {"schemaVersion": "1.2.4", "totalFiles": 21}},
            "file count",
        ),
        (
            {"issues": {"issues": []}, "summary": {"schemaVersion": "1.2.3", "totalFiles": 22}},
            "schema",
        ),
        (
            {
                "issues": {"issues": [{"severity": "ignore", "code": "X"}]},
                "summary": {"schemaVersion": "1.2.4", "totalFiles": 22},
            },
            "ignored",
        ),
        (
            {
                "issues": {"issues": [{"severity": "warning", "code": "UNKNOWN"}]},
                "summary": {"schemaVersion": "1.2.4", "totalFiles": 22},
            },
            "unclassified",
        ),
        (
            {
                "issues": {"issues": [], "warningCount": 1},
                "summary": {"schemaVersion": "1.2.4", "totalFiles": 22},
            },
            "aggregate issue counts",
        ),
    ],
)
def test_validator_output_fails_closed(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(tool.ValidationError, match=message):
        tool._parse_validator_result(json.dumps(payload), 0)


def test_docker_policy_is_offline_read_only_and_minimally_mounted(tmp_path: Path) -> None:
    base = tool._docker_base_policy_args()
    dataset = tool._docker_dataset_policy_args(tmp_path)
    assert "--pull=never" in base
    assert "--network=none" in base
    assert "--read-only" in base
    assert "--cap-drop=ALL" in base
    assert "--security-opt=no-new-privileges" in base
    assert "--mount" not in base and str(tmp_path) not in " ".join(base)
    assert dataset.count("--mount") == 1
    assert f"src={tmp_path}" in " ".join(dataset)
    assert "dst=/data,readonly" in " ".join(dataset)
    assert "--config" not in dataset and "--ignoreNiftiHeaders" not in dataset


def test_repository_local_docker_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Path(__file__).parents[1] / "docker"
    monkeypatch.setattr(tool.shutil, "which", lambda _name: str(fake))
    monkeypatch.setattr(tool.Path, "resolve", lambda self, strict=False: self)
    monkeypatch.setattr(tool.Path, "is_file", lambda self: True)
    with pytest.raises(tool.ValidationError, match="trusted system"):
        tool._trusted_docker(fake)


def test_user_home_docker_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Path.home() / "bin" / "docker"
    monkeypatch.setattr(tool.shutil, "which", lambda _name: str(fake))
    monkeypatch.setattr(tool.Path, "resolve", lambda self, strict=False: self)
    monkeypatch.setattr(tool.Path, "is_file", lambda self: True)
    with pytest.raises(tool.ValidationError, match="trusted system"):
        tool._trusted_docker(fake)


@pytest.mark.skipif(os.name != "nt", reason="uses the Windows trusted system executable")
def test_trusted_system_docker_path_and_wrong_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = Path(r"C:\Windows\System32\where.exe")
    monkeypatch.setattr(tool.shutil, "which", lambda _name: str(trusted))
    assert tool._trusted_docker(trusted) == trusted.resolve()
    with pytest.raises(tool.ValidationError, match="differs"):
        tool._trusted_docker(Path(r"C:\Windows\System32\whoami.exe"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and mode enforcement")
def test_trusted_system_docker_path_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Path("/usr/bin/docker")
    resolved_docker = docker.resolve()
    original_stat = tool.Path.stat

    def trusted_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
        result = original_stat(path, *args, **kwargs)
        if path == resolved_docker:
            return SimpleNamespace(st_uid=0, st_mode=0o100755)
        return result

    monkeypatch.setattr(tool.shutil, "which", lambda _name: str(docker))
    monkeypatch.setattr(tool.Path, "stat", trusted_stat)
    assert tool._trusted_docker(docker) == resolved_docker


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and mode enforcement")
@pytest.mark.parametrize("mode", [0o100020, 0o100002])
def test_writable_docker_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    fake = tmp_path / "docker"
    fake.write_text("synthetic", encoding="utf-8")
    original_stat = tool.Path.stat

    def fake_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
        result = original_stat(path, *args, **kwargs)
        if path == fake:
            return SimpleNamespace(st_uid=0, st_mode=mode)
        return result

    monkeypatch.setattr(tool.shutil, "which", lambda _name: str(fake))
    monkeypatch.setattr(tool.Path, "stat", fake_stat)
    with pytest.raises(tool.ValidationError, match="ownership or mode"):
        tool._trusted_docker(fake)


@pytest.mark.parametrize(
    "image", ["bids/validator:3.0.0", "bids/validator:latest", "bids/validator@sha256:" + "0" * 64]
)
def test_mutable_or_wrong_validator_image_is_rejected(tmp_path: Path, image: str) -> None:
    with pytest.raises(tool.ValidationError, match="pinned digest"):
        tool._inspect_validator_image(Path("docker"), image, _docker_runner(_validator_result()))


def test_missing_local_validator_image_is_rejected() -> None:
    def missing(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[-1] == "info":
            return subprocess.CompletedProcess(command, 0, "ok", "")
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(tool.ValidationError, match="image is missing"):
        tool._inspect_validator_image(Path("docker"), tool.VALIDATOR_IMAGE, missing)


def test_non_linux_validator_image_is_rejected() -> None:
    base = _docker_runner(_validator_result())

    def non_linux(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[-3:-1] == ["image", "inspect"]:
            value = [
                {
                    "RepoDigests": [tool.VALIDATOR_IMAGE],
                    "Architecture": "amd64",
                    "Os": "windows",
                }
            ]
            return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
        return cast(subprocess.CompletedProcess[str], base(command, **kwargs))

    with pytest.raises(tool.ValidationError, match="operating system"):
        tool._inspect_validator_image(Path("docker"), tool.VALIDATOR_IMAGE, non_linux)


def test_image_disappearance_cannot_pull(tmp_path: Path) -> None:
    base = _docker_runner(_validator_result())
    runs: list[list[str]] = []

    def disappears(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "run" in command:
            runs.append(command)
            return subprocess.CompletedProcess(command, 125, "", "image missing")
        return cast(subprocess.CompletedProcess[str], base(command, **kwargs))

    with pytest.raises(tool.ValidationError, match="version differs"):
        tool._run_validator(
            Path("docker"),
            tool.VALIDATOR_IMAGE,
            tmp_path,
            tmp_path / "output.json",
            disappears,
        )
    assert runs and all("--pull=never" in command for command in runs)


def test_validator_version_mismatch_is_rejected(tmp_path: Path) -> None:
    base = _docker_runner(_validator_result())

    def wrong_version(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "3.0.1", "")
        return cast(subprocess.CompletedProcess[str], base(command, **kwargs))

    with pytest.raises(tool.ValidationError, match="version differs"):
        tool._run_validator(
            Path("docker"),
            tool.VALIDATOR_IMAGE,
            tmp_path,
            tmp_path / "output.json",
            wrong_version,
        )


def test_subject_token_does_not_disclose_subject() -> None:
    token = tool._subject_token("sub-synthetic")
    assert "synthetic" not in token and len(token) == 12


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode enforcement")
def test_validator_output_is_created_mode_600(
    tmp_path: Path,
) -> None:
    output = tmp_path / "validator.json"
    tool._run_validator(
        Path("docker"),
        tool.VALIDATOR_IMAGE,
        tmp_path,
        output,
        _docker_runner(_validator_result()),
    )
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


def _receipt_for_manifest(manifest: Path) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "scope": "ds000030_pilot_5_subjects",
        "actual_final_file_count": tool.EXPECTED_FILES,
        "actual_total_bytes": tool.EXPECTED_BYTES,
        "manifest_sha256": tool._sha256(manifest),
    }


def test_receipt_manifest_binding_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text("synthetic", encoding="utf-8")
    receipt = _receipt_for_manifest(manifest)
    monkeypatch.setattr(tool, "AUDITED_MANIFEST_SHA256", receipt["manifest_sha256"])
    monkeypatch.setattr(
        tool,
        "EXPECTED_RECEIPT",
        f"ds000030-pilot-acquisition-sha256:{tool._canonical_digest(receipt)}",
    )
    assert tool._validate_receipt_manifest_binding(receipt, manifest) == receipt["manifest_sha256"]


def test_actual_manifest_digest_mismatch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text("before", encoding="utf-8")
    receipt = _receipt_for_manifest(manifest)
    monkeypatch.setattr(tool, "AUDITED_MANIFEST_SHA256", receipt["manifest_sha256"])
    monkeypatch.setattr(
        tool,
        "EXPECTED_RECEIPT",
        f"ds000030-pilot-acquisition-sha256:{tool._canonical_digest(receipt)}",
    )
    manifest.write_text("after", encoding="utf-8")
    with pytest.raises(tool.ValidationError, match="manifest digest"):
        tool._validate_receipt_manifest_binding(receipt, manifest)


def test_manifest_binding_fails_before_raw_or_docker_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir(mode=0o700)
    output_dir = tmp_path / "reports"
    output_dir.mkdir(mode=0o700)
    manifest = tmp_path / "checksums.sha256"
    receipt = tmp_path / "receipt.json"
    manifest.write_text("synthetic", encoding="utf-8")
    _json(receipt, {"schema_version": "1"})
    if os.name != "nt":
        manifest.chmod(0o600)
    else:
        monkeypatch.setattr(tool, "_mode_private", lambda _path: True)
    monkeypatch.setattr(tool, "_require_runtime", lambda: None)
    monkeypatch.setattr(
        tool,
        "_validate_receipt_manifest_binding",
        lambda *_args: (_ for _ in ()).throw(tool.ValidationError("manifest digest mismatch")),
    )
    monkeypatch.setattr(
        tool,
        "_validate_private_tree",
        lambda *_args: pytest.fail("raw inspected"),
    )
    args = SimpleNamespace(
        raw_root=raw,
        manifest=manifest,
        acquisition_receipt=receipt,
        output=output_dir / "report.json",
        docker_executable=Path("docker"),
        validator_image=tool.VALIDATOR_IMAGE,
    )
    with pytest.raises(tool.ValidationError, match="manifest digest"):
        tool.validate(args, _docker_runner(_validator_result()))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"manifest_sha256": "0" * 64}, "manifest digest"),
        ({"manifest_sha256": None}, "malformed"),
        ({"remove_manifest": True}, "required fields"),
    ],
)
def test_receipt_manifest_binding_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, Any],
    message: str,
) -> None:
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text("synthetic", encoding="utf-8")
    receipt = _receipt_for_manifest(manifest)
    if change.get("remove_manifest"):
        receipt.pop("manifest_sha256")
    else:
        receipt.update(change)
    monkeypatch.setattr(
        tool,
        "EXPECTED_RECEIPT",
        f"ds000030-pilot-acquisition-sha256:{tool._canonical_digest(receipt)}",
    )
    with pytest.raises(tool.ValidationError, match=message):
        tool._validate_receipt_manifest_binding(receipt, manifest)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode enforcement")
def test_wrong_raw_mode_blocks_before_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dataset(tmp_path)
    next(root.rglob("*.json")).chmod(0o644)
    monkeypatch.setattr(tool, "_require_runtime", lambda: None)
    called = False

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("Docker invoked")

    manifest = {
        path.relative_to(root).as_posix(): tool._sha256(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(tool.ValidationError, match="mode is not 600"):
        tool._snapshot(root, manifest)
    assert not called


def test_synthetic_end_to_end_validate_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dataset(tmp_path)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    manifest_path = tmp_path / "checksums.sha256"
    manifest_path.write_text(
        "".join(f"{tool._sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "1",
        "scope": "ds000030_pilot_5_subjects",
        "actual_final_file_count": len(files),
        "actual_total_bytes": sum(path.stat().st_size for path in files),
        "manifest_sha256": tool._sha256(manifest_path),
    }
    receipt_path = tmp_path / "receipt.json"
    _json(receipt_path, receipt)
    output_dir = tmp_path / "reports"
    output_dir.mkdir(mode=0o700)
    docker = Path(r"C:\Windows\System32\where.exe") if os.name == "nt" else Path("/usr/bin/docker")
    resolved_docker = docker.resolve()
    original_which = tool.shutil.which
    monkeypatch.setattr(
        tool.shutil,
        "which",
        lambda name: str(docker) if name == "docker" else original_which(name),
    )
    if os.name != "nt":
        manifest_path.chmod(0o600)
        original_stat = tool.Path.stat

        def trusted_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
            result = original_stat(path, *args, **kwargs)
            if path == resolved_docker:
                return SimpleNamespace(st_uid=0, st_mode=0o100755)
            return result

        monkeypatch.setattr(tool.Path, "stat", trusted_stat)
    else:
        monkeypatch.setattr(tool, "_mode_private", lambda _path: True)
    monkeypatch.setattr(tool, "_require_runtime", lambda: None)
    monkeypatch.setattr(tool, "EXPECTED_FILES", len(files))
    monkeypatch.setattr(tool, "EXPECTED_BYTES", receipt["actual_total_bytes"])
    monkeypatch.setattr(tool, "AUDITED_MANIFEST_SHA256", receipt["manifest_sha256"])
    monkeypatch.setattr(
        tool,
        "EXPECTED_RECEIPT",
        f"ds000030-pilot-acquisition-sha256:{tool._canonical_digest(receipt)}",
    )
    before = {path: (tool._sha256(path), path.stat().st_mtime_ns) for path in files}
    args = SimpleNamespace(
        raw_root=root,
        manifest=manifest_path,
        acquisition_receipt=receipt_path,
        output=output_dir / "report.json",
        docker_executable=docker,
        validator_image=tool.VALIDATOR_IMAGE,
    )
    summary = tool.validate(args, _docker_runner(_validator_result()))
    after = {path: (tool._sha256(path), path.stat().st_mtime_ns) for path in files}
    assert summary["validation_passed"] is True
    assert summary["voxel_arrays_loaded"] == 0
    assert before == after
    report = json.loads(args.output.read_text(encoding="utf-8"))
    assert report["acquisition_manifest_binding_verified"] is True
    if os.name != "nt":
        assert stat.S_IMODE(args.output.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "secret",
    [
        "/home/private/raw/sub-sensitive/file.nii.gz",
        "https://example.invalid/object?X-Amz-Signature=secret",
        "docker run --mount /private/raw",
        r"C:\\Users\\private\\raw\\file.json",
    ],
)
def test_failure_output_and_report_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    secret: str,
) -> None:
    output_dir = tmp_path / "reports"
    output_dir.mkdir(mode=0o700)
    output = output_dir / "blocked.json"
    args = SimpleNamespace(output=output)
    monkeypatch.setattr(tool, "parser", lambda: SimpleNamespace(parse_args=lambda: args))
    monkeypatch.setattr(
        tool,
        "validate",
        lambda _args: (_ for _ in ()).throw(OSError(secret)),
    )
    assert tool.main() == 1
    console = capsys.readouterr().out
    report = output.read_text(encoding="utf-8")
    assert secret not in console and secret not in report
    assert "error_category" in console and "output_write_failed" in report


def test_called_process_error_command_is_sanitized() -> None:
    error = subprocess.CalledProcessError(1, ["docker", "run", "/private/raw"])
    assert tool._error_category(error) == "docker_unavailable"
