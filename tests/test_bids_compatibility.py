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
    _SANITIZED_CENSUS,
    _SANITIZED_JSON_PARSE,
    _SANITIZED_NONEMPTY_DEST,
    REMOVED_FIELDS,
    BIDSCompatibilityRecord,
    CompatibilityCensus,
    CompatibilityError,
    build_compatibility_view,
    compute_tree_digest,
    sanitize_json,
    verify_view,
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
        last_bold = sorted(s.rglob("*_task-rest_bold.nii.gz"))[-1]
        last_bold.write_bytes(b"X" * (28135460 + diff))
    return s


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, separators=(", ", ": ")) + "\n", encoding="utf-8")


def _write_nii(path: Path, size: int = 1000) -> None:
    """Write a synthetic non-JSON file."""
    path.write_bytes(b"X" * size)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestSanitizeJson:
    def test_removes_both_fields(self) -> None:
        content = json.dumps({"CogAtlasID": "x", "CogPOID": "y", "Keep": 1})
        result, removed, changed = sanitize_json(content)
        assert changed is True
        assert removed == ["CogAtlasID", "CogPOID"]
        parsed = json.loads(result)
        assert "CogAtlasID" not in parsed
        assert "CogPOID" not in parsed
        assert parsed["Keep"] == 1

    def test_removes_only_atlas(self) -> None:
        content = json.dumps({"CogAtlasID": "x", "Keep": 1})
        result, removed, changed = sanitize_json(content)
        assert changed is True
        assert removed == ["CogAtlasID"]
        assert json.loads(result) == {"Keep": 1}

    def test_removes_only_poid(self) -> None:
        content = json.dumps({"CogPOID": "y", "Keep": 1})
        result, removed, changed = sanitize_json(content)
        assert changed is True
        assert removed == ["CogPOID"]
        assert json.loads(result) == {"Keep": 1}

    def test_neither_field_present_returns_original_bytes_unchanged(self) -> None:
        content = json.dumps({"Keep": 1, "Nested": {"a": 1}}, indent=2)
        result, removed, changed = sanitize_json(content)
        assert changed is False
        assert removed == []
        assert result == content  # byte-for-byte identical

    def test_nested_unrelated_values_unchanged(self) -> None:
        content = json.dumps(
            {"CogAtlasID": "x", "Nested": {"Deep": [1, 2, 3], "CogAtlasID": "should-stay"}}
        )
        result, removed, changed = sanitize_json(content)
        assert changed is True
        assert removed == ["CogAtlasID"]
        parsed = json.loads(result)
        assert "CogAtlasID" not in parsed
        # Nested CogAtlasID is a different scope — preserved per spec
        assert parsed["Nested"]["CogAtlasID"] == "should-stay"

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            sanitize_json("not json")


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
        assert result.source_tree_digest_before == result.source_tree_digest_after
        assert result.no_voxel_access
        assert result.evidence_reference.startswith("ds000030-bids-compatibility-sha256:")
        assert evid.exists()

    def test_json_without_fields_remains_byte_identical(
        self, source_bids: Path, repo_root: Path
    ) -> None:
        """JSON files that already lack CogAtlasID/CogPOID must not be rewritten."""
        # Add a JSON file without the target fields
        clean = source_bids / "clean.json"
        _write_json(clean, {"Keep": 1, "Other": "value"})
        # Adjust census — need to match total, so skip; instead check via built result
        clean.unlink()
        # Build and check a specific JSON that had no fields originally
        desc = source_bids / "dataset_description.json"
        desc_orig = desc.read_bytes()
        build_compatibility_view(
            source=source_bids,
            destination=source_bids.parent / "compat_byte",
            repo_root=repo_root,
        )
        # dataset_description.json had no CogAtlasID/CogPOID — must be byte-identical
        dest_desc = source_bids.parent / "compat_byte" / "dataset_description.json"
        assert dest_desc.read_bytes() == desc_orig

    def test_only_json_with_removal_is_rewritten(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_rewrite"
        result = build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        assert result.json_files_changed == 11  # 5 T1w + 5 bold + 1 root = 11 files with CogAtlasID
        # Note: root task-rest_bold.json has CogAtlasID + CogPOID (1 file)
        # 5 subject T1w.json have CogAtlasID (5 files)
        # 5 subject bold.json have CogAtlasID + CogPOID (5 files)
        # Total: 11 files with at least one removed field
        assert result.changed_file_count == 11

    def test_evidence_contains_changed_json_files(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_evid"
        evid = source_bids.parent / "evidence2.json"
        result = build_compatibility_view(
            source=source_bids, destination=dest, repo_root=repo_root, evidence_path=evid
        )
        parsed = json.loads(evid.read_text(encoding="utf-8"))
        assert "changed_json_files" in parsed
        assert isinstance(parsed["changed_json_files"], list)
        assert len(parsed["changed_json_files"]) == result.changed_file_count
        # Check sorted by relative_path
        paths = [e["relative_path"] for e in parsed["changed_json_files"]]
        assert paths == sorted(paths)

    def test_changed_entry_fields(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_entry"
        evid = source_bids.parent / "evidence3.json"
        build_compatibility_view(
            source=source_bids,
            destination=dest,
            repo_root=repo_root,
            evidence_path=evid,
        )
        parsed = json.loads(evid.read_text(encoding="utf-8"))
        for entry in parsed["changed_json_files"]:
            assert "relative_path" in entry
            assert "source_sha256" in entry
            assert "destination_sha256" in entry
            assert "removed_fields" in entry
            assert entry["source_sha256"] != entry["destination_sha256"]
            assert isinstance(entry["removed_fields"], list)
            assert all(f in REMOVED_FIELDS for f in entry["removed_fields"])

    def test_aggregate_counts_reconcile(self, source_bids: Path, repo_root: Path) -> None:
        evid = source_bids.parent / "evidence4.json"
        build_compatibility_view(
            source=source_bids,
            destination=source_bids.parent / "compat_recon",
            repo_root=repo_root,
            evidence_path=evid,
        )
        parsed = json.loads(evid.read_text(encoding="utf-8"))
        # Aggregate removed_field_counts must equal sum of per-file entries
        per_file_counts: dict[str, int] = dict.fromkeys(REMOVED_FIELDS, 0)
        for entry in parsed["changed_json_files"]:
            for f in entry["removed_fields"]:
                per_file_counts[f] += 1
        assert parsed["removed_field_counts"] == per_file_counts

    def test_source_unchanged_tree_digest(self, source_bids: Path, repo_root: Path) -> None:
        src_digest_before = compute_tree_digest(source_bids)
        dest = source_bids.parent / "compat_digest"
        result = build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        src_digest_after = compute_tree_digest(source_bids)
        assert src_digest_before == src_digest_after
        assert result.source_tree_digest_before == result.source_tree_digest_after
        assert result.source_unchanged is True

    def test_source_mutation_detected(self, source_bids: Path, repo_root: Path) -> None:
        """A simulated source mutation must be detected."""
        dest = source_bids.parent / "compat_mut"
        build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        # Mutate source after build
        mutated = next(iter(source_bids.rglob("*.json")))
        mutated.write_text('{"mutated": true}', encoding="utf-8")
        # detect by re-running and observing source_unchanged
        dest2 = source_bids.parent / "compat_mut2"
        with pytest.raises(CompatibilityError, match="source census mismatch"):
            # File count still 22 but bytes differ — census catches it
            build_compatibility_view(source=source_bids, destination=dest2, repo_root=repo_root)

    def test_hidden_destination_fails(self, source_bids: Path, repo_root: Path) -> None:
        """A destination containing only hidden files must fail."""
        dest = source_bids.parent / "hidden_dest"
        dest.mkdir()
        (dest / ".keep").write_text("")
        with pytest.raises(CompatibilityError, match=_SANITIZED_NONEMPTY_DEST):
            build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)

    def test_source_unchanged(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_src"
        src_digest_before = compute_tree_digest(source_bids)
        build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        src_digest_after = compute_tree_digest(source_bids)
        assert src_digest_before == src_digest_after

    def test_non_json_byte_identity(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_nonjson"
        build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        for p in source_bids.rglob("*"):
            if p.is_file() and p.suffix.lower() != ".json":
                rel = p.relative_to(source_bids)
                dest_file = dest / rel
                assert dest_file.exists()
                assert p.read_bytes() == dest_file.read_bytes(), f"content changed for {rel}"

    def test_both_fields_removed(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "compat_fields"
        result = build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        assert result.removed_field_counts.get("CogAtlasID", 0) > 0
        assert result.removed_field_counts.get("CogPOID", 0) > 0
        for p in dest.rglob("*.json"):
            content = p.read_text(encoding="utf-8")
            if "CogAtlasID" in content:
                pytest.fail(f"CogAtlasID found in {p}")

    def test_malformed_json_fails(self, tmp_path: Path, repo_root: Path) -> None:
        """Malformed JSON in an otherwise-valid source reaches the parser."""
        src = tmp_path / "bad_json_src"
        src.mkdir()
        # Build a valid 22-file/187570603-byte source with one malformed JSON
        _write_json(src / "dataset_description.json", {"Name": "test"})
        _write_json(src / "task-rest_bold.json", {"TaskName": "rest"})
        for i in range(5):
            sub = f"sub-SYNTH{i:02d}"
            (src / sub / "anat").mkdir(parents=True)
            (src / sub / "func").mkdir(parents=True)
            _write_nii(src / sub / "anat" / f"{sub}_T1w.nii.gz", size=9378530)
            _write_json(src / sub / "anat" / f"{sub}_T1w.json", {"Manufacturer": "Test"})
            _write_nii(src / sub / "func" / f"{sub}_task-rest_bold.nii.gz", size=28135460)
            _write_json(src / sub / "func" / f"{sub}_task-rest_bold.json", {"TaskName": "rest"})
        # Total is now 22 files. Replace one JSON with malformed content
        # Remove a JSON first to keep count at 22
        target = src / "sub-SYNTH00" / "anat" / "sub-SYNTH00_T1w.json"
        target.write_text("{invalid", encoding="utf-8")
        current = sum(p.stat().st_size for p in src.rglob("*") if p.is_file())
        # Adjust bytes to exactly 187570603
        diff = 187570603 - current
        if diff != 0:
            last = sorted(src.rglob("*.nii.gz"))[-1]
            last_data = last.read_bytes()
            last.write_bytes(last_data + b"X" * diff)

        dest = src.parent / "bad_dest"
        with pytest.raises(CompatibilityError, match=_SANITIZED_JSON_PARSE):
            build_compatibility_view(source=src, destination=dest, repo_root=repo_root)

    def test_malformed_json_cli_no_paths(self, source_bids: Path, repo_root: Path) -> None:
        """Success summary must be path-free."""
        dest = source_bids.parent / "compat_cli"
        result = build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        d = result.to_dict()
        serialized = json.dumps(d)
        assert "sub-" not in serialized
        assert "evidence_reference" in serialized

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
        with pytest.raises(CompatibilityError, match=_SANITIZED_CENSUS):
            build_compatibility_view(source=src, destination=dest, repo_root=repo_root)

    def test_existing_nonempty_dest_fails(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "existing"
        dest.mkdir()
        (dest / "existing_file.txt").write_text("data")
        with pytest.raises(CompatibilityError, match=_SANITIZED_NONEMPTY_DEST):
            build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)

    def test_hidden_only_dest_fails(self, source_bids: Path, repo_root: Path) -> None:
        dest = source_bids.parent / "hidden_only"
        dest.mkdir()
        (dest / ".DS_Store").write_text("garbage")
        with pytest.raises(CompatibilityError, match=_SANITIZED_NONEMPTY_DEST):
            build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)

    def test_relative_path_fails(self, repo_root: Path) -> None:
        with pytest.raises(CompatibilityError, match="must be an absolute path"):
            build_compatibility_view(
                source=Path("relative"),
                destination=repo_root.parent / "d",
                repo_root=repo_root,
            )

    def test_no_voxel_reader_imported(self) -> None:
        """Confirm nibabel or numpy is not imported by the builder at module level."""

        import neuromultiverse.bids_compatibility as bc

        source = inspect.getsource(bc)
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
            source=source_bids,
            destination=dest,
            repo_root=repo_root,
            evidence_path=evid,
        )
        assert evid.exists()
        parsed = json.loads(evid.read_text(encoding="utf-8"))
        assert parsed.get("schema") == "ds000030-bids-compatibility-v1"
        assert "source_acquisition_evidence_reference" in parsed
        assert "source_raw_validation_evidence_reference" in parsed
        assert "source_tree_digest_before" in parsed
        assert "source_tree_digest_after" in parsed
        assert parsed["source_tree_digest_before"] == parsed["source_tree_digest_after"]
        assert "changed_json_files" in parsed
        assert "json_files_changed" in parsed
        assert "removed_field_counts" in parsed
        assert "no_voxel_array_access" in parsed
        assert parsed["no_voxel_array_access"] is True
        assert result1.evidence_reference.startswith("ds000030-bids-compatibility-sha256:")


class TestCompatibilityCensus:
    def test_from_tree(self, source_bids: Path) -> None:
        census = CompatibilityCensus.from_tree(source_bids)
        assert census.file_count == 22

    def test_equality(self) -> None:
        assert CompatibilityCensus(22, 100) == CompatibilityCensus(22, 100)

    def test_repr(self) -> None:
        r = repr(CompatibilityCensus(1, 2))
        assert "files=1" in r
        assert "bytes=2" in r


class TestVerifyView:
    def test_non_json_byte_failure_sanitized(self, source_bids: Path, repo_root: Path) -> None:
        """Verification failure for non-JSON changes uses sanitized message."""
        dest = source_bids.parent / "verify_dest"
        build_compatibility_view(source=source_bids, destination=dest, repo_root=repo_root)
        # Corrupt a non-JSON file
        target = next(iter(dest.rglob("*.nii.gz")))
        target.write_bytes(b"corrupted")
        with pytest.raises(CompatibilityError) as exc:
            verify_view(source_bids, dest, repo_root)
        msg = str(exc.value)
        assert "/" not in msg.replace(" ", ""), f"path leaked in: {msg}"
        assert "sub-" not in msg.lower()


class TestBIDSCompatibilityRecord:
    def test_sha256_stable(self) -> None:
        r1 = BIDSCompatibilityRecord({"a": 1})
        r2 = BIDSCompatibilityRecord({"a": 1})
        assert r1.sha256 == r2.sha256

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
