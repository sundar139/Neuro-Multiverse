#!/usr/bin/env python3
"""Read-only structural validation for the acquired ds000030 pilot."""

from __future__ import annotations

import argparse
import dataclasses
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
import urllib.parse
from collections import Counter
from collections.abc import Callable, Sequence
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
AUDITED_MANIFEST_SHA256 = "32772c890a8aacbf23b8464cca9b458cb65d2e5a5d68570320ca5e62102de2b2"
TR_TOLERANCE = 1e-4
MAX_JSON_BYTES = 1_000_000
MAX_JSON_DEPTH = 20
MAX_JSON_KEY_LENGTH = 256
MAX_JSON_STRING_LENGTH = 100_000
VALIDATOR_IMAGE = (
    "bids/validator@sha256:8ef7bf22a5e62430c98c0f3e62627f400c62e85c20db3f691e370ddfdc9963c7"
)
VALIDATOR_VERSION = "3.0.0"
VALIDATOR_SCHEMA = "1.2.4"
VALIDATOR_ARCHITECTURE = "amd64"
DOCKER_COMMAND_POLICY_VERSION = "2"
REVIEWED_DOCKER_COMMAND = Path("/usr/bin/docker")
REVIEWED_DOCKER_CANONICAL = Path("/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker")
REVIEWED_DOCKER_CLI_SHA256 = "36fe758b39961505c5edc1c9675f1af18166103454fcd21db5255d381ce540d8"
REVIEWED_DOCKER_CLI_VERSION = "29.5.3"
REVIEWED_DOCKER_ENGINE_VERSION = "29.5.3"
REVIEWED_DOCKER_API_VERSION = "1.54"
REVIEWED_DOCKER_CONTEXT = "default"
REVIEWED_DOCKER_PROVENANCE = "trusted_docker_desktop_wsl_cli"
REVIEWED_DOCKER_GROUP = "root"
REVIEWED_DOCKER_MOUNT = Path("/mnt/wsl/docker-desktop/cli-tools")
REVIEWED_DOCKER_FILESYSTEM = "iso9660"
REVIEWED_DOCKER_ENDPOINT = "unix:///var/run/docker.sock"
REVIEWED_DOCKER_SOCKET = Path("/var/run/docker.sock")
REVIEWED_DOCKER_SOCKET_CANONICAL = Path("/run/docker.sock")
REVIEWED_DOCKER_SOCKET_UID = 0
REVIEWED_DOCKER_SOCKET_GID = 1001
REVIEWED_DOCKER_SOCKET_MODE = 0o660
REVIEWED_DOCKER_SOCKET_MOUNT = Path("/run")
REVIEWED_DOCKER_SOCKET_FILESYSTEM = "tmpfs"
REVIEWED_DOCKER_SERVER_NAME = "docker-desktop"
REVIEWED_DOCKER_SERVER_OS = "Docker Desktop"
REVIEWED_DOCKER_CONFIG = Path("/run/neuromultiverse-empty-docker-config")
DOCKER_ENVIRONMENT_POLICY_VERSION = "1"
PROHIBITED_DOCKER_ENV = frozenset(
    {
        "DOCKER_API_VERSION",
        "DOCKER_CERT_PATH",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "DOCKER_CUSTOM_HEADERS",
        "DOCKER_DEFAULT_PLATFORM",
        "DOCKER_HOST",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
    }
)
ERROR_CATEGORIES = frozenset(
    {
        "runtime_unsupported",
        "evidence_permission_invalid",
        "receipt_invalid",
        "manifest_binding_invalid",
        "manifest_invalid",
        "raw_permission_invalid",
        "raw_integrity_invalid",
        "structure_invalid",
        "metadata_invalid",
        "header_invalid",
        "docker_untrusted",
        "docker_unavailable",
        "image_missing",
        "image_digest_mismatch",
        "validator_version_mismatch",
        "validator_output_invalid",
        "validator_errors",
        "validator_warning_unclassified",
        "raw_changed",
        "output_write_failed",
    }
)
WARNING_CLASSIFICATIONS = {
    "JSON_KEY_RECOMMENDED": "nonblocking recommendation",
    "SIDECAR_KEY_RECOMMENDED": "nonblocking recommendation",
    "README_FILE_MISSING": "expected bounded-subset warning",
}
PROHIBITED_METADATA_KEYS = {
    "patientname",
    "patientid",
    "patientbirthdate",
    "patientaddress",
    "medicalrecordnumber",
    "participantid",
}
SUBJECT_RE = re.compile(r"^sub-([A-Za-z0-9]+)$")
SECRET_RE = re.compile(
    r"X-Amz-|credential|authorization|password|cookie|token|signature",
    re.IGNORECASE,
)
# Complete public HTTP(S) URI spans are recognized and validated as a unit
# before any local-filesystem-path classification runs. A Windows drive
# letter class such as ``[A-Za-z]:[\\/]`` is applied only to the
# residual text AFTER public URI spans are removed, never to the ``s:/``
# inside ``https://``.
URL_RE = re.compile(r"https?://[^\s'\"]+", re.IGNORECASE)
# Residual text after public HTTP(S) URI spans are removed: any remaining
# scheme, Windows/UNC/POSIX/user/home-relative path, or local file URI is
# rejected.
RESIDUAL_FORBIDDEN_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]"  # Windows drive path
    r"|\\{2,}[^\\/\s]+\\[^\\/\s]+"  # UNC path
    r"|/home/|/Users/"  # POSIX user paths
    r"|/mnt/[a-z]/Users/"  # WSL-mounted user path
    r"|~/"  # home-relative path
    r"|://"  # non-http(s) scheme (file://, ...)
    r"|file:)"  # file: scheme
)
T1W_RE = re.compile(r"^(sub-[A-Za-z0-9]+)_T1w\.(nii\.gz|json)$")
BOLD_RE = re.compile(r"^(sub-[A-Za-z0-9]+)_task-rest_bold\.(nii\.gz|json)$")


