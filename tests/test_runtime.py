"""Tests for the runtime provenance module.

These tests exercise real behaviour: schema shape, JSON round-tripping, the
absent-PyTorch path, Git failure handling, dirty-state parsing, the disclosure
rules, and timestamp format. None of them asserts a hardcoded success flag.
"""

from __future__ import annotations

import builtins
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from neuromultiverse import __version__, runtime

UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_metadata_has_exact_expected_schema() -> None:
    """The record exposes exactly the declared top-level fields."""
    metadata = runtime.collect_runtime_metadata()
    assert set(metadata) == {
        "schema_version",
        "collected_at_utc",
        "package_version",
        "python_version",
        "python_executable",
        "platform_system",
        "platform_release",
        "platform_version",
        "machine",
        "processor",
        "git",
        "packages",
        "torch",
    }
    assert set(metadata["git"]) == {"commit", "dirty", "error"}
    assert set(metadata["torch"]) == {
        "installed",
        "version",
        "cuda_build",
        "cuda_available",
        "device_count",
        "device_name",
        "error",
    }


def test_metadata_reports_running_interpreter_and_package() -> None:
    """Reported version fields describe the interpreter actually running."""
    metadata = runtime.collect_runtime_metadata()
    assert metadata["package_version"] == __version__
    assert metadata["python_version"].startswith("3.11.")
    assert metadata["schema_version"] == runtime.SCHEMA_VERSION


def test_metadata_is_json_serializable_and_round_trips() -> None:
    """The record survives a JSON round trip without loss."""
    metadata = runtime.collect_runtime_metadata()
    encoded = json.dumps(dict(metadata))
    decoded: dict[str, Any] = json.loads(encoded)
    assert decoded["package_version"] == metadata["package_version"]
    assert decoded["packages"] == metadata["packages"]
    assert decoded["git"]["commit"] == metadata["git"]["commit"]


def test_timestamp_is_utc_formatted() -> None:
    """The timestamp is a Z-suffixed second-resolution UTC instant."""
    assert UTC_TIMESTAMP_PATTERN.match(runtime.utc_timestamp())
    metadata = runtime.collect_runtime_metadata()
    assert UTC_TIMESTAMP_PATTERN.match(metadata["collected_at_utc"])


@pytest.mark.parametrize(
    ("porcelain", "expected"),
    [
        ("", False),
        ("\n", False),
        ("   \n  \n", False),
        (" M src/neuromultiverse/runtime.py\n", True),
        ("?? untracked.txt\n", True),
        ("A  staged.txt\n M modified.txt\n", True),
        ("D  deleted.txt", True),
    ],
)
def test_parse_dirty_classifies_porcelain_output(porcelain: str, expected: bool) -> None:
    """Dirty-state parsing follows git porcelain semantics."""
    assert runtime.parse_dirty(porcelain) is expected


def test_git_provenance_reports_error_when_git_executable_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing git binary yields a recorded error, not an exception."""

    def _raise_missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _raise_missing)
    provenance = runtime.collect_git_provenance()
    assert provenance["commit"] is None
    assert provenance["dirty"] is None
    assert provenance["error"] == "git executable not found"


def test_git_provenance_reports_error_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A git failure is recorded rather than raised."""

    def _raise_called_process_error(*_args: object, **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, ["git", "rev-parse", "HEAD"])

    monkeypatch.setattr(subprocess, "run", _raise_called_process_error)
    provenance = runtime.collect_git_provenance()
    assert provenance["commit"] is None
    assert provenance["dirty"] is None
    assert provenance["error"] is not None
    assert "128" in provenance["error"]


def test_git_provenance_reports_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung git call is recorded rather than blocking the caller forever."""

    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(["git"], 10)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    provenance = runtime.collect_git_provenance()
    assert provenance["error"] == "git timed out"


def test_git_provenance_outside_repository_does_not_raise(tmp_path: Path) -> None:
    """Collecting provenance outside a repository yields a record, not a crash."""
    provenance = runtime.collect_git_provenance(tmp_path)
    if provenance["error"] is None:
        # A parent of tmp_path may itself be a repository on some machines.
        assert provenance["commit"] is not None
    else:
        assert provenance["commit"] is None


def test_torch_provenance_when_torch_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """An uninstalled PyTorch is reported as absent, without an error."""
    real_import = builtins.__import__

    def _blocked_import(name: str, *args: object, **kwargs: object) -> Any:
        if name == "torch" or name.startswith("torch."):
            raise ImportError("No module named 'torch'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    provenance = runtime.collect_torch_provenance()
    assert provenance["installed"] is False
    assert provenance["version"] is None
    assert provenance["cuda_available"] is None
    assert provenance["error"] is None


def test_package_versions_report_absent_package_as_none() -> None:
    """A package that is not installed maps to None rather than raising."""
    versions = runtime.collect_package_versions(("numpy", "definitely-not-a-real-package-xyz"))
    assert versions["definitely-not-a-real-package-xyz"] is None
    assert set(versions) == {"numpy", "definitely-not-a-real-package-xyz"}


def test_declared_key_packages_are_all_reported() -> None:
    """Every declared key package appears in the record."""
    metadata = runtime.collect_runtime_metadata()
    assert set(metadata["packages"]) == set(runtime.KEY_PACKAGES)


def test_output_carries_no_secret_bearing_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment-variable values never reach the output.

    A sentinel secret is planted in the environment under names the module
    would be most tempting to read. It must not appear anywhere in the JSON.
    """
    sentinel = "s3cr3t-sentinel-value-must-not-appear"
    for name in ("API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "PASSWORD", "NM_TEST_SECRET"):
        monkeypatch.setenv(name, sentinel)

    encoded = json.dumps(dict(runtime.collect_runtime_metadata()))
    assert sentinel not in encoded


def test_output_carries_no_username_or_home_path() -> None:
    """The user home directory and username are redacted from reported paths."""
    metadata = runtime.collect_runtime_metadata()
    home = str(Path.home()).replace("\\", "/")
    encoded = json.dumps(dict(metadata))
    assert home.lower() not in encoded.lower()
    # The executable is still reported, just rooted at ~.
    assert metadata["python_executable"]


def test_redact_home_rewrites_home_prefix_only() -> None:
    """Home-prefixed paths are redacted; unrelated paths are left intact."""
    home = Path.home()
    redacted = runtime._redact_home(str(home / "some" / "tool" / "python.exe"))
    assert redacted.startswith("~/")
    assert "some/tool/python.exe" in redacted

    unrelated = runtime._redact_home("/opt/tools/python3")
    assert unrelated == "/opt/tools/python3"


def test_cli_emits_parsable_json(capsys: pytest.CaptureFixture[str]) -> None:
    """The module CLI prints JSON and exits zero."""
    exit_code = runtime.main(["--json"])
    assert exit_code == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == runtime.SCHEMA_VERSION
    assert payload["package_version"] == __version__


def test_cli_respects_indent_argument(capsys: pytest.CaptureFixture[str]) -> None:
    """The indent argument changes formatting without breaking JSON."""
    assert runtime.main(["--json", "--indent", "0"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)


@pytest.fixture(autouse=True)
def _no_network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail loudly if provenance collection ever opens a socket."""
    import socket

    def _blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime provenance collection must not access the network")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    yield
