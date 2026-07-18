#!/usr/bin/env python
"""Safety-gated acquisition executor for the ds000030 five-subject pilot.

Default is ``--dry-run``: it validates the plan, the approval record and storage
record (when supplied), the target root, capacity, and repository cleanliness,
performs **zero provider body requests**, prints only aggregate identifier-free
output, and exits nonzero if any precondition fails.

Execution (``--execute``) is refused unless a separate external **approval
record** (``--approval-record``, mode 600) independently authorizes this exact
plan *and* this exact code. A command-line boolean cannot establish approval;
there is no ``--approved`` flag. Approval is bound to the current HEAD (an
ancestor is not enough), to the SHA-256 of the security-critical executor bundle
at that commit, and to the external storage-readiness record (``--storage-record``).

The plan never carries a download URL: at execution time each URL is resolved
from the trusted OpenNeuro metadata endpoint, scheme/host/path-validated, and
used once; signed URLs are never printed, logged, or persisted. A file counts as
complete only when its size *and* a recomputed SHA-256 match the external
checksum manifest; a size-only match is never trusted. Execution is supported
only inside Ubuntu-24.04 WSL2, where POSIX file modes are enforceable.

This task runs the tool in dry-run only and downloads nothing.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from neuromultiverse.ds000030_pilot import (
    CONTROLLED_RESERVE_BYTES,
    DS000030_ACCESSION,
    DS000030_DOI,
    DS000030_PILOT_EXPECTED_BYTES,
    DS000030_PILOT_FILE_COUNT,
    DS000030_PILOT_PLAN_REFERENCE,
    DS000030_PLAN_CANONICAL_SHA256,
    DS000030_SCOPE,
    DS000030_SNAPSHOT,
    DS000030_STORAGE_REFERENCE,
    PILOT_SUBJECT_COUNT,
    PilotAcquisitionPlan,
    PilotApprovalRecord,
    PilotFileEntry,
    PilotStorageRecord,
)

_CHUNK = 1024 * 1024
_ALLOWED_SCHEMES = frozenset({"https"})
_EXPECTED_WSL_DISTRIBUTION = "Ubuntu-24.04"
_RAW_RELATIVE_ROOT = Path("ds000030/raw")
_MANIFEST_RELATIVE_PATH = Path("ds000030/checksums.sha256")
_LOG_RELATIVE_ROOT = Path("acquisition-log")

# The security-critical modules bound by the executor bundle digest. Every module
# that controls approval, plan, URL, download-integrity, or manifest logic lives
# here; the executor imports only its typed models from the pilot module.
_BUNDLE_MEMBERS = (
    "scripts/acquire_ds000030_pilot.py",
    "src/neuromultiverse/ds000030_pilot.py",
)


@dataclass(frozen=True)
class ObjectOrigin:
    """A precise host-plus-path policy for a trusted object or metadata origin."""

    host: str
    path_prefix: str  # the URL path must start with this


# Minimum precise allowlist for ds000030 snapshot 1.0.0, from authoritative
# metadata-only observation: object URLs are served from the OpenNeuro CRN object
# endpoint under /crn/datasets/, which redirects to the ``openneuro.org`` S3
# bucket (path-style and virtual-hosted forms of the *same* bucket).
_OBJECT_ORIGINS = (
    ObjectOrigin("openneuro.org", "/crn/datasets/"),
    ObjectOrigin("s3.amazonaws.com", "/openneuro.org/"),
)
_METADATA_ORIGINS = (ObjectOrigin("openneuro.org", "/crn/graphql"),)
_METADATA_ENDPOINT = "https://openneuro.org/crn/graphql"

# Substrings that must never appear in an event key or in any event string value.
_FORBIDDEN_EVENT_TOKENS = (
    "url",
    "signed",
    "token",
    "cookie",
    "authorization",
    "password",
    "credential",
    "x-amz",
)

MetadataFetcher = Callable[[str, str], list[dict[str, Any]]]


# --- Selection (retained; used to reproduce the deterministic pilot set) -----
def selection_digest(subject_id: str, seed: str) -> str:
    """Stable, process-independent selection key. Never uses builtin hash()."""
    payload = f"{seed}|ds000030|{DS000030_SNAPSHOT}|pilot-selection-v1|{subject_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


def select_pilot_subjects(subject_ids: list[str], seed: str, count: int) -> list[str]:
    """Deterministically select ``count`` subjects, independent of input order."""
    ordered = sorted(subject_ids, key=lambda sid: (selection_digest(sid, seed), sid))
    return ordered[:count]


# --- Digests, loading -------------------------------------------------------
def canonical_plan_digest(plan: dict[str, Any]) -> str:
    """SHA-256 of the plan's canonical JSON (stable across key order)."""
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_json_digest(data: dict[str, Any]) -> str:
    """SHA-256 of any object's canonical JSON (sorted keys, compact)."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_plan(path: Path) -> tuple[dict[str, Any], PilotAcquisitionPlan]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, PilotAcquisitionPlan.model_validate(data)


def load_approval(path: Path) -> PilotApprovalRecord:
    return PilotApprovalRecord.model_validate_json(path.read_text(encoding="utf-8"))


def load_storage_record(path: Path) -> tuple[dict[str, Any], PilotStorageRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, PilotStorageRecord.model_validate(data)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# --- POSIX modes / runtime (fail closed when modes cannot be verified) -------
def posix_mode(path: Path) -> int | None:
    """The file's permission bits on POSIX, or None where modes are meaningless."""
    if hasattr(os, "getuid"):
        return path.stat().st_mode & 0o777
    return None