class ValidationError(RuntimeError):
    """A disclosure-safe validation failure."""


@dataclasses.dataclass(frozen=True)
class DockerCliIdentity:
    """Security-relevant identity checked around every Docker subprocess."""

    command: str
    canonical: str
    command_device: int
    command_inode: int
    command_uid: int
    command_gid: int
    command_mode: int
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    size: int
    mtime_ns: int
    digest: str
    mount_point: str
    mount_source: str
    filesystem: str


@dataclasses.dataclass(frozen=True)
class DockerEndpointIdentity:
    """Local endpoint identity compared around each Docker subprocess."""

    endpoint: str
    command_path: str
    canonical_path: str
    symlink_chain: tuple[tuple[str, str, int, int, int, int, int], ...]
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    mount_point: str
    mount_source: str
    filesystem: str


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


def _validate_public_url(url: str) -> None:
    """Accept a well-formed public HTTP(S) reference; reject everything else."""
    if SECRET_RE.search(url):
        raise ValidationError("metadata JSON contains prohibited secret or credential material")
    if "\x00" in url or any(ord(char) < 0x20 for char in url):
        raise ValidationError("metadata JSON contains a malformed URI")
    parsed = urllib.parse.urlsplit(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValidationError("metadata JSON contains a prohibited URI scheme")
    if not parsed.netloc:
        raise ValidationError("metadata JSON contains a malformed URI")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("metadata JSON contains a prohibited URI userinfo")


def _validate_residual_text(text: str) -> None:
    """Reject remaining local paths, file URIs, and non-HTTP(S) schemes."""
    if RESIDUAL_FORBIDDEN_RE.search(text):
        raise ValidationError("metadata JSON contains prohibited secret or path material")


def _validate_metadata_text(text: str) -> None:
    """Classify decoded JSON strings: public URLs pass, local paths fail."""
    if SECRET_RE.search(text):
        raise ValidationError("metadata JSON contains prohibited secret or credential material")
    parts: list[str] = []
    last = 0
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(".,);:]\"'")
        _validate_public_url(url)
        parts.append(text[last : match.start()])
        parts.append(" ")
        last = match.end()
    parts.append(text[last:])
    _validate_residual_text("".join(parts))


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

    def inspect(decoded: Any, depth: int = 0) -> None:
        if depth > MAX_JSON_DEPTH:
            raise ValidationError("metadata JSON nesting is excessive")
        if isinstance(decoded, dict):
            for key, item in decoded.items():
                if len(key) > MAX_JSON_KEY_LENGTH:
                    raise ValidationError("metadata JSON key is excessively long")
                if key.casefold() in PROHIBITED_METADATA_KEYS:
                    raise ValidationError("metadata JSON contains a prohibited participant field")
                inspect(key, depth + 1)
                inspect(item, depth + 1)
        elif isinstance(decoded, list):
            for item in decoded:
                inspect(item, depth + 1)
        elif isinstance(decoded, str):
            if len(decoded) > MAX_JSON_STRING_LENGTH:
                raise ValidationError("metadata JSON string is excessively long")
            if any(
                ord(char) == 0
                or (ord(char) < 0x20 and char not in "\t\r\n")
                or ord(char) == 0x7F
                or 0xD800 <= ord(char) <= 0xDFFF
                for char in decoded
            ):
                raise ValidationError("metadata JSON contains a prohibited character")
            _validate_metadata_text(decoded)

    inspect(value)
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


def _require_owner(path: Path) -> None:
    geteuid = getattr(os, "geteuid", None)
    if os.name != "nt" and geteuid is not None and path.stat().st_uid != geteuid():
        raise ValidationError("external path owner is not the current user")


def _require_private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValidationError("private directory is missing or symbolic")
    _require_owner(path)
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ValidationError("private directory mode is not 700")


def _require_private_evidence_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValidationError("external evidence is missing or symbolic")
    _require_owner(path)
    if not _mode_private(path):
        raise ValidationError("external evidence mode is not 600")


def _validate_private_tree(raw_root: Path) -> None:
    _require_private_directory(raw_root)
    for directory in raw_root.iterdir():
        if directory.is_dir():
            _require_private_directory(directory)
            for child in directory.iterdir():
                if child.is_dir():
                    _require_private_directory(child)


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
        _require_owner(path)
        if os.name != "nt" and stat.S_IMODE(info.st_mode) != 0o600:
            raise ValidationError("raw file mode is not 600")
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
    if "License" in description and str(description["License"]).casefold() not in {
        "cc0",
        "cc0-1.0",
    }:
        raise ValidationError("dataset license differs from the verified record")
    root_bold = _strict_json(raw_root / "task-rest_bold.json")
    root_tr = root_bold.get("RepetitionTime")
    if root_tr is not None and not _positive_finite(root_tr):
        raise ValidationError("root repetition time is invalid")
    if "TaskName" in root_bold and "rest" not in str(root_bold["TaskName"]).lower():
        raise ValidationError("root task metadata is not resting state")
    parsed = 2
    effective_trs: list[float] = []
    for item in structure["subjects"]:
        t1 = _strict_json(item["t1_sidecar"])
        direct = _strict_json(item["bold_sidecar"])
        parsed += 2
        effective = {**root_bold, **direct}
        tr = effective.get("RepetitionTime")
        if not _positive_finite(tr):
            raise ValidationError("effective repetition time is invalid")
        effective_trs.append(float(cast(float, tr)))
        item["t1_metadata"] = t1
        item["bold_metadata"] = direct
        item["effective_bold_metadata"] = effective
    if max(effective_trs) - min(effective_trs) > TR_TOLERANCE:
        raise ValidationError("effective repetition times differ across the controlled pilot")
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
    orientation = nib.orientations.aff2axcodes(affine)  # type: ignore[no-untyped-call]
    if any(code is None for code in orientation):
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
        "orientation": orientation,
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
    free_text_count = 0
    for item in structure["subjects"]:
        t1 = _validate_header(item["t1_image"], 3)
        bold = _validate_header(item["bold_image"], 4)
        free_text_count += int(t1["free_text_present"]) + int(bold["free_text_present"])
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
        "header_free_text_count": free_text_count,
        "raw_volume_count": _stats(volumes),
        "raw_duration_seconds": _stats(durations),
        "at_least_120_original_volumes": sum(value >= 120 for value in volumes),
        "at_least_240_raw_seconds": sum(value >= 240 for value in durations),
    }


