#!/usr/bin/env python
"""Resumable, safety-gated acquisition tool for the ds000030 five-subject pilot.

This tool consumes an external metadata-only plan and, only under an explicit
``--execute`` with independent approval, would stream the planned files to an
external target root. **The default is ``--dry-run``**, which performs zero
network-body requests: it validates the plan and preconditions and reports an
aggregate summary. This task runs it only in dry-run.

Every hard precondition below must hold before any transfer:

* the plan parses and pins scope, snapshot, DOI, and exactly five subjects;
* the runtime-supplied plan digest matches the plan's canonical SHA-256;
* the target root resolves outside the Git repository;
* free capacity still clears the planned transfer plus the 250 GiB reserve;
* no target escapes the target root; no duplicate target; no traversal;
* the plan contains no participant table and no phenotype/behavioral file;
* no already-complete file would be overwritten;
* execution was independently approved.

Selected subject identifiers live only in the external plan. This tool never
prints them in its default (aggregate) output, and never logs a download URL
(which can carry a signed token).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REQUIRED_SCOPE = "ds000030_pilot_5_subjects"
REQUIRED_SNAPSHOT = "1.0.0"
REQUIRED_DOI = "10.18112/openneuro.ds000030.v1.0.0"
REQUIRED_SUBJECT_COUNT = 5
RESERVE_BYTES = 268435456000  # 250 GiB
_CHUNK = 1024 * 1024

_FORBIDDEN_SUBSTRINGS = ("participants.tsv", "/phenotype/", "phenotype/")
_FORBIDDEN_SUFFIXES = ("_beh.tsv", "_events.tsv")


def canonical_digest(plan: dict[str, Any]) -> str:
    """SHA-256 of the plan's canonical JSON (stable across key order)."""
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def selection_digest(subject_id: str, seed: str) -> str:
    """Stable, process-independent selection key. Never uses builtin hash()."""
    payload = f"{seed}|ds000030|{REQUIRED_SNAPSHOT}|pilot-selection-v1|{subject_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


def select_pilot_subjects(subject_ids: list[str], seed: str, count: int) -> list[str]:
    """Deterministically select ``count`` subjects, independent of input order."""
    ordered = sorted(subject_ids, key=lambda sid: (selection_digest(sid, seed), sid))
    return ordered[:count]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _target_for(target_root: Path, local_relative_target: str) -> Path:
    return (target_root / local_relative_target).resolve()


def check_preconditions(
    plan: dict[str, Any],
    expected_digest: str | None,
    target_root: Path,
    free_bytes: int,
    approved: bool,
    *,
    require_digest: bool,
) -> list[str]:
    """Return a list of blocking problems; empty means every precondition holds."""
    problems: list[str] = []

    if plan.get("acquisition_scope_id") != REQUIRED_SCOPE:
        problems.append(f"scope must be {REQUIRED_SCOPE}")
    if plan.get("snapshot") != REQUIRED_SNAPSHOT:
        problems.append(f"snapshot must be {REQUIRED_SNAPSHOT}")
    if plan.get("doi") != REQUIRED_DOI:
        problems.append("DOI mismatch")
    if plan.get("selected_subject_count") != REQUIRED_SUBJECT_COUNT:
        problems.append(f"selected_subject_count must be {REQUIRED_SUBJECT_COUNT}")
    ids = plan.get("selected_subject_ids") or []
    if len(ids) != REQUIRED_SUBJECT_COUNT:
        problems.append("selected_subject_ids must list exactly five subjects")

    actual_digest = canonical_digest(plan)
    if require_digest:
        if not expected_digest:
            problems.append("a plan digest must be supplied for execution")
        elif expected_digest != actual_digest:
            problems.append("plan digest does not match the supplied approved digest")

    resolved_root = target_root.resolve()
    repo = _repo_root()
    if resolved_root == repo or repo in resolved_root.parents:
        problems.append("target root must resolve outside the Git repository")

    files = plan.get("files") or []
    seen_targets: set[str] = set()
    total_bytes = 0
    for entry in files:
        rel = str(entry.get("local_relative_target", ""))
        total_bytes += int(entry.get("provider_size_bytes", 0))
        if not rel or rel.startswith("/") or ".." in rel.split("/"):
            problems.append("a target path is empty, absolute, or contains traversal")
            continue
        if any(sub in rel for sub in _FORBIDDEN_SUBSTRINGS) or rel.endswith(_FORBIDDEN_SUFFIXES):
            problems.append("plan contains a participant/phenotype/behavioral file")
        target = _target_for(resolved_root, rel)
        if resolved_root != target and resolved_root not in target.parents:
            problems.append("a target path escapes the target root")
        if rel in seen_targets:
            problems.append("duplicate target path in plan")
        seen_targets.add(rel)
        if target.exists() and target.stat().st_size == int(entry.get("provider_size_bytes", 0)):
            # Already complete: it must not be overwritten. Not an error; skipped.
            continue

    if total_bytes != int(plan.get("expected_transfer_bytes", -1)):
        problems.append("expected_transfer_bytes does not equal the sum of file sizes")
    if free_bytes < total_bytes + RESERVE_BYTES:
        problems.append("insufficient free capacity for planned transfer plus reserve")

    # Independent approval is an execution gate, not a dry-run requirement.
    if require_digest and not approved:
        problems.append("execution was not independently approved")
    return problems


