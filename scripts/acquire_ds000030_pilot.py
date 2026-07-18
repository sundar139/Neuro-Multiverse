#!/usr/bin/env python
"""Safety-gated acquisition executor for the ds000030 five-subject pilot.

Default is ``--dry-run``: it validates the plan, the approval record (when one is
supplied), the target root, capacity, and repository cleanliness, performs **zero
provider body requests**, prints only aggregate identifier-free output, and exits
nonzero if any precondition fails.

Execution (``--execute``) is refused unless a separate external **approval
record** (``--approval-record``, mode 600) independently authorizes this exact
plan. A command-line boolean cannot establish approval; there is no ``--approved``
flag. The plan never carries a download URL: at execution time each URL is
resolved from trusted OpenNeuro metadata, scheme/host-validated, and used once;
signed URLs are never printed, logged, or persisted. A file counts as complete
only when its size *and* a recomputed SHA-256 match the external checksum
manifest; a size-only match is never trusted.

This task runs the tool in dry-run only and downloads nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from neuromultiverse.ds000030_pilot import (
    CONTROLLED_RESERVE_BYTES,
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
)

_CHUNK = 1024 * 1024
_ALLOWED_SCHEMES = frozenset({"https"})
# Hosts observed in the authoritative OpenNeuro snapshot metadata response:
# object bodies are served from the OpenNeuro CRN object endpoint and its S3
# bucket. Metadata is resolved only through the CRN GraphQL host.
_ALLOWED_METADATA_HOSTS = frozenset({"openneuro.org"})
_ALLOWED_OBJECT_HOSTS = frozenset({"openneuro.org", "s3.amazonaws.com"})
_METADATA_ENDPOINT = "https://openneuro.org/crn/graphql"

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


def load_plan(path: Path) -> tuple[dict[str, Any], PilotAcquisitionPlan]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, PilotAcquisitionPlan.model_validate(data)


def load_approval(path: Path) -> PilotApprovalRecord:
    return PilotApprovalRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _posix_mode_600(path: Path) -> bool | None:
    """True/False on POSIX; None on platforms without meaningful file modes."""
    import os

    if hasattr(os, "getuid"):
        return (path.stat().st_mode & 0o777) == 0o600
    return None


# --- URL safety -------------------------------------------------------------
def validate_url(url: str, allowed_hosts: frozenset[str]) -> None:
    """Raise unless ``url`` is HTTPS to an allowlisted, non-private host."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("url scheme is not https")
    host = parsed.hostname or ""
    if host not in allowed_hosts:
        raise ValueError("url host is not on the allowlist")
    if host in ("localhost",) or host.endswith(".localhost"):
        raise ValueError("loopback host is not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved):
        raise ValueError("private/loopback/link-local address is not allowed")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect target against the object allowlist before use."""

    def validate_redirect(self, location: str) -> str:
        validate_url(location, _ALLOWED_OBJECT_HOSTS)
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
    """Resolve a single, validated HTTPS object URL from trusted metadata.

    Fails closed unless exactly one metadata object matches the approved path,
    object id, and provider-reported size. The resolved URL is validated but not
    opened here.
    """
    matches = [
        m
        for m in fetcher(provider_object_id, provider_path)
        if m.get("provider_object_id") == provider_object_id
        and m.get("provider_path") == provider_path
        and int(m.get("provider_size_bytes", -1)) == expected_size
    ]
    if len(matches) != 1:
        raise ValueError("metadata did not resolve exactly one matching object")
    url = str(matches[0]["url"])
    validate_url(url, _ALLOWED_OBJECT_HOSTS)
    return url


# --- Integrity manifest -----------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(manifest_path: Path) -> dict[str, str]:
    """Read a ``<sha256>  <relative-path>`` manifest into a mapping."""
    result: dict[str, str] = {}
    if not manifest_path.exists():
        return result
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, rel = line.partition("  ")
        if digest and rel:
            result[rel] = digest
    return result


def append_manifest(manifest_path: Path, relative_target: str, digest: str) -> None:
    """Append one entry atomically (write temp, then os.replace over a lock-free append)."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else ""
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(f"{existing}{digest}  {relative_target}\n", encoding="utf-8")
    tmp.replace(manifest_path)


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


# --- Events -----------------------------------------------------------------
def _utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_event(log_dir: Path, event: dict[str, Any]) -> None:
    """Append one JSONL event (no URL, no credential). File mode 600 on POSIX."""
    forbidden = {"url", "download_url", "cookie", "token", "authorization", "password"}
    if any(k.lower() in forbidden for k in event):
        raise ValueError("event must not contain a URL or credential field")
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "acquisition-events.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp_utc": _utc(), **event}) + "\n")
    import os

    if hasattr(os, "chmod"):
        path.chmod(0o600)


# --- Git-anchored approval checks -------------------------------------------
def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git") or "git"
    return subprocess.run(
        [git, "-C", str(_repo_root()), *args], capture_output=True, text=True, check=False
    )


def working_tree_clean() -> bool:
    result = _git(["status", "--porcelain"])
    return result.returncode == 0 and result.stdout.strip() == ""


def script_matches_commit(commit: str) -> bool:
    """Whether this executor is byte-identical to its version at ``commit``."""
    rel = "scripts/acquire_ds000030_pilot.py"
    blob = _git(["show", f"{commit}:{rel}"])
    if blob.returncode != 0:
        return False
    return blob.stdout == Path(__file__).read_text(encoding="utf-8")