def mode_is_600(path: Path) -> bool | None:
    """True/False on POSIX; None where the mode cannot be verified."""
    mode = posix_mode(path)
    return None if mode is None else mode == 0o600


def wsl_distribution() -> str | None:
    """The current WSL distribution name, if running under WSL."""
    return os.environ.get("WSL_DISTRO_NAME")


def runtime_problems() -> list[str]:
    """Problems that make execution unsupported in the current runtime."""
    problems: list[str] = []
    if not hasattr(os, "getuid") or sys.platform != "linux":
        problems.append("execution requires a POSIX runtime with enforceable file modes")
    distro = wsl_distribution()
    if distro != _EXPECTED_WSL_DISTRIBUTION:
        problems.append("execution requires the Ubuntu-24.04 WSL2 runtime")
    try:
        kernel = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
        os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        kernel = os_release = ""
    if "microsoft-standard-wsl2" not in kernel:
        problems.append("execution requires positive WSL2 kernel verification")
    release = dict(line.split("=", 1) for line in os_release.splitlines() if "=" in line)
    if (
        release.get("ID", "").strip('"') != "ubuntu"
        or release.get("VERSION_ID", "").strip('"') != "24.04"
    ):
        problems.append("execution requires Ubuntu 24.04 distribution identity")
    return problems


