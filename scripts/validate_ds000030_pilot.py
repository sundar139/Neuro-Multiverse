#!/usr/bin/env python3
"""Read-only structural validation for the acquired ds000030 pilot."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, cast

import nibabel as nib
import numpy as np

EXPECTED_FILES = 22
EXPECTED_BYTES = 187_570_603
EXPECTED_RECEIPT = (
    "ds000030-pilot-acquisition-sha256:"
    "e2b194394687738f62b199539cdc7acca6627b40fcd6a4fbb45143891b7410ea"
)
TR_TOLERANCE = 1e-4
MAX_JSON_BYTES = 1_000_000
SUBJECT_RE = re.compile(r"^sub-([A-Za-z0-9]+)$")
SECRET_RE = re.compile(
    r"X-Amz-|credential|authorization|password|cookie|token|signature",
    re.IGNORECASE,
)
PRIVATE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/home/|/Users/)")
T1W_RE = re.compile(r"^(sub-[A-Za-z0-9]+)_T1w\.(nii\.gz|json)$")
BOLD_RE = re.compile(r"^(sub-[A-Za-z0-9]+)_task-rest_bold\.(nii\.gz|json)$")


class ValidationError(RuntimeError):
    """A disclosure-safe validation failure."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValidationError("metadata JSON exceeds the size limit")
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise ValidationError("metadata JSON contains NUL")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("metadata JSON is not strict UTF-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValidationError("metadata JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValidationError(f"metadata JSON contains nonfinite value {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ValidationError("metadata JSON is malformed") from exc
    if not isinstance(value, dict):
        raise ValidationError("metadata JSON root is not an object")
    serialized = json.dumps(value, ensure_ascii=False)
    if any(ord(char) < 0x20 and char not in "\t\r\n" for char in serialized):
        raise ValidationError("metadata JSON contains a control character")
    if SECRET_RE.search(serialized) or PRIVATE_PATH_RE.search(serialized):
        raise ValidationError("metadata JSON contains prohibited secret or path material")
    return value


def _read_manifest(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or relative in result
        ):
            raise ValidationError("checksum manifest is malformed")
        result[relative] = digest
    return result


def _mode_private(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) == 0o600


def _snapshot(raw_root: Path, manifest: dict[str, str]) -> dict[str, dict[str, Any]]:
    actual = {
        path.relative_to(raw_root).as_posix(): path
        for path in raw_root.rglob("*")
        if path.is_file()
    }
    if set(actual) != set(manifest):
        raise ValidationError("raw file set differs from the checksum manifest")
    result: dict[str, dict[str, Any]] = {}
    seen_inodes: set[tuple[int, int]] = set()
    for relative, path in actual.items():
        resolved = path.resolve(strict=True)
        if raw_root.resolve() not in resolved.parents:
            raise ValidationError("raw file escapes the raw root")
        if path.is_symlink():
            raise ValidationError("raw file is a symbolic link")
        info = path.stat()
        inode = (info.st_dev, info.st_ino)
        if inode in seen_inodes:
            raise ValidationError("raw files contain a hard-link alias")
        seen_inodes.add(inode)
        digest = _sha256(path)
        if digest != manifest[relative] or info.st_size <= 0:
            raise ValidationError("raw file hash or size differs from the manifest")
        if os.name != "nt" and info.st_mode & 0o077:
            raise ValidationError("raw file permissions are not private")
        result[relative] = {
            "size": info.st_size,
            "sha256": digest,
            "mtime_ns": info.st_mtime_ns,
            "mode": stat.S_IMODE(info.st_mode),
            "inode": info.st_ino,
        }
    return result


def _subject_token(subject: str) -> str:
    value = f"ds000030-validation-v1|{subject}".encode()
    return hashlib.sha256(value).hexdigest()[:12]


def _validate_structure(raw_root: Path) -> dict[str, Any]:
    root_json = {"dataset_description.json", "task-rest_bold.json"}
    root_files = {p.name for p in raw_root.iterdir() if p.is_file()}
    if root_files != root_json:
        raise ValidationError("root metadata file set is incomplete or unexpected")
    subjects = sorted(p for p in raw_root.iterdir() if p.is_dir())
    if len(subjects) != 5 or any(not SUBJECT_RE.fullmatch(p.name) for p in subjects):
        raise ValidationError("subject directory count or naming is invalid")
    details: list[dict[str, Any]] = []
    for subject_dir in subjects:
        subject = subject_dir.name
        anat = subject_dir / "anat"
        func = subject_dir / "func"
        if not anat.is_dir() or not func.is_dir():
            raise ValidationError("subject modality directory is missing")
        anat_files = sorted(p for p in anat.iterdir() if p.is_file())
        func_files = sorted(p for p in func.iterdir() if p.is_file())
        if len(anat_files) != 2 or len(func_files) != 2:
            raise ValidationError("subject file count is invalid")
        t1 = {
            p.suffixes[-2] + p.suffix if p.name.endswith(".nii.gz") else p.suffix: p
            for p in anat_files
        }
        bold = {
            p.suffixes[-2] + p.suffix if p.name.endswith(".nii.gz") else p.suffix: p
            for p in func_files
        }
        if set(t1) != {".nii.gz", ".json"} or set(bold) != {".nii.gz", ".json"}:
            raise ValidationError("image-sidecar pairing is invalid")
        if not all(T1W_RE.fullmatch(p.name) for p in anat_files):
            raise ValidationError("T1w filename is invalid")
        if not all(BOLD_RE.fullmatch(p.name) for p in func_files):
            raise ValidationError("resting-state BOLD filename is invalid")
        if any(not p.name.startswith(subject + "_") for p in anat_files + func_files):
            raise ValidationError("subject filename does not match its directory")
        details.append(
            {
                "subject_token": _subject_token(subject),
                "t1_image": t1[".nii.gz"],
                "t1_sidecar": t1[".json"],
                "bold_image": bold[".nii.gz"],
                "bold_sidecar": bold[".json"],
            }
        )
    return {"subjects": details}


def _validate_metadata(raw_root: Path, structure: dict[str, Any]) -> dict[str, Any]:
    description = _strict_json(raw_root / "dataset_description.json")
    for key in ("Name", "BIDSVersion"):
        if not isinstance(description.get(key), str) or not description[key].strip():
            raise ValidationError("dataset description lacks a required string")
    if str(description.get("DatasetType", "raw")).lower() == "derivative":
        raise ValidationError("dataset is presented as a derivative")
    root_bold = _strict_json(raw_root / "task-rest_bold.json")
    root_tr = root_bold.get("RepetitionTime")
    if root_tr is not None and not _positive_finite(root_tr):
        raise ValidationError("root repetition time is invalid")
    if "TaskName" in root_bold and "rest" not in str(root_bold["TaskName"]).lower():
        raise ValidationError("root task metadata is not resting state")
    parsed = 2
    for item in structure["subjects"]:
        t1 = _strict_json(item["t1_sidecar"])
        direct = _strict_json(item["bold_sidecar"])
        parsed += 2
        for key in set(root_bold) & set(direct):
            if root_bold[key] != direct[key]:
                raise ValidationError("inherited and direct BOLD metadata conflict")
        effective = {**root_bold, **direct}
        tr = effective.get("RepetitionTime")
        if not _positive_finite(tr):
            raise ValidationError("effective repetition time is invalid")
        item["t1_metadata"] = t1
        item["bold_metadata"] = direct
        item["effective_bold_metadata"] = effective
    return {
        "json_files_parsed": parsed,
        "bids_version": description["BIDSVersion"],
        "license": description.get("License"),
    }


def _positive_finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and math.isfinite(value)
    )


def _validate_header(path: Path, expected_dims: int) -> dict[str, Any]:
    try:
        image = cast(nib.Nifti1Image, nib.load(path, mmap=False))
        header = image.header
        shape = tuple(int(value) for value in image.shape)
        zooms = tuple(
            float(value)
            for value in header.get_zooms()  # type: ignore[no-untyped-call]
        )
        affine = np.asarray(image.affine)
    except Exception as exc:
        raise ValidationError("NIfTI header is unreadable") from exc
    if len(shape) != expected_dims or any(value <= 0 for value in shape):
        raise ValidationError("NIfTI dimensionality is invalid")
    if len(zooms) < expected_dims or any(not _positive_finite(v) for v in zooms[:expected_dims]):
        raise ValidationError("NIfTI voxel spacing is invalid")
    if not np.isfinite(affine).all():
        raise ValidationError("NIfTI affine is nonfinite")
    if nib.orientations.aff2axcodes(affine) is None:  # type: ignore[no-untyped-call]
        raise ValidationError("NIfTI orientation is unavailable")
    datatype = header.get_data_dtype()  # type: ignore[no-untyped-call]
    if datatype.itemsize <= 0 or datatype.kind not in "iuIfF":
        raise ValidationError("NIfTI datatype is implausible")
    slope, intercept = header.get_slope_inter()  # type: ignore[no-untyped-call]
    if slope is not None and (not math.isfinite(slope) or slope == 0):
        raise ValidationError("NIfTI scaling slope is invalid")
    if intercept is not None and not math.isfinite(intercept):
        raise ValidationError("NIfTI scaling intercept is invalid")
    qform, qcode = header.get_qform(coded=True)  # type: ignore[no-untyped-call]
    sform, scode = header.get_sform(coded=True)  # type: ignore[no-untyped-call]
    return {
        "shape": shape,
        "zooms": zooms,
        "qform_code": int(qcode),
        "sform_code": int(scode),
        "qform_present": qform is not None,
        "sform_present": sform is not None,
        "orientation": nib.orientations.aff2axcodes(affine),  # type: ignore[no-untyped-call]
        "datatype": str(datatype),
        "free_text_present": any(
            bytes(header[field]).strip(b"\x00 ") for field in ("descrip", "aux_file", "intent_name")
        ),
    }


def _validate_headers(structure: dict[str, Any]) -> dict[str, Any]:
    volumes: list[int] = []
    durations: list[float] = []
    tr_matches = 0
    slice_checks = 0
    gzip_count = 0
    for item in structure["subjects"]:
        t1 = _validate_header(item["t1_image"], 3)
        bold = _validate_header(item["bold_image"], 4)
        effective = item["effective_bold_metadata"]
        tr = float(effective["RepetitionTime"])
        if abs(bold["zooms"][3] - tr) > TR_TOLERANCE:
            raise ValidationError("header and JSON repetition times differ")
        tr_matches += 1
        slice_timing = effective.get("SliceTiming")
        if slice_timing is not None:
            if (
                not isinstance(slice_timing, list)
                or len(slice_timing) != bold["shape"][2]
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < 0
                    or value > tr + TR_TOLERANCE
                    for value in slice_timing
                )
            ):
                raise ValidationError("slice timing is inconsistent")
            slice_checks += 1
        volume_count = bold["shape"][3]
        volumes.append(volume_count)
        durations.append(volume_count * tr)
        item["t1_header"] = t1
        item["bold_header"] = bold
        item["raw_volume_count"] = volume_count
        item["raw_duration_seconds"] = volume_count * tr
        for image_path in (item["t1_image"], item["bold_image"]):
            try:
                with gzip.open(image_path, "rb") as stream:
                    for _ in iter(lambda: stream.read(1024 * 1024), b""):
                        pass
            except (OSError, EOFError) as exc:
                raise ValidationError("gzip stream integrity failed") from exc
            gzip_count += 1
    return {
        "nifti_headers_parsed": 10,
        "t1w_count": 5,
        "bold_count": 5,
        "gzip_validation_count": gzip_count,
        "header_json_tr_consistency_count": tr_matches,
        "slice_timing_consistency_count": slice_checks,
        "slice_timing_present_count": slice_checks,
        "raw_volume_count": _stats(volumes),
        "raw_duration_seconds": _stats(durations),
        "at_least_120_original_volumes": sum(value >= 120 for value in volumes),
        "at_least_240_raw_seconds": sum(value >= 240 for value in durations),
    }


