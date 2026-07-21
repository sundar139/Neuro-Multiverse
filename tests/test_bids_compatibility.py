"""Synthetic tests for the BIDS compatibility-view builder.

No test reads a real BIDS dataset or touches a participant identifier. All
fixtures are ephemeral temporary directories.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from neuromultiverse.bids_compatibility import (
    BIDSCompatibilityRecord,
    CompatibilityCensus,
    CompatibilityError,
    build_compatibility_view,
    compute_tree_digest,
    sanitize_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A synthetic repository root."""
    r = tmp_path / "repo"
    r.mkdir()
    (r / "src").mkdir()
    (r / "scripts").mkdir()
    return r


@pytest.fixture
def source_bids(tmp_path: Path) -> Path:
    """A minimal synthetic BIDS dataset matching the accepted pilot census.

    22 files, 187,570,603 bytes exactly.
    """
    s = tmp_path / "source_bids"
    s.mkdir()
    # Root metadata
    _write_json(s / "dataset_description.json", {"Name": "test"})
    _write_json(
        s / "task-rest_bold.json",
        {
            "CogAtlasID": "not-a-uri",
            "CogPOID": "also-not-uri",
            "TaskName": "rest",
            "RepetitionTime": 2.0,
        },
    )
    # 5 subjects x 4 files each = 20 subject files
    for i in range(5):
        sub = f"sub-SYNTH{i:02d}"
        sub_dir = s / sub
        anat = sub_dir / "anat"
        func = sub_dir / "func"
        anat.mkdir(parents=True)
        func.mkdir(parents=True)
        _write_nii(anat / f"{sub}_T1w.nii.gz", size=9378530)
        _write_json(anat / f"{sub}_T1w.json", {"CogAtlasID": "bad-value", "Manufacturer": "Test"})
        _write_nii(func / f"{sub}_task-rest_bold.nii.gz", size=28135460)
        _write_json(
            func / f"{sub}_task-rest_bold.json",
            {
                "CogAtlasID": "also-bad",
                "CogPOID": "also-bad-too",
                "TaskName": "rest",
                "RepetitionTime": 2.0,
            },
        )
    # Adjust bytes to hit exactly 187570603
    current = sum(p.stat().st_size for p in s.rglob("*") if p.is_file())
    diff = 187570603 - current
    if diff != 0:
        # Adjust the last bold.nii.gz to make total exact
        last_bold = sorted(s.rglob("*_task-rest_bold.nii.gz"))[-1]
        last_bold.write_bytes(b"X" * (28135460 + diff))
    return s


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_nii(path: Path, size: int = 1000) -> None:
    """Write a synthetic non-JSON file."""
    path.write_bytes(b"X" * size)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestCompatibilityCensus:
    def test_from_tree(self, source_bids: Path) -> None:
        census = CompatibilityCensus.from_tree(source_bids)
        assert census.file_count == 22

    def test_equality(self) -> None:
        assert CompatibilityCensus(22, 100) == CompatibilityCensus(22, 100)
        assert CompatibilityCensus(22, 100) != CompatibilityCensus(23, 100)

    def test_repr(self) -> None:
        r = repr(CompatibilityCensus(1, 2))
        assert "files=1" in r
        assert "bytes=2" in r


class TestSanitizeJson:
    def test_removes_both_fields(self) -> None:
        content = json.dumps({"CogAtlasID": "x", "CogPOID": "y", "Keep": 1})
        result, counts = sanitize_json(content)
        parsed = json.loads(result)
        assert "CogAtlasID" not in parsed
        assert "CogPOID" not in parsed
        assert parsed["Keep"] == 1
        assert counts == {"CogAtlasID": 1, "CogPOID": 1}

    def test_removes_only_atlas(self) -> None:
        content = json.dumps({"CogAtlasID": "x", "Keep": 1})
        result, counts = sanitize_json(content)
        parsed = json.loads(result)
        assert "CogAtlasID" not in parsed
        assert parsed["Keep"] == 1
        assert counts == {"CogAtlasID": 1, "CogPOID": 0}

    def test_removes_only_poid(self) -> None:
        content = json.dumps({"CogPOID": "y", "Keep": 1})
        result, counts = sanitize_json(content)
        parsed = json.loads(result)
        assert "CogPOID" not in parsed
        assert parsed["Keep"] == 1
        assert counts == {"CogAtlasID": 0, "CogPOID": 1}

    def test_neither_field_present(self) -> None:
        content = json.dumps({"Keep": 1, "Nested": {"a": 1}})
        result, counts = sanitize_json(content)
        assert json.loads(result) == {"Keep": 1, "Nested": {"a": 1}}
        assert counts == {"CogAtlasID": 0, "CogPOID": 0}

    def test_nested_unrelated_values_unchanged(self) -> None:
        content = json.dumps({"CogAtlasID": "x", "Nested": {"Deep": [1, 2, 3]}})
        result, _ = sanitize_json(content)
        parsed = json.loads(result)
        assert parsed["Nested"] == {"Deep": [1, 2, 3]}

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            sanitize_json("not json")


class TestBIDSCompatibilityRecord:
    def test_sha256_stable(self) -> None:
        r1 = BIDSCompatibilityRecord({"a": 1})
        r2 = BIDSCompatibilityRecord({"a": 1})
        assert r1.sha256 == r2.sha256
        assert r1.reference.startswith("ds000030-bids-compatibility-sha256:")

    def test_reference_format(self) -> None:
        r = BIDSCompatibilityRecord({"x": 1})
        assert r.reference.startswith("ds000030-bids-compatibility-sha256:")
        assert len(r.reference.split(":")[1]) == 64

    def test_write(self, tmp_path: Path) -> None:
        p = tmp_path / "evidence.json"
        r = BIDSCompatibilityRecord({"test": True})
        r.write(p)
        assert p.exists()
        assert p.stat().st_size > 0
        assert "test" in p.read_text(encoding="utf-8")

    def test_record_isolation(self) -> None:
        r = BIDSCompatibilityRecord({"k": "v"})
        rec = r.record
        rec["k"] = "changed"
        assert r.record["k"] == "v"