# --- URL safety -------------------------------------------------------------
def _host_is_ip_literal(host: str) -> bool:
    """Whether ``host`` is any IP literal form (dotted, integer, hex, octal)."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # Integer / hex / octal single-token forms (e.g. 2130706433, 0x7f000001).
    try:
        ipaddress.ip_address(int(host, 0))
        return True
    except (ValueError, TypeError):
        return False


def validate_url(url: str, origins: tuple[ObjectOrigin, ...] = _OBJECT_ORIGINS) -> None:
    """Raise unless ``url`` is HTTPS to an allowlisted host-plus-path origin.

    Rejects non-HTTPS schemes, userinfo, fragments, non-default ports, any IP
    literal in any radix, loopback/localhost/private/link-local/multicast/
    unspecified/reserved addresses, and any host/path not matching an origin.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("url scheme is not https")
    if parsed.username or parsed.password:
        raise ValueError("url must not carry userinfo")
    if parsed.fragment:
        raise ValueError("url must not carry a fragment")
    if parsed.port is not None and parsed.port != 443:
        raise ValueError("url must not use a non-default port")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("url has no host")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("loopback host is not allowed")
    if _host_is_ip_literal(host):
        try:
            ip = ipaddress.ip_address(host if ":" in host or host.count(".") == 3 else int(host, 0))
        except ValueError:
            raise ValueError("ip-literal host is not allowed") from None
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ValueError("non-public ip address is not allowed")
        raise ValueError("ip-literal host is not on the allowlist")
    path = parsed.path or "/"
    decoded_path = path
    for _ in range(3):
        decoded = unquote(decoded_path)
        if decoded == decoded_path:
            break
        decoded_path = decoded
    if "\\" in decoded_path or any(segment in (".", "..") for segment in decoded_path.split("/")):
        raise ValueError("url path contains an unsafe segment")
    for origin in origins:
        if host == origin.host and path.startswith(origin.path_prefix):
            return
    raise ValueError("url host/path is not on the allowlist")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect target against the object allowlist before use."""

    def validate_redirect(self, location: str) -> str:
        validate_url(location, _OBJECT_ORIGINS)
        return location

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        self.validate_redirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def resolve_download_url(
    provider_object_id: str,
    provider_path: str,
    expected_size: int,
    fetcher: MetadataFetcher,
) -> str:
    """Resolve a single validated HTTPS object URL from trusted metadata.

    Fails closed unless exactly one metadata object matches the approved path,
    object id, and provider-reported size. The resolved URL is validated but not
    opened here; no URL appears in any error text.
    """
    try:
        candidates = fetcher(provider_object_id, provider_path)
    except (urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"metadata resolution failed: {type(exc).__name__}") from None
    matches = [
        m
        for m in candidates
        if m.get("provider_object_id") == provider_object_id
        and m.get("provider_path") == provider_path
        and _safe_int(m.get("provider_size_bytes")) == expected_size
    ]
    if len(matches) != 1:
        raise ValueError("metadata did not resolve exactly one matching object")
    url = matches[0].get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("metadata object has no valid url")
    validate_url(url, _OBJECT_ORIGINS)
    return url


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _default_metadata_fetcher(provider_object_id: str, provider_path: str) -> list[dict[str, Any]]:
    """Resolve one object's current URL from OpenNeuro GraphQL by walking the tree.

    Metadata only: the returned URL is never opened here. The endpoint is
    validated before any request, requests use a bounded timeout, and only
    clearly transient failures are retried a bounded number of times.
    """
    validate_url(_METADATA_ENDPOINT, _METADATA_ORIGINS)
    segments = provider_path.split("/")
    tree: str | None = None
    entry: dict[str, Any] | None = None
    for index, name in enumerate(segments):
        children = _graphql_files(tree)
        matches = [child for child in children if child.get("filename") == name]
        if len(matches) != 1:
            return []
        match = matches[0]
        last = index == len(segments) - 1
        if last:
            entry = match
        else:
            if not match.get("directory"):
                return []
            tree = str(match.get("id"))
    if entry is None or entry.get("directory"):
        return []
    urls = entry.get("urls") or []
    if not urls:
        return []
    return [
        {
            "provider_object_id": str(entry.get("id")),
            "provider_path": provider_path,
            "provider_size_bytes": entry.get("size"),
            "url": str(urls[0]),
        }
    ]


def _graphql_files(tree: str | None) -> list[dict[str, Any]]:
    """One bounded GraphQL query returning DatasetFile entries for a tree level."""
    field = f'files(tree:"{tree}")' if tree else "files"
    query = (
        '{ snapshot(datasetId:"ds000030",tag:"1.0.0"){ '
        f"{field}{{ id filename size directory urls }} }} }}"
    )
    body = json.dumps({"query": query}).encode()
    last_exc: Exception | None = None
    for _attempt in range(3):
        try:
            req = urllib.request.Request(  # noqa: S310 - validated https metadata endpoint
                _METADATA_ENDPOINT, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                payload = json.load(resp)
            if not isinstance(payload, dict) or payload.get("errors"):
                raise ValueError("metadata response contains errors")
            files = ((payload.get("data") or {}).get("snapshot") or {}).get("files")
            if not isinstance(files, list):
                raise ValueError("metadata response missing snapshot files")
            for item in files:
                if (
                    not isinstance(item, dict)
                    or set(item) != {"id", "filename", "size", "directory", "urls"}
                    or not isinstance(item["id"], str)
                    or not item["id"]
                    or not isinstance(item["filename"], str)
                    or not item["filename"]
                    or not isinstance(item["size"], int)
                    or isinstance(item["size"], bool)
                    or item["size"] < 0
                    or not isinstance(item["directory"], bool)
                    or not isinstance(item["urls"], list)
                    or not all(isinstance(url, str) and url for url in item["urls"])
                ):
                    raise ValueError("metadata response contains a malformed file entry")
            return files
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504):
                raise ValueError("metadata query failed: HTTPError") from None
            last_exc = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc  # transient: bounded retry
        except json.JSONDecodeError:
            raise ValueError("metadata response is malformed JSON") from None
    raise ValueError(f"metadata query failed: {type(last_exc).__name__ if last_exc else 'unknown'}")


# --- Integrity manifest (strict, fail-closed) -------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ManifestError(ValueError):
    """A checksum manifest is malformed or violates the target namespace."""


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_manifest_relpath(rel: str, allowed: frozenset[str] | None) -> None:
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        raise ManifestError("manifest path must be a non-empty relative path")
    if any(ord(c) < 0x20 or c == "\x7f" for c in rel):
        raise ManifestError("manifest path contains a control character")
    if "\\" in rel:
        raise ManifestError("manifest path must use POSIX separators")
    parts = rel.split("/")
    if ".." in parts or "" in parts:
        raise ManifestError("manifest path contains traversal")
    if allowed is not None and rel not in allowed:
        raise ManifestError("manifest path is outside the approved target namespace")


def read_manifest(
    manifest_path: Path, allowed_targets: frozenset[str] | None = None
) -> dict[str, str]:
    """Read a ``<sha256>  <relative-path>`` manifest, failing closed on any defect."""
    result: dict[str, str] = {}
    if not manifest_path.exists():
        return result
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        if raw == "":
            raise ManifestError("manifest contains a blank line")
        if raw != raw.strip():
            raise ManifestError("manifest line has leading/trailing whitespace")
        digest, sep, rel = raw.partition("  ")
        if not sep or not digest or not rel:
            raise ManifestError("manifest line is not '<sha256>  <path>'")
        if not _valid_sha256(digest):
            raise ManifestError("manifest digest is not lowercase 64-char sha256")
        _validate_manifest_relpath(rel, allowed_targets)
        if rel in result:
            if result[rel] != digest:
                raise ManifestError("manifest has conflicting digests for one path")
            raise ManifestError("manifest has a duplicate path entry")
        result[rel] = digest
    return result


def write_manifest(manifest_path: Path, entries: dict[str, str]) -> None:
    """Write a canonical, sorted manifest atomically (temp, fsync, replace, 0600)."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{entries[rel]}  {rel}\n" for rel in sorted(entries)]
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write("".join(lines))
        fh.flush()
        if hasattr(os, "fsync"):
            os.fsync(fh.fileno())
    if hasattr(os, "chmod"):
        tmp.chmod(0o600)
    tmp.replace(manifest_path)
    if hasattr(os, "chmod"):
        manifest_path.chmod(0o600)