def _stats(values: list[int] | list[float]) -> dict[str, float]:
    return {"minimum": min(values), "median": median(values), "maximum": max(values)}


def _run_validator(
    executable: Path, raw_root: Path, output_path: Path, expected: str | None
) -> dict[str, Any]:
    version_result = subprocess.run(
        [str(executable), "--version"], text=True, capture_output=True, check=True
    )
    version_match = re.search(r"\d+\.\d+\.\d+", version_result.stdout)
    if not version_match:
        raise ValidationError("BIDS Validator version is unavailable")
    version = version_match.group(0)
    if expected is not None and version != expected:
        raise ValidationError("BIDS Validator version differs from the pinned version")
    started = _utc_now()
    result = subprocess.run(
        [str(executable), str(raw_root), "--format", "json"],
        text=True,
        capture_output=True,
    )
    completed = _utc_now()
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(result.stdout)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError("BIDS Validator output is not JSON") from exc
    issue_container = payload.get("issues", {})
    issues = issue_container.get("issues", []) if isinstance(issue_container, dict) else []
    severity = Counter(str(issue.get("severity", "")) for issue in issues)
    codes = Counter(str(issue.get("code", "UNKNOWN")) for issue in issues)
    errors = severity["error"]
    warnings = severity["warning"]
    ignored = severity["ignore"]
    classifications = {
        code: (
            "expected bounded-subset warning"
            if code == "README_FILE_MISSING"
            else "nonblocking recommendation"
        )
        for code in codes
    }
    if result.returncode != 0 or errors:
        raise ValidationError("BIDS Validator reported errors")
    summary = payload.get("summary", {})
    return {
        "name": "BIDS Validator",
        "version": version,
        "schema_version": summary.get("schemaVersion"),
        "started_at_utc": started,
        "completed_at_utc": completed,
        "exit_code": result.returncode,
        "error_count": errors,
        "warning_count": warnings,
        "ignored_count": ignored,
        "issue_code_counts": dict(sorted(codes.items())),
        "warning_classifications": classifications,
        "files_examined": summary.get("totalFiles"),
        "output_sha256": _sha256(output_path),
        "nifti_headers_parsed": True,
    }