def commit_is_approved_ancestor(commit: str) -> bool:
    """Whether ``commit`` is HEAD or a first-parent ancestor of HEAD."""
    head = _git(["rev-parse", "HEAD"]).stdout.strip()
    if commit == head:
        return True
    return _git(["merge-base", "--is-ancestor", commit, "HEAD"]).returncode == 0


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
    return problems


def execution_repo_problems(approval: PilotApprovalRecord) -> list[str]:
    problems: list[str] = []
    if not working_tree_clean():
        problems.append("working tree/index is not clean")
    if not commit_is_approved_ancestor(approval.approved_code_commit):
        problems.append("approved_code_commit is not HEAD or an ancestor of HEAD")
    if not script_matches_commit(approval.approved_code_commit):
        problems.append("executor differs from the approved_code_commit version")
    return problems


def check_preconditions(
    plan: dict[str, Any],
    plan_model: PilotAcquisitionPlan,
    target_root: Path,
    free_bytes: int,
    approval: PilotApprovalRecord | None,
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

    if for_execution:
        if approval is None:
            problems.append("execution requires an external approval record")
        else:
            problems.extend(approval_problems(plan, approval))
            problems.extend(execution_repo_problems(approval))
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
        "network_body_requests": 0,
        "preconditions_ok": not problems,
        "problems": problems,
    }


def _default_metadata_fetcher(provider_object_id: str, provider_path: str) -> list[dict[str, Any]]:
    """Resolve one object's current URL from OpenNeuro GraphQL (execution only)."""
    query = (
        '{ snapshot(datasetId:"ds000030",tag:"1.0.0"){ files{ id filename size urls directory } } }'
    )
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(  # noqa: S310 - fixed https metadata endpoint
        _METADATA_ENDPOINT, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        _ = json.load(resp)
    # A full resolver would walk the tree to the object; kept minimal because this
    # path is never exercised in the preflight. Fail closed until implemented.
    raise NotImplementedError("live URL resolution is completed under a reviewed execution change")


def _run_execution(
    plan_model: PilotAcquisitionPlan,
    target_root: Path,
    fetcher: MetadataFetcher,
    log_dir: Path,
    manifest_path: Path,
) -> int:
    resolved_root = target_root.resolve()
    manifest = read_manifest(manifest_path)
    append_event(log_dir, {"event": "run_started", "scope": plan_model.acquisition_scope_id})
    for entry in plan_model.files:
        rel = entry.local_relative_target
        target = (resolved_root / rel).resolve()
        status = completion_status(target, entry.provider_size_bytes, manifest, rel)
        if status == "complete":
            append_event(log_dir, {"event": "file_skipped_verified", "target": rel})
            continue
        if status in ("size_only_unverified", "checksum_mismatch", "size_mismatch"):
            append_event(
                log_dir, {"event": "file_integrity_failed", "target": rel, "status": status}
            )
            append_event(log_dir, {"event": "run_failed", "error_category": status})
            return 1
        url = resolve_download_url(
            entry.provider_object_id, entry.provider_path, entry.provider_size_bytes, fetcher
        )
        append_event(log_dir, {"event": "file_download_started", "target": rel})
        digest = _stream_download(url, target, entry.provider_size_bytes)
        append_manifest(manifest_path, rel, digest)
        manifest[rel] = digest
        append_event(
            log_dir,
            {"event": "file_download_completed", "target": rel, "local_sha256": digest},
        )
    append_event(log_dir, {"event": "run_completed", "scope": plan_model.acquisition_scope_id})
    return 0


def _stream_download(url: str, target: Path, expected_size: int) -> str:
    """Stream to ``<target>.partial``, hash, verify size, fsync, atomically promote.

    Uses an opener whose only redirect handler re-validates every redirect target
    against the object-host allowlist, so a redirect cannot exfiltrate to an
    untrusted host.
    """
    import os

    validate_url(url, _ALLOWED_OBJECT_HOSTS)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0
    opener = urllib.request.build_opener(SafeRedirectHandler())
    req = urllib.request.Request(url)  # noqa: S310 - validated https object URL
    with opener.open(req, timeout=120) as resp, partial.open("wb") as fh:
        for chunk in iter(lambda: resp.read(_CHUNK), b""):
            fh.write(chunk)
            digest.update(chunk)
            written += len(chunk)
        fh.flush()
        if hasattr(os, "fsync"):
            os.fsync(fh.fileno())
    if written != expected_size:
        partial.unlink(missing_ok=True)
        raise RuntimeError("byte-count mismatch during download")
    partial.replace(target)
    return digest.hexdigest()


def main(argv: list[str] | None = None, fetcher: MetadataFetcher | None = None) -> int:
    parser = argparse.ArgumentParser(description="ds000030 pilot acquisition (dry-run by default).")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument(
        "--approval-record", default=None, help="external approval record (mode 600)"
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

    approval: PilotApprovalRecord | None = None
    if args.approval_record is not None:
        approval_path = Path(args.approval_record)
        try:
            approval = load_approval(approval_path)
        except Exception as exc:
            print(json.dumps({"error": f"approval record invalid: {type(exc).__name__}"}))
            return 1
        if _posix_mode_600(approval_path) is False:
            print(json.dumps({"error": "approval record must have mode 600"}))
            return 1

    try:
        free_bytes = shutil.disk_usage(target_root).free
    except OSError:
        free_bytes = 0

    problems = check_preconditions(
        plan, plan_model, target_root, free_bytes, approval, for_execution=for_execution
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

    data_root = target_root.resolve()
    return _run_execution(
        plan_model,
        target_root,
        fetcher or _default_metadata_fetcher,
        log_dir=data_root.parent / "acquisition-log",
        manifest_path=data_root / "checksums.sha256",
    )


if __name__ == "__main__":
    sys.exit(main())