def _stats(values: list[int] | list[float]) -> dict[str, float]:
    return {"minimum": min(values), "median": median(values), "maximum": max(values)}


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _docker_base_policy_args() -> list[str]:
    uid = getattr(os, "geteuid", lambda: 0)()
    gid = getattr(os, "getegid", lambda: 0)()
    return [
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user",
        f"{uid}:{gid}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108 - container-only tmpfs
    ]


def _docker_dataset_policy_args(raw_root: Path) -> list[str]:
    return [
        *_docker_base_policy_args(),
        "--mount",
        f"type=bind,src={raw_root},dst=/data,readonly",
    ]


def _effective_write(path: Path) -> bool:
    try:
        return os.access(path, os.W_OK, effective_ids=True)
    except TypeError:  # pragma: no cover - POSIX supports effective_ids
        return os.access(path, os.W_OK)


def _replacement_writable(path: Path) -> bool:
    """Whether the current user can replace any existing component of *path*."""
    if os.name == "nt" or not path.is_absolute():
        return True
    euid = os.geteuid()  # type: ignore[attr-defined]
    parts = path.parts
    for index in range(1, len(parts)):
        parent = Path(*parts[:index])
        child = Path(*parts[: index + 1])
        try:
            writable = os.access(parent, os.W_OK | os.X_OK, effective_ids=True)
            parent_info = parent.stat()
            child_info = child.lstat()
        except OSError:
            return True
        if not writable:
            continue
        sticky_protects = bool(parent_info.st_mode & stat.S_ISVTX) and euid not in {
            0,
            parent_info.st_uid,
            child_info.st_uid,
        }
        if not sticky_protects:
            return True
    return False


def _mount_provenance(path: Path) -> tuple[str, str, str, frozenset[str]]:
    best: tuple[str, str, str, frozenset[str]] | None = None
    best_length = -1
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        separator = fields.index("-")
        mount_point = fields[4].replace("\\040", " ")
        mounted = Path(mount_point)
        if path != mounted and mounted not in path.parents:
            continue
        if len(mount_point) <= best_length:
            continue
        options = frozenset((*fields[5].split(","), *fields[separator + 3].split(",")))
        best = (mount_point, fields[separator + 2], fields[separator + 1], options)
        best_length = len(mount_point)
    if best is None:
        raise ValidationError("Docker CLI mount provenance is unavailable")
    return best


def _path_symlink_chain(path: Path) -> tuple[tuple[str, str, int, int, int, int, int], ...]:
    chain: list[tuple[str, str, int, int, int, int, int]] = []
    for index in range(1, len(path.parts) + 1):
        component = Path(*path.parts[:index])
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode):
            chain.append(
                (
                    str(component),
                    str(component.readlink()),
                    info.st_dev,
                    info.st_ino,
                    info.st_uid,
                    info.st_gid,
                    stat.S_IMODE(info.st_mode),
                )
            )
    return tuple(chain)


