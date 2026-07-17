"""Collect non-secret runtime provenance for reproducibility records.

Every recorded result must be traceable to the environment that produced it.
This module gathers that environment description in a machine-readable form.

Disclosure rules enforced here:

* No network access is performed.
* No environment-variable values are read or emitted.
* No username, home-directory path, or home-directory content is emitted.
  Paths under the user home are redacted to ``~`` before being reported.
* No participant, dataset, or study-outcome information is touched.
* An optional component that is absent is reported as absent. It is never
  reported as present, and its absence is never reported as an error.

The module reports only what it actually inspected. It makes no claim about
external neuroimaging tools such as FSL, AFNI, or FreeSurfer, because it does
not check them; ``scripts/verify.ps1`` and ``scripts/verify.sh`` cover the
repository, and system-tool readiness is verified separately.

Command line:

    python -m neuromultiverse.runtime --json
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, TypedDict

from neuromultiverse import __version__

__all__ = [
    "KEY_PACKAGES",
    "GitProvenance",
    "RuntimeMetadata",
    "TorchProvenance",
    "collect_runtime_metadata",
    "main",
]

#: Packages whose versions materially affect numerical results and are therefore
#: recorded with every run. Ordered for stable output.
KEY_PACKAGES: tuple[str, ...] = (
    "numpy",
    "scipy",
    "pandas",
    "pyarrow",
    "pydantic",
    "PyYAML",
    "nibabel",
    "nilearn",
    "pybids",
    "scikit-learn",
    "joblib",
    "platformdirs",
)

_GIT_TIMEOUT_SECONDS = 10


class GitProvenance(TypedDict):
    """Git commit identity of the working tree, when it can be determined."""

    commit: str | None
    dirty: bool | None
    error: str | None


class TorchProvenance(TypedDict):
    """PyTorch and CUDA description, when PyTorch is installed."""

    installed: bool
    version: str | None
    cuda_build: str | None
    cuda_available: bool | None
    device_count: int | None
    device_name: str | None
    error: str | None


class RuntimeMetadata(TypedDict):
    """Complete runtime provenance record. Field names are stable."""

    schema_version: str
    collected_at_utc: str
    package_version: str
    python_version: str
    python_executable: str
    platform_system: str
    platform_release: str
    platform_version: str
    machine: str
    processor: str
    git: GitProvenance
    packages: dict[str, str | None]
    torch: TorchProvenance


SCHEMA_VERSION = "1"


def _redact_home(raw: str) -> str:
    """Replace a leading user-home path with ``~`` so no username is emitted.

    Falls back to returning the input unchanged only when the home directory
    cannot be resolved, in which case there is nothing to redact against.
    """
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):
        return raw
    if not home:
        return raw
    normalized_home = home.replace("\\", "/")
    normalized_raw = raw.replace("\\", "/")
    if normalized_raw.lower().startswith(normalized_home.lower()):
        return "~" + normalized_raw[len(normalized_home) :]
    return normalized_raw


def _package_version(name: str) -> str | None:
    """Return an installed distribution version, or ``None`` when absent."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def collect_package_versions(names: tuple[str, ...] = KEY_PACKAGES) -> dict[str, str | None]:
    """Map each declared key package to its installed version, or ``None``."""
    return {name: _package_version(name) for name in names}


def parse_dirty(porcelain_output: str) -> bool:
    """Return whether ``git status --porcelain`` output indicates a dirty tree.

    Any non-blank line means at least one tracked file is modified, staged, or
    otherwise deviates from HEAD. A tree with only blank output is clean.
    """
    return any(line.strip() for line in porcelain_output.splitlines())


def _git_executable() -> str:
    """Resolve the absolute path to git, or raise FileNotFoundError.

    Resolving the full path avoids depending on PATH lookup at call time.
    """
    resolved = shutil.which("git")
    if resolved is None:
        raise FileNotFoundError("git")
    return resolved