class TestBuild:
    def test_valid_creation(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat"
        evid = source_bids.parent / "evidence.json"
        result = build_compatibility_view(
            source=source_bids, destination=dest, repo_root=repo_root, evidence_path=evid
        )
        assert result.source_census_matched
        assert result.json_files_changed > 0
        assert result.non_json_hashes_unchanged
        assert result.source_unchanged
        assert result.no_voxel_access
        assert result.evidence_reference.startswith("ds000030-bids-compatibility-sha256:")
        assert evid.exists()

    def test_source_unchanged(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat2"
        src_digest_before = compute_tree_digest(source_bids)
        build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        src_digest_after = compute_tree_digest(source_bids)
        assert src_digest_before == src_digest_after

    def test_non_json_byte_identity(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat3"
        build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        for p in source_bids.rglob("*"):
            if p.is_file() and p.suffix.lower() != ".json":
                rel = p.relative_to(source_bids)
                dest_file = dest / rel
                assert dest_file.exists()
                assert p.read_bytes() == dest_file.read_bytes(), f"content changed for {rel}"

    def test_both_fields_removed(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat4"
        result = build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        assert result.removed_field_counts.get("CogAtlasID", 0) > 0
        assert result.removed_field_counts.get("CogPOID", 0) > 0
        for p in dest.rglob("*.json"):
            content = p.read_text(encoding="utf-8")
            assert "CogAtlasID" not in content
            assert "CogPOID" not in content

    def test_malformed_json_fails(self, source_bids: Path, repo_root: Path) -> None:
        """Adding a file outside the census fails before JSON sanitize runs."""
        bad = source_bids / "bad.json"
        bad.write_text("{invalid", encoding="utf-8")
        dest = source_bids.parent / "compat_fail"
        with pytest.raises(CompatibilityError, match="source census mismatch"):
            build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        bad.unlink()

    def test_source_inside_repo_fails(self, repo_root: Path) -> None:
        src = repo_root / "inside"
        src.mkdir()
        dest = repo_root.parent / "outside_dest"
        with pytest.raises(CompatibilityError, match="source must lie outside"):
            build_compatibility_view(source=src, destination=dest, repo_root=repo_root)

    def test_dest_inside_repo_fails(self, source_bids: Path, repo_root: Path) -> None:
        dest = repo_root / "inside_dest"
        with pytest.raises(CompatibilityError, match="destination must lie outside"):
            build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)

    def test_source_equals_dest_fails(self, source_bids: Path, repo_root: Path) -> None:
        with pytest.raises(CompatibilityError, match="source and destination must differ"):
            build_compatibility_view(
                source=source_bids, destination=source_bids, repo_root=repo_root
            )

    def test_incorrect_census_fails(self, repo_root: Path) -> None:
        src = repo_root.parent / "bad_source"
        src.mkdir()
        _write_json(src / "dataset_description.json", {"Name": "test"})
        dest = repo_root.parent / "bad_dest"
        with pytest.raises(CompatibilityError, match="source census mismatch"):
            build_compatibility_view(source=src, destination=dest, repo_root=repo_root)

    def test_existing_nonempty_dest_fails(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "existing"
        dest.mkdir()
        (dest / "existing_file.txt").write_text("data")
        with pytest.raises(CompatibilityError, match="destination already contains"):
            build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)

    def test_relative_path_fails(self, repo_root: Path) -> None:
        with pytest.raises(CompatibilityError, match="must be an absolute path"):
            build_compatibility_view(
                source=Path("relative"), destination=repo_root.parent / "d", repo_root=repo_root
            )

    def test_no_voxel_reader_imported(self) -> None:
        """Confirm nibabel or numpy is not imported by the builder at module level."""

        # Check that the module doesn't import nibabel at top level
        import neuromultiverse.bids_compatibility as bc

        source = inspect.getsource(bc)
        # NIfTI readers should not appear at module level
        assert "import nibabel" not in source
        assert "nibabel.load" not in source
        assert "numpy" not in source


class TestCompatibilityResult:
    def test_no_participant_data_in_output(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_result"
        result = build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        d = result.to_dict()
        serialized = json.dumps(d)
        assert "sub-" not in serialized
        assert "evidence_reference" in serialized

    def test_evidence_canonical(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_evid"
        evid = source_bids.parent / "evidence2.json"
        result1 = build_compatibility_view(
            source=source_bids, destination=dest, repo_root=repo_root, evidence_path=evid
        )
        assert evid.exists()
        parsed = json.loads(evid.read_text(encoding="utf-8"))
        assert parsed.get("schema") == "ds000030-bids-compatibility-v1"
        assert "source_acquisition_evidence_reference" in parsed
        assert "source_raw_validation_evidence_reference" in parsed
        assert "source_census" in parsed
        assert "destination_census" in parsed
        assert "source_tree_digest" in parsed
        assert "destination_tree_digest" in parsed
        assert "json_files_changed" in parsed
        assert "removed_field_counts" in parsed
        assert "non_json_hashes_unchanged" in parsed
        assert "no_voxel_array_access" in parsed
        assert "source_unchanged" in parsed
        assert "tool_version" in parsed
        assert "created_at_utc" in parsed
        assert parsed["no_voxel_array_access"] is True
        # Verify the SHA-256-derived reference consistency
        assert result1.evidence_reference.startswith("ds000030-bids-compatibility-sha256:")