def add_manifest_entry(
    manifest_path: Path,
    relative_target: str,
    digest: str,
    allowed_targets: frozenset[str] | None = None,
) -> None:
    """Add one entry to the manifest, never replacing a different existing digest."""
    if not _valid_sha256(digest):
        raise ManifestError("refusing to record a non-sha256 digest")
    _validate_manifest_relpath(relative_target, allowed_targets)
    entries = read_manifest(manifest_path, allowed_targets)
    existing = entries.get(relative_target)
    if existing is not None and existing != digest:
        raise ManifestError("refusing to overwrite an existing manifest digest")
    entries[relative_target] = digest
    write_manifest(manifest_path, entries)
    if read_manifest(manifest_path, allowed_targets) != entries:
        raise ManifestError("manifest verification failed after atomic update")


def completion_status(
    target: Path, expected_size: int, manifest: dict[str, str], relative: str
) -> str:
    """Integrity-aware completion. Size alone is never 'complete'."""
    if not target.exists():
        return "absent"
    if target.stat().st_size != expected_size:
        return "size_mismatch"
    recorded = manifest.get(relative)
    if recorded is None:
        return "size_only_unverified"
    return "complete" if sha256_file(target) == recorded else "checksum_mismatch"


# --- Events (common context, no URL, no credential) -------------------------
def _utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reject_forbidden(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            low = str(key).lower()
            if any(tok in low for tok in _FORBIDDEN_EVENT_TOKENS):
                raise ValueError("event key looks like a url or credential")
            _reject_forbidden(value)
    elif isinstance(obj, list):
        for item in obj:
            _reject_forbidden(item)
    elif isinstance(obj, str):
        low = obj.lower()
        if any(tok in low for tok in _FORBIDDEN_EVENT_TOKENS) or "://" in low:
            raise ValueError("event value looks like a url or credential")


def append_event(log_dir: Path, event: dict[str, Any]) -> None:
    """Append one JSONL event (no URL, no credential). File mode 600 on POSIX."""
    _reject_forbidden(event)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "acquisition-events.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp_utc": _utc(), **event}) + "\n")
    if hasattr(os, "chmod"):
        path.chmod(0o600)


def _event_context(
    plan_model: PilotAcquisitionPlan, approval: PilotApprovalRecord
) -> dict[str, Any]:
    """The common, identifier-free context stamped on every real execution event."""
    return {
        "dataset_accession": DS000030_ACCESSION,
        "acquisition_scope_id": plan_model.acquisition_scope_id,
        "snapshot": plan_model.snapshot,
        "canonical_plan_sha256": DS000030_PLAN_CANONICAL_SHA256,
        "approval_id": approval.approval_id,
        "approved_code_commit": approval.approved_code_commit,
        "executor_bundle_sha256": approval.executor_bundle_sha256,
    }


def _checksum_classification(entry: PilotFileEntry) -> str:
    if entry.provider_checksum is None:
        return "unavailable"
    if not entry.provider_checksum_suitable_for_content_integrity:
        return "unsuitable"
    return f"verified_{entry.provider_checksum_algorithm}"


# --- Git-anchored approval + executor-bundle checks -------------------------
def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git") or "git"
    return subprocess.run(
        [git, "-C", str(_repo_root()), *args], capture_output=True, text=True, check=False
    )