def validate(args: argparse.Namespace) -> dict[str, Any]:
    if platform.system() != "Linux" or "microsoft" not in platform.release().lower():
        raise ValidationError("validation requires WSL2 Linux")
    if "24.04" not in Path("/etc/os-release").read_text():
        raise ValidationError("validation requires Ubuntu 24.04")
    raw_root = args.raw_root.resolve(strict=True)
    repository = Path(__file__).resolve().parents[1]
    if repository == raw_root or repository in raw_root.parents or raw_root in repository.parents:
        raise ValidationError("raw root must be outside Git")
    if args.output.resolve().is_relative_to(raw_root):
        raise ValidationError("validation output must be outside the raw tree")
    if not _mode_private(args.manifest) or not _mode_private(args.acquisition_receipt):
        raise ValidationError("external evidence mode is not 600")
    receipt = _strict_json(args.acquisition_receipt)
    if (
        receipt.get("scope") != "ds000030_pilot_5_subjects"
        or receipt.get("actual_final_file_count") != EXPECTED_FILES
        or receipt.get("actual_total_bytes") != EXPECTED_BYTES
        or f"ds000030-pilot-acquisition-sha256:{_canonical_digest(receipt)}" != EXPECTED_RECEIPT
    ):
        raise ValidationError("acquisition receipt does not match approved evidence")
    manifest = _read_manifest(args.manifest)
    if len(manifest) != EXPECTED_FILES:
        raise ValidationError("manifest entry count is not 22")
    pre = _snapshot(raw_root, manifest)
    if sum(item["size"] for item in pre.values()) != EXPECTED_BYTES:
        raise ValidationError("raw byte total differs from acquisition evidence")
    started = _utc_now()
    structure = _validate_structure(raw_root)
    metadata = _validate_metadata(raw_root, structure)
    validator_output = args.output.with_suffix(".validator.json")
    validator = _run_validator(
        args.bids_validator,
        raw_root,
        validator_output,
        args.bids_validator_version,
    )
    headers = _validate_headers(structure)
    post = _snapshot(raw_root, manifest)
    changed = sum(pre[key] != post[key] for key in pre)
    if changed:
        raise ValidationError("raw files changed during validation")
    completed = _utc_now()
    report: dict[str, Any] = {
        "schema_version": "1",
        "validation_started_at_utc": started,
        "validation_completed_at_utc": completed,
        "git_commit": subprocess.run(
            [shutil.which("git") or "git", "rev-parse", "HEAD"],
            cwd=repository,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip(),
        "acquisition_receipt_reference": EXPECTED_RECEIPT,
        "raw_root_identity_sha256": hashlib.sha256(str(raw_root).encode()).hexdigest(),
        "validator": validator,
        "validated_final_file_count": len(post),
        "validated_total_bytes": sum(value["size"] for value in post.values()),
        "manifest_sha256": _sha256(args.manifest),
        "pre_validation_manifest_matches": True,
        "post_validation_manifest_matches": True,
        "json_files_parsed": metadata["json_files_parsed"],
        "declared_bids_version": metadata["bids_version"],
        "nifti_headers_parsed": headers["nifti_headers_parsed"],
        "t1w_count": headers["t1w_count"],
        "bold_count": headers["bold_count"],
        "direct_sidecar_count": 10,
        "gzip_validation_count": headers["gzip_validation_count"],
        "header_json_tr_consistency_count": headers["header_json_tr_consistency_count"],
        "slice_timing_consistency_count": headers["slice_timing_consistency_count"],
        "slice_timing_present_count": headers["slice_timing_present_count"],
        "raw_volume_count": headers["raw_volume_count"],
        "raw_duration_seconds": headers["raw_duration_seconds"],
        "at_least_120_original_volumes": headers["at_least_120_original_volumes"],
        "at_least_240_raw_seconds": headers["at_least_240_raw_seconds"],
        "duplicate_path_count": 0,
        "unexpected_file_count": 0,
        "changed_file_count": changed,
        "voxel_arrays_loaded": 0,
        "raw_files_modified": 0,
        "validation_decision": "passed",
        "blocking_issues": [],
    }
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    digest = _canonical_digest(report)
    return {
        "mode": "read-only-validation",
        "validation_passed": True,
        "files_validated": len(post),
        "bytes_validated": report["validated_total_bytes"],
        "validator_version": validator["version"],
        "bids_schema_version": validator["schema_version"],
        "validator_errors": validator["error_count"],
        "validator_warnings": validator["warning_count"],
        "nifti_headers_parsed": headers["nifti_headers_parsed"],
        "voxel_arrays_loaded": 0,
        "changed_files": changed,
        "validation_report_sha256": digest,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--raw-root", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--acquisition-receipt", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--bids-validator", type=Path, required=True)
    result.add_argument("--bids-validator-version")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        summary = validate(args)
    except (OSError, subprocess.SubprocessError, ValidationError) as exc:
        failure = {
            "schema_version": "1",
            "validation_completed_at_utc": _utc_now(),
            "validation_decision": "blocked",
            "blocking_issues": [str(exc)],
            "voxel_arrays_loaded": 0,
            "raw_files_modified": 0,
        }
        if not args.output.exists():
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(failure, indent=2, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        print(
            json.dumps(
                {
                    "validation_passed": False,
                    "problem": str(exc),
                    "validation_report_sha256": _canonical_digest(failure),
                }
            )
        )
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
