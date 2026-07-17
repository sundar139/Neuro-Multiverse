#!/usr/bin/env python
"""Validate the data-acquisition governance records against the typed contracts.

This validator is offline and read-only. It never contacts a data provider,
never downloads data, and never writes into the repository: provider
verification (which reads authoritative web sources) is a separate, human-run
activity, and its findings are transcribed into ``docs/`` and into the canonical
records below. This script only checks internal consistency of what was
transcribed:

* every required dataset record validates through the typed models;
* every dataset carries a verification date;
* every citation id resolves to a *verified* row in the citation inventory;
* no record still holds the acquisition placeholder;
* every READY dataset has verified license, citation, access, size, storage,
  and hash strategy;
* optional datasets can never be marked acquisition-permitted;
* no record carries an absolute user-home path, username, or secret-like value;
* the subject-manifest template is header-only and matches the model columns.

A machine-readable summary is written under a fresh temporary directory (never
the repository). The script exits nonzero on any inconsistency.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import date
from pathlib import Path

from neuromultiverse.data_contracts import (
    SUBJECT_MANIFEST_COLUMNS,
    AccessStatus,
    DatasetAccessRecord,
    DatasetRole,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CITATION_INVENTORY = REPO_ROOT / "docs" / "citation_inventory.md"
MANIFEST_TEMPLATE = REPO_ROOT / "data" / "manifests" / "subject_manifest.template.tsv"

PLACEHOLDER = "Authoritative verification required before acquisition."

# The portable data root from the setup documentation. A literal home path or
# username must never appear in a committed governance record.
DATA_ROOT = "$HOME/neuromultiverse-data"

VERIFICATION_DATE = date(2026, 7, 17)

# Optional datasets that must never be authorized for acquisition here.
OPTIONAL_IDS = frozenset({"cobre_raw", "aomic_id1000"})

# Patterns that must not appear in any record value.
_SECRET_RE = re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token|cookie|bearer)\s*[:=]")
_HOME_RE = re.compile(r"/home/(?!\$)[^/\s]+|/Users/(?!\$)[^/\s]+|[A-Za-z]:[\\/]Users")


def required_records() -> list[DatasetAccessRecord]:
    """The canonical governance records for the three required datasets.

    Every field was transcribed from an authoritative source during provider
    verification (see ``docs/acquisition_register.md``). Constructing these
    records runs the full typed-contract validation.
    """
    return [
        DatasetAccessRecord(
            dataset_id="abide_i_pcp",
            dataset_name="ABIDE-I Preprocessed Connectomes Project derivatives",
            role=DatasetRole.MAIN_MULTIVERSE,
            provider="Preprocessed Connectomes Project / FCP-INDI",
            authoritative_sources=[
                "http://fcon_1000.projects.nitrc.org/indi/abide/abide_I.html",
                "https://preprocessed-connectomes-project.github.io/abide/",
                "https://s3.amazonaws.com/fcp-indi/data/Projects/ABIDE_Initiative/Outputs/",
            ],
            version="ABIDE-I PCP (Phenotypic_V1_0b_preprocessed1)",
            license_id="CC BY-NC-SA 3.0",
            access_status=AccessStatus.MANUAL_AUTHORIZATION_REQUIRED,
            registration_required=True,
            approval_required=False,
            redistribution_allowed=False,
            commercial_use_allowed=False,
            reidentification_prohibited=True,
            expected_size_bytes=None,
            expected_size_source=(
                "FCP-INDI S3 object listing at acquisition; phenotypic file "
                "Phenotypic_V1_0b_preprocessed1.csv verified at 449443 bytes"
            ),
            verification_date=VERIFICATION_DATE,
            citation_ids=["ABIDE-I", "Preprocessed Connectomes Project ABIDE derivatives"],
            target_root=f"{DATA_ROOT}/abide_i_pcp",
            hash_algorithm="sha256",
            acquisition_permitted=False,
        ),
        DatasetAccessRecord(
            dataset_id="ds000030",
            dataset_name="OpenNeuro ds000030 (UCLA CNP LA5c Study)",
            role=DatasetRole.RAW_PIPELINE_COMPARISON,
            provider="OpenNeuro",
            authoritative_sources=[
                "https://openneuro.org/datasets/ds000030/versions/1.0.0",
                "https://openneuro.org/crn/graphql",
            ],
            version="1.0.0",
            license_id="CC0",
            access_status=AccessStatus.READY,
            registration_required=False,
            approval_required=False,
            redistribution_allowed=True,
            commercial_use_allowed=True,
            reidentification_prohibited=True,
            expected_size_bytes=85127263296,
            expected_size_source=(
                "OpenNeuro GraphQL snapshot size for tag 1.0.0 (full dataset); the "
                "pilot subset of 20 subjects is computed from per-file snapshot metadata"
            ),
            verification_date=VERIFICATION_DATE,
            citation_ids=["OpenNeuro ds000030"],
            target_root=f"{DATA_ROOT}/ds000030",
            hash_algorithm="sha256",
            acquisition_permitted=False,
        ),
        DatasetAccessRecord(
            dataset_id="cobre_niak",
            dataset_name="COBRE preprocessed with NIAK 0.17 - lightweight release",
            role=DatasetRole.REPLICATION,
            provider="figshare (SIMEXP / P. Bellec)",
            authoritative_sources=[
                "https://figshare.com/articles/dataset/"
                "COBRE_preprocessed_with_NIAK_0_17_-_lightweight_release/4197885",
                "https://api.figshare.com/v2/articles/4197885",
            ],
            version="10.6084/m9.figshare.4197885.v1",
            license_id="CC BY 4.0",
            access_status=AccessStatus.READY,
            registration_required=False,
            approval_required=False,
            redistribution_allowed=True,
            commercial_use_allowed=True,
            reidentification_prohibited=True,
            expected_size_bytes=657308547,
            expected_size_source="figshare API article 4197885 (297 files, total bytes)",
            verification_date=VERIFICATION_DATE,
            citation_ids=["COBRE", "NIAK COBRE derivative release"],
            target_root=f"{DATA_ROOT}/cobre_niak",
            hash_algorithm="sha256",
            acquisition_permitted=False,
        ),
    ]


def verified_citation_topics() -> set[str]:
    """Return the set of citation-inventory topics marked ``Verified``."""
    verified: set[str] = set()
    for line in CITATION_INVENTORY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        topic, status = cells[0], cells[4]
        if status == "Verified":
            verified.add(topic)
    return verified


def _record_values(record: DatasetAccessRecord) -> list[str]:
    values: list[str] = []
    for value in record.model_dump().values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return values


def check(records: list[DatasetAccessRecord]) -> list[str]:
    """Return a list of governance problems; empty means the gate passes."""
    problems: list[str] = []
    verified_topics = verified_citation_topics()

    for record in records:
        rid = record.dataset_id
        values = _record_values(record)

        if record.dataset_id in OPTIONAL_IDS:
            problems.append(f"{rid}: optional dataset must not appear as a required record")

        for value in values:
            if PLACEHOLDER in value:
                problems.append(f"{rid}: unresolved acquisition placeholder in a field")
            if _HOME_RE.search(value):
                problems.append(f"{rid}: absolute user-home path or username in a field: {value!r}")
            if _SECRET_RE.search(value):
                problems.append(f"{rid}: secret-like value in a field")

        for citation_id in record.citation_ids:
            if citation_id not in verified_topics:
                problems.append(
                    f"{rid}: citation id {citation_id!r} does not resolve to a verified "
                    "citation-inventory row"
                )

        if record.acquisition_permitted:
            if record.access_status is not AccessStatus.READY:
                problems.append(f"{rid}: acquisition_permitted with non-READY access")
            if record.dataset_id in OPTIONAL_IDS:
                problems.append(f"{rid}: optional dataset marked acquisition_permitted")

        if record.access_status is AccessStatus.READY:
            if record.license_id == "":
                problems.append(f"{rid}: READY dataset lacks a license")
            if not record.citation_ids:
                problems.append(f"{rid}: READY dataset lacks a citation")
            if record.expected_size_bytes is None:
                problems.append(f"{rid}: READY dataset lacks a verified size")
            if not record.target_root:
                problems.append(f"{rid}: READY dataset lacks a storage target")
            if record.hash_algorithm not in ("sha256", "sha512"):
                problems.append(f"{rid}: READY dataset lacks a supported hash strategy")

    problems.extend(_check_template())
    return problems


def _check_template() -> list[str]:
    problems: list[str] = []
    if not MANIFEST_TEMPLATE.exists():
        return [f"manifest template missing: {MANIFEST_TEMPLATE.name}"]
    lines = [ln for ln in MANIFEST_TEMPLATE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) != 1:
        problems.append("manifest template must be header-only (a data row would be a participant)")
        return problems
    if tuple(lines[0].split("\t")) != SUBJECT_MANIFEST_COLUMNS:
        problems.append("manifest template header does not match the model column order")
    return problems


def main() -> int:
    try:
        records = required_records()
    except Exception as exc:
        print(f"FAIL: a governance record failed typed validation: {exc}")
        return 1

    problems = check(records)

    summary = {
        "verification_date": VERIFICATION_DATE.isoformat(),
        "required_datasets": [
            {
                "dataset_id": r.dataset_id,
                "access_status": r.access_status.value,
                "license_id": r.license_id,
                "acquisition_permitted": r.acquisition_permitted,
            }
            for r in records
        ],
        "problem_count": len(problems),
        "problems": problems,
    }
    out_dir = Path(tempfile.mkdtemp(prefix="nm_data_governance_"))
    summary_path = out_dir / "data_governance_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary written to {summary_path}")

    if problems:
        print(f"RESULT: FAIL ({len(problems)} problem(s))")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"RESULT: PASS ({len(records)} required datasets validated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