def _run_git(args: list[str], repo_root: Path) -> str:
    completed = subprocess.run(
        [_git_executable(), *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    return completed.stdout


def collect_git_provenance(repo_root: Path | None = None) -> GitProvenance:
    """Describe the Git commit and dirty state, tolerating a missing Git.

    Git may be absent, the directory may not be a repository, or the call may
    time out. Each case yields a record with ``error`` set rather than raising,
    because provenance collection must never break the run it is describing.
    """
    root = repo_root if repo_root is not None else Path(__file__).resolve().parent
    try:
        commit = _run_git(["rev-parse", "HEAD"], root).strip()
        porcelain = _run_git(["status", "--porcelain"], root)
    except FileNotFoundError:
        return GitProvenance(commit=None, dirty=None, error="git executable not found")
    except subprocess.CalledProcessError as exc:
        return GitProvenance(
            commit=None, dirty=None, error=f"git failed with code {exc.returncode}"
        )
    except subprocess.TimeoutExpired:
        return GitProvenance(commit=None, dirty=None, error="git timed out")
    except OSError as exc:
        return GitProvenance(commit=None, dirty=None, error=f"git could not run: {exc.strerror}")
    return GitProvenance(commit=commit, dirty=parse_dirty(porcelain), error=None)


def collect_torch_provenance() -> TorchProvenance:
    """Describe PyTorch and CUDA, tolerating absence and broken installations.

    PyTorch is an optional dependency resolved against the local NVIDIA driver.
    Several distinct states are normal and none may crash the caller:

    * Not installed at all: ``installed`` is False with no error.
    * Installed and importable: fully described.
    * Distribution metadata present but import raises. This is the classic
      broken-CUDA-install shape on Windows, where the wheel is on disk but a
      dependent DLL fails to load and ``import torch`` raises ``OSError``. The
      package *is* installed, so ``installed`` stays True and the version is
      recovered from distribution metadata rather than from the failed import.
    * Import succeeds but a CUDA query raises.

    Error strings are sanitized to an exception category. Raw exception text is
    never emitted: on Windows a DLL load failure embeds absolute paths, which
    would leak the username and home directory into a provenance record that is
    meant to be shareable.
    """
    installed_version = _package_version("torch")

    try:
        import torch
    except ImportError:
        # Distinguish "absent" from "present but unimportable". A distribution
        # can be recorded as installed while its import machinery fails.
        if installed_version is None:
            return TorchProvenance(
                installed=False,
                version=None,
                cuda_build=None,
                cuda_available=None,
                device_count=None,
                device_name=None,
                error=None,
            )
        return TorchProvenance(
            installed=True,
            version=installed_version,
            cuda_build=None,
            cuda_available=None,
            device_count=None,
            device_name=None,
            error="torch import failed: ImportError",
        )
    except (OSError, RuntimeError) as exc:
        return TorchProvenance(
            installed=installed_version is not None,
            version=installed_version,
            cuda_build=None,
            cuda_available=None,
            device_count=None,
            device_name=None,
            error=f"torch import failed: {type(exc).__name__}",
        )

    try:
        cuda_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count()) if cuda_available else 0
        device_name = str(torch.cuda.get_device_name(0)) if device_count > 0 else None
    except (RuntimeError, AssertionError, OSError) as exc:
        # A driver or runtime mismatch must not abort provenance collection.
        return TorchProvenance(
            installed=True,
            version=str(torch.__version__),
            cuda_build=torch.version.cuda,
            cuda_available=None,
            device_count=None,
            device_name=None,
            error=f"CUDA query failed: {type(exc).__name__}",
        )

    return TorchProvenance(
        installed=True,
        version=str(torch.__version__),
        cuda_build=torch.version.cuda,
        cuda_available=cuda_available,
        device_count=device_count,
        device_name=device_name,
        error=None,
    )


def utc_timestamp() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_runtime_metadata(repo_root: Path | None = None) -> RuntimeMetadata:
    """Collect the full runtime provenance record."""
    return RuntimeMetadata(
        schema_version=SCHEMA_VERSION,
        collected_at_utc=utc_timestamp(),
        package_version=__version__,
        python_version=platform.python_version(),
        python_executable=_redact_home(sys.executable),
        platform_system=platform.system(),
        platform_release=platform.release(),
        platform_version=platform.version(),
        machine=platform.machine(),
        processor=platform.processor(),
        git=collect_git_provenance(repo_root),
        packages=collect_package_versions(),
        torch=collect_torch_provenance(),
    )


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m neuromultiverse.runtime",
        description="Print non-secret runtime provenance for this environment.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON (the only supported output; accepted for explicitness).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation width (default: 2).",
    )
    args = parser.parse_args(argv)
    _ = args.json

    payload: dict[str, Any] = dict(collect_runtime_metadata())
    print(json.dumps(payload, indent=args.indent, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