def _git_blob_bytes(commit: str, rel: str) -> bytes | None:
    git = shutil.which("git") or "git"
    result = subprocess.run(
        [git, "-C", str(_repo_root()), "show", f"{commit}:{rel}"],
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def working_tree_clean() -> bool:
    result = _git(["status", "--porcelain"])
    return result.returncode == 0 and result.stdout.strip() == ""


def head_commit() -> str:
    return _git(["rev-parse", "HEAD"]).stdout.strip()


def _bundle_digest(get_bytes: Callable[[str], bytes | None]) -> str | None:
    """Canonical SHA-256 over the executor bundle (sorted paths, length-framed)."""
    digest = hashlib.sha256()
    for rel in sorted(_BUNDLE_MEMBERS):
        blob = get_bytes(rel)
        if blob is None:
            return None
        path_bytes = rel.encode("utf-8")
        digest.update(struct.pack(">Q", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(blob)))
        digest.update(blob)
    return digest.hexdigest()


def executor_bundle_digest_at(commit: str) -> str | None:
    return _bundle_digest(lambda rel: _git_blob_bytes(commit, rel))


def executor_bundle_digest_working() -> str | None:
    def read(rel: str) -> bytes | None:
        path = _repo_root() / rel
        return path.read_bytes() if path.exists() else None

    return _bundle_digest(read)


def working_files_match_commit(commit: str) -> bool:
    """Whether every bundle member's working bytes equal the approved git blob."""
    for rel in _BUNDLE_MEMBERS:
        blob = _git_blob_bytes(commit, rel)
        path = _repo_root() / rel
        if blob is None or not path.exists() or path.read_bytes() != blob:
            return False
    return True


# --- Preconditions ----------------------------------------------------------
def approval_problems(plan: dict[str, Any], approval: PilotApprovalRecord) -> list[str]:
    """Problems tying the approval record to the exact plan and committed evidence."""
    problems: list[str] = []
    if approval.decision != "approved":
        problems.append("approval decision is not 'approved'")
    if approval.canonical_plan_sha256 != canonical_plan_digest(plan):
        problems.append("approval plan digest does not match the plan")
    if approval.acquisition_scope_id != DS000030_SCOPE:
        problems.append("approval scope mismatch")
    if approval.snapshot != DS000030_SNAPSHOT or approval.doi != DS000030_DOI:
        problems.append("approval snapshot/DOI mismatch")
    if approval.expected_file_count != plan.get("expected_file_count"):
        problems.append("approval file count mismatch")
    if approval.expected_transfer_bytes != plan.get("expected_transfer_bytes"):
        problems.append("approval byte count mismatch")
    if approval.canonical_plan_sha256 != DS000030_PLAN_CANONICAL_SHA256:
        problems.append("approval plan digest does not match the committed governance record")
    if approval.expected_file_count != DS000030_PILOT_FILE_COUNT:
        problems.append("approval file count does not match the committed governance record")
    if approval.expected_transfer_bytes != DS000030_PILOT_EXPECTED_BYTES:
        problems.append("approval byte count does not match the committed governance record")
    if DS000030_PILOT_PLAN_REFERENCE.rsplit(":", 1)[-1] != approval.canonical_plan_sha256:
        problems.append("approval plan digest does not match the committed plan reference")
    if approval.storage_evidence_reference != DS000030_STORAGE_REFERENCE:
        problems.append("approval storage evidence reference mismatch")
    if approval.size_evidence_reference != DS000030_PILOT_PLAN_REFERENCE:
        problems.append("approval size evidence reference mismatch")
    if approval.storage_record_sha256 != DS000030_STORAGE_REFERENCE.rsplit(":", 1)[-1]:
        problems.append("approval storage_record_sha256 mismatch")
    return problems


def execution_repo_problems(approval: PilotApprovalRecord) -> list[str]:
    """Bind approval to the *exact* current HEAD and the whole executor bundle."""
    problems: list[str] = []
    if not working_tree_clean():
        problems.append("working tree/index is not clean")
    head = head_commit()
    if not head or approval.approved_code_commit != head:
        problems.append("approved_code_commit is not exactly the current HEAD")
    bundle_at_head = executor_bundle_digest_at("HEAD")
    if bundle_at_head is None:
        problems.append("could not compute the executor bundle digest at HEAD")
    elif approval.executor_bundle_sha256 != bundle_at_head:
        problems.append("approval executor bundle digest does not match HEAD")
    if not working_files_match_commit("HEAD"):
        problems.append("a working executor file differs from its approved git blob")
    return problems


def _mount_info(mount_point: str) -> tuple[str, str] | None:
    """(device, fstype) for a mount point, read from /proc/self/mountinfo."""
    proc = Path("/proc/self/mountinfo")
    if not proc.exists():
        return None
    try:
        for line in proc.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if " - " not in line:
                continue
            sep = fields.index("-")
            mp = fields[4]
            if mp == mount_point:
                fstype = fields[sep + 1]
                source = fields[sep + 2]
                return source, fstype
    except (OSError, ValueError, IndexError):
        return None
    return None


def storage_problems(
    storage_data: dict[str, Any],
    storage_model: PilotStorageRecord,
    target_root: Path,
    expected_transfer: int,
) -> list[str]:
    """Bind the target root to the external storage-readiness record."""
    problems: list[str] = []
    if canonical_json_digest(storage_data) != DS000030_STORAGE_REFERENCE.rsplit(":", 1)[-1]:
        problems.append("storage record canonical digest does not match the committed reference")
    if storage_model.controlled_raw_processing_reserve_bytes != CONTROLLED_RESERVE_BYTES:
        problems.append("storage record reserve is not exactly the controlled reserve")
    if not storage_model.capacity_gate_passes:
        problems.append("storage record says the capacity gate did not pass")
    if storage_model.available_bytes < expected_transfer + CONTROLLED_RESERVE_BYTES:
        problems.append("recorded capacity does not clear transfer plus reserve")
    if not storage_model.external_root_outside_git:
        problems.append("storage record does not assert the root is outside Git")
    if storage_model.wsl_distribution != _EXPECTED_WSL_DISTRIBUTION:
        problems.append("storage record was not generated in Ubuntu-24.04")

    resolved_target = target_root.resolve()
    recorded_root = Path(storage_model.resolved_external_data_root).resolve()
    if recorded_root / _RAW_RELATIVE_ROOT != resolved_target:
        problems.append("runtime target is not the recorded external root's ds000030/raw directory")

    repo = _repo_root()
    if resolved_target == repo or repo in resolved_target.parents:
        problems.append("target root resolves inside the Git repository")
    if _target_symlinks_into_repo(target_root, repo):
        problems.append("target root is a symlink into the Git repository")

    try:
        free_now = shutil.disk_usage(target_root).free
    except OSError:
        free_now = 0
    if free_now < expected_transfer + CONTROLLED_RESERVE_BYTES:
        problems.append("current free capacity no longer clears transfer plus reserve")

    current = _mount_info(storage_model.mount_point)
    if current is None:
        problems.append("recorded mount cannot be verified; renew the readiness record")
    else:
        source, fstype = current
        if source != storage_model.filesystem_device or fstype != storage_model.filesystem_type:
            problems.append("filesystem device or type changed; renew the readiness record")
    return problems


def _target_symlinks_into_repo(target_root: Path, repo: Path) -> bool:
    node = target_root
    for candidate in (node, *node.parents):
        try:
            if candidate.is_symlink():
                resolved = candidate.resolve()
                if resolved == repo or repo in resolved.parents:
                    return True
        except OSError:
            continue
    return False


def check_preconditions(
    plan: dict[str, Any],
    plan_model: PilotAcquisitionPlan,
    target_root: Path,
    free_bytes: int,
    approval: PilotApprovalRecord | None,
    storage: tuple[dict[str, Any], PilotStorageRecord] | None,
    *,
    for_execution: bool,
) -> list[str]:
    """Return blocking problems; empty means every applicable precondition holds."""
    problems: list[str] = []

    if plan.get("acquisition_scope_id") != DS000030_SCOPE:
        problems.append("plan scope must be the five-subject pilot scope")
    if plan.get("snapshot") != DS000030_SNAPSHOT or plan.get("doi") != DS000030_DOI:
        problems.append("plan snapshot/DOI mismatch")
    if len(plan_model.selected_subject_ids) != PILOT_SUBJECT_COUNT:
        problems.append("plan must select exactly five subjects")
    if plan_model.expected_file_count != DS000030_PILOT_FILE_COUNT:
        problems.append("plan file count does not match the reviewed pilot count")
    if plan_model.expected_transfer_bytes != DS000030_PILOT_EXPECTED_BYTES:
        problems.append("plan transfer bytes do not match the reviewed pilot total")
    if canonical_plan_digest(plan) != DS000030_PLAN_CANONICAL_SHA256:
        problems.append("plan canonical digest does not match the committed reference")

    resolved_root = target_root.resolve()
    repo = _repo_root()
    if resolved_root == repo or repo in resolved_root.parents:
        problems.append("target root must resolve outside the Git repository")

    if free_bytes < plan_model.expected_transfer_bytes + CONTROLLED_RESERVE_BYTES:
        problems.append("insufficient free capacity for planned transfer plus reserve")

    if storage is not None:
        problems.extend(
            storage_problems(
                storage[0], storage[1], target_root, plan_model.expected_transfer_bytes
            )
        )

    if for_execution:
        if approval is None:
            problems.append("execution requires an external approval record")
        else:
            problems.extend(approval_problems(plan, approval))
            problems.extend(execution_repo_problems(approval))
        if storage is None:
            problems.append("execution requires an external storage-readiness record")
        problems.extend(runtime_problems())
    elif approval is not None:
        # In a dry-run an approval record is validated but does not authorize.
        problems.extend(approval_problems(plan, approval))
    return problems


def _aggregate_summary(
    mode: str, plan_model: PilotAcquisitionPlan, target_root: Path, problems: list[str]
) -> dict[str, Any]:
    repo = _repo_root()
    resolved = target_root.resolve()
    return {
        "mode": mode,
        "scope": plan_model.acquisition_scope_id,
        "snapshot": plan_model.snapshot,
        "plan_digest": DS000030_PLAN_CANONICAL_SHA256,
        "planned_file_count": plan_model.expected_file_count,
        "planned_transfer_bytes": plan_model.expected_transfer_bytes,
        "target_root_outside_repo": resolved != repo and repo not in resolved.parents,
        "runtime_supported": not runtime_problems(),
        "network_body_requests": 0,
        "preconditions_ok": not problems,
        "problems": problems,
    }


# --- Single-run execution lock ----------------------------------------------
class LockHeldError(RuntimeError):
    """Another live process holds the execution lock."""


class ExecutionLock:
    """A mode-600 single-run lock outside Git; refuses a second live process."""

    def __init__(self, path: Path, info: dict[str, Any]) -> None:
        self.path = path
        self.info = info
        self._acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._create()
        except FileExistsError:
            # Conservatively refuse all existing locks. An operator may inspect and
            # remove a proven-stale lock; the executor never risks deleting a live one.
            raise LockHeldError("another process holds the execution lock") from None
        self._acquired = True

    def _create(self) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        fd = os.open(self.path, flags, 0o600)
        try:
            os.write(fd, (json.dumps(self.info) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        if hasattr(os, "chmod"):
            self.path.chmod(0o600)

    def release(self) -> None:
        if self._acquired:
            self.path.unlink(missing_ok=True)
            self._acquired = False


# --- Download + promotion (failure-safe) ------------------------------------
def _stream_download(url: str, partial: Path, expected_size: int, entry: PilotFileEntry) -> str:
    """Stream to ``partial``, hash (local + provider), verify size, fsync.

    Returns the local SHA-256. Raises on size or provider-checksum mismatch,
    leaving no promoted file. No URL appears in any raised message.
    """
    validate_url(url, _OBJECT_ORIGINS)
    partial.parent.mkdir(parents=True, exist_ok=True)
    local = hashlib.sha256()
    provider = None
    if entry.provider_checksum_suitable_for_content_integrity and entry.provider_checksum_algorithm:
        provider = hashlib.new(entry.provider_checksum_algorithm)
    written = 0
    opener = urllib.request.build_opener(SafeRedirectHandler())
    req = urllib.request.Request(url)  # noqa: S310 - validated https object URL
    with opener.open(req, timeout=120) as resp, partial.open("wb") as fh:
        for chunk in iter(lambda: resp.read(_CHUNK), b""):
            fh.write(chunk)
            local.update(chunk)
            if provider is not None:
                provider.update(chunk)
            written += len(chunk)
        fh.flush()
        if hasattr(os, "fsync"):
            os.fsync(fh.fileno())
    if written != expected_size:
        raise RuntimeError("byte-count mismatch during download")
    if (
        provider is not None
        and entry.provider_checksum is not None
        and provider.hexdigest() != entry.provider_checksum.lower()
    ):
        raise RuntimeError("provider checksum mismatch")
    return local.hexdigest()


def _download_one(
    entry: PilotFileEntry,
    url: str,
    resolved_root: Path,
    manifest_path: Path,
    allowed: frozenset[str],
    log_dir: Path,
    context: dict[str, Any],
) -> None:
    """Download, verify, atomically promote, and record one file, failure-safe."""
    rel = entry.local_relative_target
    target = (resolved_root / rel).resolve()
    if resolved_root not in target.parents:
        raise ValueError("resolved target escapes the data root")
    partial = target.with_suffix(target.suffix + ".partial")

    digest = _stream_download(url, partial, entry.provider_size_bytes, entry)
    # Promote only after the partial is fully verified; never overwrite an
    # existing (unverified) final file.
    if target.exists():
        partial.unlink(missing_ok=True)
        raise RuntimeError("refusing to overwrite an existing final file")
    partial.replace(target)
    try:
        add_manifest_entry(manifest_path, rel, digest, allowed)
        recheck = read_manifest(manifest_path, allowed)
        if recheck.get(rel) != digest or sha256_file(target) != digest:
            raise ManifestError("post-promotion manifest verification failed")
    except Exception:
        # Manifest update failed after promotion: quarantine the final file so the
        # next run cannot mistake a size-only file for complete.
        quarantine = target.with_suffix(target.suffix + f".unrecorded.{os.getpid()}")
        try:
            target.replace(quarantine)
        except OSError:
            target.unlink(missing_ok=True)
        raise
    append_event(
        log_dir,
        {
            **context,
            "event": "file_download_completed",
            "provider_object_id": entry.provider_object_id,
            "relative_target": rel,
            "expected_bytes": entry.provider_size_bytes,
            "actual_bytes": entry.provider_size_bytes,
            "local_sha256": digest,
            "provider_checksum_classification": _checksum_classification(entry),
            "status": "completed",
        },
    )


def _run_execution(
    plan_model: PilotAcquisitionPlan,
    approval: PilotApprovalRecord,
    target_root: Path,
    fetcher: MetadataFetcher,
    log_dir: Path,
    manifest_path: Path,
    lock_path: Path,
) -> int:
    resolved_root = target_root.resolve()
    allowed = frozenset(f.local_relative_target for f in plan_model.files)
    context = _event_context(plan_model, approval)
    lock = ExecutionLock(
        lock_path,
        {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_utc": _utc(),
            "plan_digest": DS000030_PLAN_CANONICAL_SHA256,
            "approval_id": approval.approval_id,
        },
    )
    try:
        lock.acquire()
    except LockHeldError:
        print(json.dumps({"error": "another process holds the execution lock"}))
        return 1

    try:
        current_entry: PilotFileEntry | None = None
        manifest = read_manifest(manifest_path, allowed)  # validate whole manifest first
        append_event(log_dir, {**context, "event": "run_started"})
        for entry in plan_model.files:
            current_entry = entry
            rel = entry.local_relative_target
            target = (resolved_root / rel).resolve()
            status = completion_status(target, entry.provider_size_bytes, manifest, rel)
            if status == "complete":
                append_event(
                    log_dir,
                    {**context, "event": "file_skipped_verified", "relative_target": rel},
                )
                continue
            if status in ("size_mismatch", "checksum_mismatch", "size_only_unverified"):
                _cleanup_partial(resolved_root, rel)
                append_event(
                    log_dir,
                    {
                        **context,
                        "event": "file_integrity_failed",
                        "relative_target": rel,
                        "status": status,
                    },
                )
                raise RuntimeError("file_integrity_failed")
            url = resolve_download_url(
                entry.provider_object_id, entry.provider_path, entry.provider_size_bytes, fetcher
            )
            append_event(
                log_dir,
                {**context, "event": "file_download_started", "relative_target": rel},
            )
            try:
                _download_one(entry, url, resolved_root, manifest_path, allowed, log_dir, context)
            except Exception:
                _cleanup_partial(resolved_root, rel)
                raise
            manifest[rel] = read_manifest(manifest_path, allowed)[rel]
        append_event(log_dir, {**context, "event": "run_completed"})
        return 0
    except Exception as exc:
        category = type(exc).__name__
        if current_entry is not None:
            append_event(
                log_dir,
                {
                    **context,
                    "event": "file_failed",
                    "relative_target": current_entry.local_relative_target,
                    "error_category": category,
                },
            )
        append_event(log_dir, {**context, "event": "run_failed", "error_category": category})
        return 1
    finally:
        lock.release()


def _cleanup_partial(resolved_root: Path, rel: str) -> None:
    partial = (resolved_root / rel).with_suffix(Path(rel).suffix + ".partial")
    with contextlib.suppress(OSError):
        partial.unlink(missing_ok=True)


# --- CLI --------------------------------------------------------------------
def main(argv: list[str] | None = None, fetcher: MetadataFetcher | None = None) -> int:
    parser = argparse.ArgumentParser(description="ds000030 pilot acquisition (dry-run by default).")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument(
        "--approval-record", default=None, help="external approval record (mode 600)"
    )
    parser.add_argument(
        "--storage-record", default=None, help="external storage-readiness record (mode 600)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    for_execution = args.execute and not args.dry_run
    target_root = Path(args.target_root)

    try:
        plan, plan_model = load_plan(Path(args.plan))
    except Exception as exc:
        print(json.dumps({"error": f"plan invalid: {type(exc).__name__}"}))
        return 1
    if mode_is_600(Path(args.plan)) is False:
        print(json.dumps({"error": "plan must have mode 600"}))
        return 1

    approval: PilotApprovalRecord | None = None
    if args.approval_record is not None:
        approval_path = Path(args.approval_record)
        try:
            approval = load_approval(approval_path)
        except Exception as exc:
            print(json.dumps({"error": f"approval record invalid: {type(exc).__name__}"}))
            return 1
        # A verifiably-wrong mode fails immediately; an unverifiable mode (no POSIX
        # runtime) is only fatal for --execute, handled in the execution branch.
        if mode_is_600(approval_path) is False:
            print(json.dumps({"error": "approval record must have mode 600"}))
            return 1

    storage: tuple[dict[str, Any], PilotStorageRecord] | None = None
    if args.storage_record is not None:
        storage_path = Path(args.storage_record)
        try:
            storage = load_storage_record(storage_path)
        except Exception as exc:
            print(json.dumps({"error": f"storage record invalid: {type(exc).__name__}"}))
            return 1
        if mode_is_600(storage_path) is False:
            print(json.dumps({"error": "storage record must have mode 600"}))
            return 1

    try:
        free_bytes = shutil.disk_usage(target_root).free
    except OSError:
        free_bytes = 0

    problems = check_preconditions(
        plan, plan_model, target_root, free_bytes, approval, storage, for_execution=for_execution
    )

    if not for_execution:
        print(
            json.dumps(_aggregate_summary("dry-run", plan_model, target_root, problems), indent=2)
        )
        return 1 if problems else 0

    if problems:
        print(
            json.dumps({"error": "preconditions failed", "problem_count": len(problems)}, indent=2)
        )
        return 1

    # Every execution-critical mode must be verifiably 600 (None is not success).
    if approval is None or storage is None:  # guarded by preconditions above
        print(json.dumps({"error": "execution requires approval and storage records"}))
        return 1
    storage_root = Path(storage[1].resolved_external_data_root).resolve()
    log_dir = storage_root / _LOG_RELATIVE_ROOT
    manifest_path = storage_root / _MANIFEST_RELATIVE_PATH
    lock_path = log_dir / "ds000030-pilot.lock"
    mode_targets = [Path(args.plan), Path(args.approval_record), Path(args.storage_record)]
    if manifest_path.exists():
        mode_targets.append(manifest_path)
    event_path = log_dir / "acquisition-events.jsonl"
    if event_path.exists():
        mode_targets.append(event_path)
    if lock_path.exists():
        mode_targets.append(lock_path)
    for path in mode_targets:
        if mode_is_600(path) is not True:
            print(json.dumps({"error": "an execution-critical file lacks verifiable mode 600"}))
            return 1

    try:
        return _run_execution(
            plan_model,
            approval,
            target_root,
            fetcher or _default_metadata_fetcher,
            log_dir=log_dir,
            manifest_path=manifest_path,
            lock_path=lock_path,
        )
    except Exception as exc:
        print(json.dumps({"error": f"execution failed: {type(exc).__name__}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