def _trusted_docker_environment(parent: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if parent is None else parent
    if any(name.startswith("DOCKER_") for name in source):
        raise ValidationError("prohibited Docker environment override is present")
    return {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _docker_global_args() -> list[str]:
    return [
        "--config",
        str(REVIEWED_DOCKER_CONFIG),
        "--host",
        REVIEWED_DOCKER_ENDPOINT,
    ]


def _validate_endpoint_evidence(
    identity: DockerEndpointIdentity,
    *,
    socket_is_socket: bool,
    replacement_writable: bool,
    mount_options: frozenset[str],
) -> None:
    if identity.endpoint != REVIEWED_DOCKER_ENDPOINT:
        raise ValidationError("Docker endpoint differs from reviewed evidence")
    if Path(identity.command_path) != REVIEWED_DOCKER_SOCKET:
        raise ValidationError("Docker socket path differs from reviewed evidence")
    if Path(identity.canonical_path) != REVIEWED_DOCKER_SOCKET_CANONICAL:
        raise ValidationError("Docker socket canonical path differs from reviewed evidence")
    if not socket_is_socket:
        raise ValidationError("Docker endpoint is not a Unix-domain socket")
    reviewed_links = tuple(
        (path, target, uid, gid, mode)
        for path, target, _device, _inode, uid, gid, mode in identity.symlink_chain
    )
    if reviewed_links != (("/var/run", "/run", 0, 0, 0o777),):
        raise ValidationError("Docker socket symlink chain differs from reviewed evidence")
    if (identity.uid, identity.gid, identity.mode) != (
        REVIEWED_DOCKER_SOCKET_UID,
        REVIEWED_DOCKER_SOCKET_GID,
        REVIEWED_DOCKER_SOCKET_MODE,
    ):
        raise ValidationError("Docker socket ownership or mode differs from reviewed evidence")
    if replacement_writable:
        raise ValidationError("Docker socket can be replaced through its parent chain")
    if (
        Path(identity.mount_point) != REVIEWED_DOCKER_SOCKET_MOUNT
        or identity.filesystem != REVIEWED_DOCKER_SOCKET_FILESYSTEM
        or identity.mount_source != "none"
        or not {"rw", "nosuid", "nodev"}.issubset(mount_options)
    ):
        raise ValidationError("Docker socket mount provenance differs from reviewed evidence")


def _docker_endpoint_identity() -> DockerEndpointIdentity:
    parsed = urllib.parse.urlsplit(REVIEWED_DOCKER_ENDPOINT)
    if parsed.scheme != "unix" or parsed.netloc or not parsed.path.startswith("/"):
        raise ValidationError("reviewed Docker endpoint is not an absolute Unix endpoint")
    repository = Path(__file__).resolve().parents[1]
    home = Path.home().resolve()
    command = Path(parsed.path)
    try:
        canonical = command.resolve(strict=True)
        info = canonical.stat()
        symlinks = _path_symlink_chain(command)
    except OSError as exc:
        raise ValidationError("Docker endpoint provenance is unavailable") from exc
    if repository in canonical.parents or home in canonical.parents:
        raise ValidationError("Docker endpoint resolves inside a private mutable path")
    mount_point, mount_source, filesystem, options = _mount_provenance(canonical)
    identity = DockerEndpointIdentity(
        endpoint=REVIEWED_DOCKER_ENDPOINT,
        command_path=str(command),
        canonical_path=str(canonical),
        symlink_chain=symlinks,
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.S_IMODE(info.st_mode),
        mount_point=mount_point,
        mount_source=mount_source,
        filesystem=filesystem,
    )
    _validate_endpoint_evidence(
        identity,
        socket_is_socket=stat.S_ISSOCK(info.st_mode),
        replacement_writable=_replacement_writable(command) or _replacement_writable(canonical),
        mount_options=options,
    )
    return identity


def _docker_group_is_trusted(gid: int) -> bool:
    try:
        import grp
        import pwd

        group = grp.getgrgid(gid)  # type: ignore[attr-defined]
        current_groups = set(os.getgroups()) | {  # type: ignore[attr-defined]
            os.getgid()  # type: ignore[attr-defined]
        }
        member_uids = {
            pwd.getpwnam(member).pw_uid  # type: ignore[attr-defined]
            for member in group.gr_mem
            if member
        } | {
            entry.pw_uid
            for entry in pwd.getpwall()  # type: ignore[attr-defined]
            if entry.pw_gid == gid
        }
    except (ImportError, KeyError, OSError):
        return False
    return _group_membership_trusted(gid, group.gr_name, current_groups, member_uids)


def _group_membership_trusted(
    gid: int, name: str, current_groups: set[int], member_uids: set[int]
) -> bool:
    return (
        gid == 0
        and name == REVIEWED_DOCKER_GROUP
        and gid not in current_groups
        and all(uid == 0 for uid in member_uids)
    )


def _validate_docker_evidence(
    identity: DockerCliIdentity,
    *,
    command_is_symlink: bool,
    group_trusted: bool,
    effective_write: bool,
    replacement_writable: bool,
    mount_options: frozenset[str],
) -> None:
    if Path(identity.command) != REVIEWED_DOCKER_COMMAND:
        raise ValidationError("Docker CLI command path differs from reviewed provenance")
    if Path(identity.canonical) != REVIEWED_DOCKER_CANONICAL:
        raise ValidationError("Docker CLI canonical path differs from reviewed provenance")
    if not command_is_symlink or identity.command_uid != 0:
        raise ValidationError("Docker CLI symlink provenance is unsafe")
    if identity.uid != 0 or identity.mode & 0o002:
        raise ValidationError("Docker CLI ownership or world-write mode is unsafe")
    if identity.mode & 0o020 and not group_trusted:
        raise ValidationError("Docker CLI group-write provenance is unsafe")
    if effective_write:
        raise ValidationError("Docker CLI is effectively writable by the validation user")
    if replacement_writable:
        raise ValidationError("Docker CLI can be replaced through its parent chain")
    if (
        Path(identity.mount_point) != REVIEWED_DOCKER_MOUNT
        or identity.filesystem != REVIEWED_DOCKER_FILESYSTEM
        or "ro" not in mount_options
        or not re.fullmatch(r"/dev/loop[0-9]+", identity.mount_source)
    ):
        raise ValidationError("Docker CLI mount provenance differs from reviewed evidence")
    if identity.digest != REVIEWED_DOCKER_CLI_SHA256:
        raise ValidationError("Docker CLI digest differs from reviewed evidence")


def _docker_identity(asserted: Path | None = None) -> DockerCliIdentity:
    """Resolve and validate the reviewed Docker Desktop WSL CLI provenance."""
    if os.name == "nt":
        raise ValidationError("trusted Docker CLI requires WSL2")
    resolved_name = shutil.which("docker")
    if not resolved_name:
        raise ValidationError("trusted Docker CLI is unavailable")
    command = Path(resolved_name)
    try:
        command_info = command.lstat()
        docker = command.resolve(strict=True)
    except OSError as exc:
        raise ValidationError("Docker CLI provenance is unavailable") from exc
    if asserted is not None:
        try:
            asserted_docker = asserted.resolve(strict=True)
        except OSError as exc:
            raise ValidationError("supplied Docker path is unavailable") from exc
        if asserted_docker != docker:
            raise ValidationError("supplied Docker path differs from the trusted CLI")
    info = docker.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValidationError("Docker CLI canonical target is not a regular file")
    mode = stat.S_IMODE(info.st_mode)
    mount_point, mount_source, filesystem, options = _mount_provenance(docker)
    digest = _sha256(docker)
    identity = DockerCliIdentity(
        command=str(command),
        canonical=str(docker),
        command_device=command_info.st_dev,
        command_inode=command_info.st_ino,
        command_uid=command_info.st_uid,
        command_gid=command_info.st_gid,
        command_mode=stat.S_IMODE(command_info.st_mode),
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=mode,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        digest=digest,
        mount_point=mount_point,
        mount_source=mount_source,
        filesystem=filesystem,
    )
    _validate_docker_evidence(
        identity,
        command_is_symlink=stat.S_ISLNK(command_info.st_mode),
        group_trusted=_docker_group_is_trusted(info.st_gid),
        effective_write=_effective_write(docker),
        replacement_writable=_replacement_writable(command) or _replacement_writable(docker),
        mount_options=options,
    )
    return identity


def _trusted_docker(asserted: Path | None = None) -> Path:
    return Path(_docker_identity(asserted).canonical)


def _run_captured(
    runner: CommandRunner, command: Sequence[str], *, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


DockerIdentityProvider = Callable[[Path | None], DockerCliIdentity]
DockerEndpointProvider = Callable[[], DockerEndpointIdentity]


def _run_trusted_docker(
    docker: Path,
    arguments: Sequence[str],
    runner: CommandRunner,
    *,
    check: bool = False,
    identity_provider: DockerIdentityProvider | None = None,
    endpoint_provider: DockerEndpointProvider | None = None,
    environment_provider: Callable[[], dict[str, str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    identity_provider = identity_provider or _docker_identity
    endpoint_provider = endpoint_provider or _docker_endpoint_identity
    environment_provider = environment_provider or _trusted_docker_environment
    environment = environment_provider()
    if environment != {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}:
        raise ValidationError("Docker subprocess environment differs from trusted policy")
    before_cli = identity_provider(docker)
    before_endpoint = endpoint_provider()
    command = [str(docker), *_docker_global_args(), *arguments]
    result: subprocess.CompletedProcess[str] | None = None
    runner_error: BaseException | None = None
    try:
        result = _run_captured(runner, command, environment=environment)
    except Exception as exc:  # post-checks must run even after runner failure
        runner_error = exc
    after_cli = identity_provider(docker)
    after_endpoint = endpoint_provider()
    if before_cli != after_cli:
        raise ValidationError("Docker CLI identity changed during command execution")
    if before_endpoint != after_endpoint:
        raise ValidationError("Docker endpoint identity changed during command execution")
    if runner_error is not None:
        raise ValidationError("Docker command execution failed") from runner_error
    if result is None:  # pragma: no cover - defensive invariant
        raise ValidationError("Docker command produced no result")
    if check and result.returncode != 0:
        raise ValidationError("Docker command exited unsuccessfully")
    return result


def _verify_docker_cli_version(
    docker: Path,
    runner: CommandRunner,
    identity_provider: DockerIdentityProvider | None = None,
    endpoint_provider: DockerEndpointProvider | None = None,
    environment_provider: Callable[[], dict[str, str]] | None = None,
) -> None:
    try:
        result = _run_trusted_docker(
            docker,
            ["version", "--format", "{{.Client.Version}}"],
            runner,
            identity_provider=identity_provider,
            endpoint_provider=endpoint_provider,
            environment_provider=environment_provider,
        )
    except subprocess.SubprocessError as exc:
        raise ValidationError("Docker CLI version is unavailable") from exc
    if result.returncode != 0 or result.stdout.strip() != REVIEWED_DOCKER_CLI_VERSION:
        raise ValidationError("Docker CLI version differs from reviewed evidence")


def _verify_docker_backend(
    docker: Path,
    runner: CommandRunner,
    identity_provider: DockerIdentityProvider | None = None,
    endpoint_provider: DockerEndpointProvider | None = None,
    environment_provider: Callable[[], dict[str, str]] | None = None,
) -> None:
    template = (
        '{"client":"{{.Client.Version}}","server":"{{.Server.Version}}",'
        '"client_api":"{{.Client.APIVersion}}","server_api":"{{.Server.APIVersion}}",'
        '"os":"{{.Server.Os}}","arch":"{{.Server.Arch}}"}'
    )
    try:
        version = _run_trusted_docker(
            docker,
            ["version", "--format", template],
            runner,
            identity_provider=identity_provider,
            endpoint_provider=endpoint_provider,
            environment_provider=environment_provider,
        )
        context = _run_trusted_docker(
            docker,
            [
                "context",
                "inspect",
                REVIEWED_DOCKER_CONTEXT,
                "--format",
                "{{json .Endpoints.docker.Host}}",
            ],
            runner,
            identity_provider=identity_provider,
            endpoint_provider=endpoint_provider,
            environment_provider=environment_provider,
        )
        info = _run_trusted_docker(
            docker,
            [
                "info",
                "--format",
                '{"name":{{json .Name}},"operating_system":{{json .OperatingSystem}},'
                '"architecture":{{json .Architecture}},'
                '"security_options":{{json .SecurityOptions}}}',
            ],
            runner,
            identity_provider=identity_provider,
            endpoint_provider=endpoint_provider,
            environment_provider=environment_provider,
        )
        details = json.loads(version.stdout)
        context_endpoint = json.loads(context.stdout)
        server = json.loads(info.stdout)
    except (json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise ValidationError("Docker backend provenance is unavailable") from exc
    if (
        version.returncode != 0
        or context.returncode != 0
        or info.returncode != 0
        or details
        != {
            "client": REVIEWED_DOCKER_CLI_VERSION,
            "server": REVIEWED_DOCKER_ENGINE_VERSION,
            "client_api": REVIEWED_DOCKER_API_VERSION,
            "server_api": REVIEWED_DOCKER_API_VERSION,
            "os": "linux",
            "arch": VALIDATOR_ARCHITECTURE,
        }
        or context_endpoint != REVIEWED_DOCKER_ENDPOINT
        or server.get("name") != REVIEWED_DOCKER_SERVER_NAME
        or server.get("operating_system") != REVIEWED_DOCKER_SERVER_OS
        or server.get("architecture") != "x86_64"
        or not isinstance(server.get("security_options"), list)
        or any("rootless" in str(value).casefold() for value in server["security_options"])
    ):
        raise ValidationError("Docker backend provenance differs from reviewed evidence")


def _inspect_validator_image(
    docker: Path,
    image: str,
    runner: CommandRunner,
    identity_provider: DockerIdentityProvider | None = None,
    endpoint_provider: DockerEndpointProvider | None = None,
    environment_provider: Callable[[], dict[str, str]] | None = None,
) -> dict[str, Any]:
    if image != VALIDATOR_IMAGE or "@sha256:" not in image or image.endswith(":latest"):
        raise ValidationError("validator image is not the exact pinned digest")
    try:
        info_result = _run_trusted_docker(
            docker,
            ["info"],
            runner,
            identity_provider=identity_provider,
            endpoint_provider=endpoint_provider,
            environment_provider=environment_provider,
        )
    except subprocess.SubprocessError as exc:
        raise ValidationError("Docker daemon is unavailable") from exc
    if info_result.returncode != 0:
        raise ValidationError("Docker daemon is unavailable")
    try:
        result = _run_trusted_docker(
            docker,
            ["image", "inspect", image],
            runner,
            identity_provider=identity_provider,
            endpoint_provider=endpoint_provider,
            environment_provider=environment_provider,
        )
    except subprocess.SubprocessError as exc:
        raise ValidationError("validator image is missing") from exc
    if result.returncode != 0:
        raise ValidationError("validator image is missing")
    try:
        inspected = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError("Docker image inspection is malformed") from exc
    if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
        raise ValidationError("Docker image inspection is malformed")
    details = inspected[0]
    digests = details.get("RepoDigests")
    if not isinstance(digests, list) or VALIDATOR_IMAGE not in digests:
        raise ValidationError("local validator image digest does not match")
    if details.get("Architecture") != VALIDATOR_ARCHITECTURE:
        raise ValidationError("validator image architecture is unsupported")
    if details.get("Os") != "linux":
        raise ValidationError("validator image operating system is unsupported")
    return details


def _parse_validator_result(stdout: str, returncode: int) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError("BIDS Validator output is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("BIDS Validator output root is not an object")
    if any(key in payload for key in ("derivatives", "derivativeSummary", "derivativesSummary")):
        raise ValidationError("BIDS Validator output contains a derivative summary")
    issue_container = payload.get("issues")
    if not isinstance(issue_container, dict):
        raise ValidationError("BIDS Validator issues structure is malformed")
    issues = issue_container.get("issues")
    if not isinstance(issues, list):
        raise ValidationError("BIDS Validator issue list is missing")
    severity: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValidationError("BIDS Validator issue is malformed")
        level = issue.get("severity")
        code = issue.get("code")
        if level not in {"error", "warning", "ignore"}:
            raise ValidationError("BIDS Validator issue severity is malformed")
        if not isinstance(code, str) or not code.strip():
            raise ValidationError("BIDS Validator issue code is malformed")
        severity[level] += 1
        codes[code] += 1
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValidationError("BIDS Validator summary is missing")
    total_files = summary.get("totalFiles")
    schema = summary.get("schemaVersion")
    if isinstance(total_files, bool) or not isinstance(total_files, int):
        raise ValidationError("BIDS Validator file count is malformed")
    if total_files != EXPECTED_FILES:
        raise ValidationError("BIDS Validator file count is not 22")
    if not isinstance(schema, str) or schema != VALIDATOR_SCHEMA:
        raise ValidationError("BIDS Validator schema version differs from the pinned version")
    if summary.get("subjectMetadata") not in (None, {}, []):
        raise ValidationError("BIDS Validator exposed subject metadata")
    for container in (issue_container, summary):
        for key, level in (
            ("errorCount", "error"),
            ("warningCount", "warning"),
            ("ignoredCount", "ignore"),
        ):
            if key in container and container[key] != severity[level]:
                raise ValidationError("BIDS Validator aggregate issue counts differ")
    warning_codes = {issue["code"] for issue in issues if issue["severity"] == "warning"}
    unknown = sorted(warning_codes - WARNING_CLASSIFICATIONS.keys())
    if unknown:
        raise ValidationError("BIDS Validator reported an unclassified warning")
    if returncode != 0 or severity["error"]:
        raise ValidationError("BIDS Validator reported errors")
    if severity["ignore"]:
        raise ValidationError("BIDS Validator reported ignored issues")
    return {
        "schema_version": schema,
        "error_count": severity["error"],
        "warning_count": severity["warning"],
        "ignored_count": severity["ignore"],
        "issue_code_counts": dict(sorted(codes.items())),
        "warning_classifications": {
            code: WARNING_CLASSIFICATIONS[code] for code in sorted(warning_codes)
        },
        "files_examined": total_files,
    }


def _parse_validator_version(stdout: str) -> str:
    plain = re.sub(r"\x1b\[[0-9;]*m", "", stdout).strip()
    match = re.fullmatch(r"(?:bids-validator\s+)?(3\.0\.0)", plain)
    if match is None:
        raise ValidationError("BIDS Validator version differs from the pinned version")
    return match.group(1)


def _run_validator(
    docker: Path,
    image: str,
    raw_root: Path,
    output_path: Path,
    runner: CommandRunner = subprocess.run,
    identity_provider: DockerIdentityProvider | None = None,
    endpoint_provider: DockerEndpointProvider | None = None,
    environment_provider: Callable[[], dict[str, str]] | None = None,
) -> dict[str, Any]:
    _verify_docker_cli_version(
        docker, runner, identity_provider, endpoint_provider, environment_provider
    )
    _verify_docker_backend(
        docker, runner, identity_provider, endpoint_provider, environment_provider
    )
    _inspect_validator_image(
        docker,
        image,
        runner,
        identity_provider,
        endpoint_provider,
        environment_provider,
    )
    base_policy = _docker_base_policy_args()
    version_result = _run_trusted_docker(
        docker,
        [*base_policy, image, "--version"],
        runner,
        identity_provider=identity_provider,
        endpoint_provider=endpoint_provider,
        environment_provider=environment_provider,
    )
    if version_result.returncode != 0:
        raise ValidationError("BIDS Validator version differs from the pinned version")
    version = _parse_validator_version(version_result.stdout)
    started = _utc_now()
    dataset_policy = _docker_dataset_policy_args(raw_root)
    result = _run_trusted_docker(
        docker,
        [*dataset_policy, image, "/data", "--format", "json"],
        runner,
        identity_provider=identity_provider,
        endpoint_provider=endpoint_provider,
        environment_provider=environment_provider,
    )
    completed = _utc_now()
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(result.stdout)
        stream.flush()
        os.fsync(stream.fileno())
    parsed = _parse_validator_result(result.stdout, result.returncode)
    return {
        "name": "BIDS Validator",
        "version": version,
        "container_image": image,
        "docker_command_policy_version": DOCKER_COMMAND_POLICY_VERSION,
        "started_at_utc": started,
        "completed_at_utc": completed,
        "exit_code": result.returncode,
        "output_sha256": _sha256(output_path),
        "nifti_headers_parsed": True,
        **parsed,
    }


def _require_runtime() -> None:
    if platform.system() != "Linux" or "microsoft" not in platform.release().lower():
        raise ValidationError("validation requires WSL2 Linux")
    if "24.04" not in Path("/etc/os-release").read_text():
        raise ValidationError("validation requires Ubuntu 24.04")


def _validate_receipt_manifest_binding(receipt: dict[str, Any], manifest_path: Path) -> str:
    required = {
        "schema_version",
        "scope",
        "actual_final_file_count",
        "actual_total_bytes",
        "manifest_sha256",
    }
    if not required.issubset(receipt):
        raise ValidationError("acquisition receipt lacks required fields")
    if (
        receipt["scope"] != "ds000030_pilot_5_subjects"
        or receipt["actual_final_file_count"] != EXPECTED_FILES
        or receipt["actual_total_bytes"] != EXPECTED_BYTES
        or f"ds000030-pilot-acquisition-sha256:{_canonical_digest(receipt)}" != EXPECTED_RECEIPT
    ):
        raise ValidationError("acquisition receipt does not match approved evidence")
    recorded = receipt["manifest_sha256"]
    if not isinstance(recorded, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded):
        raise ValidationError("receipt manifest digest is malformed")
    actual = _sha256(manifest_path)
    if recorded != AUDITED_MANIFEST_SHA256 or actual != recorded:
        raise ValidationError("manifest digest does not match acquisition evidence")
    return actual


def validate(args: argparse.Namespace, runner: CommandRunner = subprocess.run) -> dict[str, Any]:
    _require_runtime()
    if args.raw_root.is_symlink():
        raise ValidationError("raw root is a symbolic link")
    raw_root = args.raw_root.resolve(strict=True)
    repository = Path(__file__).resolve().parents[1]
    if repository == raw_root or repository in raw_root.parents or raw_root in repository.parents:
        raise ValidationError("raw root must be outside Git")
    if args.output.resolve().is_relative_to(raw_root):
        raise ValidationError("validation output must be outside the raw tree")
    _require_private_directory(args.output.parent)
    _require_private_evidence_file(args.manifest)
    _require_private_evidence_file(args.acquisition_receipt)
    receipt = _strict_json(args.acquisition_receipt)
    actual_manifest_digest = _validate_receipt_manifest_binding(receipt, args.manifest)
    manifest = _read_manifest(args.manifest)
    if len(manifest) != EXPECTED_FILES:
        raise ValidationError("manifest entry count is not 22")
    _validate_private_tree(raw_root)
    pre = _snapshot(raw_root, manifest)
    if sum(item["size"] for item in pre.values()) != EXPECTED_BYTES:
        raise ValidationError("raw byte total differs from acquisition evidence")
    started = _utc_now()
    structure = _validate_structure(raw_root)
    metadata = _validate_metadata(raw_root, structure)
    validator_output = args.output.with_suffix(".validator.json")
    validator = _run_validator(
        _trusted_docker(args.docker_executable),
        args.validator_image,
        raw_root,
        validator_output,
        runner,
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
        "manifest_sha256": actual_manifest_digest,
        "acquisition_manifest_binding_verified": True,
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
        "header_free_text_count": headers["header_free_text_count"],
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
        "acquisition_manifest_binding_verified": True,
        "validation_report_sha256": digest,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--raw-root", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--acquisition-receipt", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--docker-executable", type=Path, required=True)
    result.add_argument("--validator-image", default=VALIDATOR_IMAGE)
    return result


def _error_category(exc: BaseException) -> str:
    if isinstance(exc, subprocess.SubprocessError):
        return "docker_unavailable"
    message = str(exc).casefold()
    rules = (
        (("wsl2", "ubuntu 24.04"), "runtime_unsupported"),
        (("trusted docker", "docker cli", "supplied docker", "docker backend"), "docker_untrusted"),
        (("docker daemon",), "docker_unavailable"),
        (("evidence mode", "evidence is missing", "owner"), "evidence_permission_invalid"),
        (("receipt manifest", "manifest digest"), "manifest_binding_invalid"),
        (("acquisition receipt", "required fields"), "receipt_invalid"),
        (("manifest",), "manifest_invalid"),
        (("raw file mode", "private directory", "raw root"), "raw_permission_invalid"),
        (("hash or size", "byte total"), "raw_integrity_invalid"),
        (("structure", "directory count", "file count", "pairing"), "structure_invalid"),
        (("metadata", "repetition time", "slice timing"), "metadata_invalid"),
        (("nifti", "header", "affine", "voxel spacing", "orientation"), "header_invalid"),
        (("image digest",), "image_digest_mismatch"),
        (("image",), "image_missing"),
        (("validator version",), "validator_version_mismatch"),
        (("unclassified warning",), "validator_warning_unclassified"),
        (("reported errors",), "validator_errors"),
        (("validator",), "validator_output_invalid"),
        (("changed during validation",), "raw_changed"),
    )
    for needles, category in rules:
        if any(needle in message for needle in needles):
            return category
    return "output_write_failed" if isinstance(exc, OSError) else "validator_output_invalid"


def main() -> int:
    args = parser().parse_args()
    try:
        summary = validate(args)
    except (OSError, subprocess.SubprocessError, ValidationError) as exc:
        category = _error_category(exc)
        if category not in ERROR_CATEGORIES:
            category = "validator_output_invalid"
        failure = {
            "schema_version": "1",
            "validation_completed_at_utc": _utc_now(),
            "validation_decision": "blocked",
            "blocking_issues": [category],
            "voxel_arrays_loaded": 0,
            "raw_files_modified": 0,
        }
        output_parent_private = True
        try:
            _require_private_directory(args.output.parent)
        except ValidationError:
            output_parent_private = False
        if output_parent_private and not args.output.exists():
            try:
                fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps(failure, indent=2, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                category = "output_write_failed"
                failure["blocking_issues"] = [category]
        print(
            json.dumps(
                {
                    "validation_passed": False,
                    "error_category": category,
                    "validation_report_sha256": _canonical_digest(failure),
                }
            )
        )
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