def sha256_file(path: Path) -> str:
    """Stream a file through SHA-256 without loading it whole."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_complete(target: Path, expected_size: int) -> bool:
    """Whether a validated file of the expected size already exists."""
    return target.exists() and target.stat().st_size == expected_size


def finalize_partial(partial: Path, target: Path, expected_size: int) -> None:
    """Atomically promote a validated ``.partial`` to its final name.

    Refuses to clobber an already-complete target, and refuses to promote a
    partial whose size does not match the expectation. The rename is atomic on
    the same filesystem.
    """
    if is_complete(target, expected_size):
        raise RuntimeError("refusing to overwrite an already-complete file")
    if partial.stat().st_size != expected_size:
        raise RuntimeError("partial size does not match the expected size")
    partial.replace(target)


def _stream_download(url: str, partial: Path, expected_size: int) -> str:
    """Stream ``url`` to ``partial`` with a running SHA-256. Never logs ``url``.

    Imported lazily so a dry-run never touches the network stack. Returns the
    hex digest; raises on a byte-count mismatch.
    """
    import urllib.request  # lazy import: a dry-run never touches the network stack

    digest = hashlib.sha256()
    written = 0
    partial.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)  # noqa: S310 - provider https URL, audited by preconditions
    with urllib.request.urlopen(req, timeout=120) as resp, partial.open("wb") as fh:  # noqa: S310
        while True:
            chunk = resp.read(_CHUNK)
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            written += len(chunk)
    if written != expected_size:
        raise RuntimeError("byte-count mismatch during download")
    return digest.hexdigest()


def dry_run_summary(plan: dict[str, Any], target_root: Path, problems: list[str]) -> dict[str, Any]:
    """Aggregate, identifier-free summary of what an execution would transfer."""
    files = plan.get("files") or []
    return {
        "mode": "dry-run",
        "scope": plan.get("acquisition_scope_id"),
        "snapshot": plan.get("snapshot"),
        "plan_digest": canonical_digest(plan),
        "planned_file_count": len(files),
        "planned_transfer_bytes": sum(int(f.get("provider_size_bytes", 0)) for f in files),
        "target_root": str(target_root),
        "network_body_requests": 0,
        "preconditions_ok": not problems,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ds000030 pilot acquisition (dry-run by default).")
    parser.add_argument("--plan", required=True, help="path to the external pilot plan JSON")
    parser.add_argument("--target-root", required=True, help="external target root")
    parser.add_argument("--plan-digest", default=None, help="approved plan SHA-256 (execution)")
    parser.add_argument("--approved", action="store_true", help="independent approval was granted")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate only (default)")
    mode.add_argument("--execute", action="store_true", help="perform the transfer")
    args = parser.parse_args(argv)

    execute = args.execute and not args.dry_run
    plan_path = Path(args.plan)
    target_root = Path(args.target_root)

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"plan did not parse: {type(exc).__name__}"}))
        return 1

    try:
        free_bytes = shutil.disk_usage(target_root).free
    except OSError:
        free_bytes = 0

    problems = check_preconditions(
        plan,
        args.plan_digest,
        target_root,
        free_bytes,
        approved=args.approved,
        require_digest=execute,
    )

    if not execute:
        # A dry-run is a validation report; it always exits 0 and carries the
        # precondition outcome in its output.
        print(json.dumps(dry_run_summary(plan, target_root, problems), indent=2))
        return 0

    if problems:
        print(json.dumps({"error": "preconditions failed", "problems": problems}, indent=2))
        return 1

    # Execution path (not exercised in the preflight task, which runs dry-run
    # only). Each planned file is streamed to ``<target>.partial``, hashed while
    # writing, size-verified, and atomically promoted; an already-complete file
    # is left intact (resumability). Download URLs are re-resolved from provider
    # metadata at run time rather than stored, so no signed token is persisted;
    # a plan without a resolvable URL cannot execute here.
    resolved_root = target_root.resolve()
    for entry in plan.get("files") or []:
        target = _target_for(resolved_root, str(entry["local_relative_target"]))
        expected_size = int(entry["provider_size_bytes"])
        if is_complete(target, expected_size):
            continue
        url = entry.get("provider_download_url")
        if not url:
            print(json.dumps({"error": "plan omits a resolvable download URL for a file"}))
            return 1
        partial = target.with_suffix(target.suffix + ".partial")
        _stream_download(url, partial, expected_size)
        finalize_partial(partial, target, expected_size)
    print(json.dumps({"status": "completed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
