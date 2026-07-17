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
* every READY dataset has a VERIFIED license and verified citation, access,
  size, storage, and hash strategy;
* a pinned OpenNeuro snapshot DOI encodes its exact version, and the required
  citation DOIs (PCP Neuro Bureau, ds000030) are recorded exactly;
* a CONFLICT or SOURCE_AMBIGUOUS license can never present as READY or be
  acquisition-permitted, and layered licenses are represented, not collapsed;
* a permissive license is never stated alongside a re-identification clause
  (project ethics must not be attributed to a provider license);
* every gating access state has a documented required manual action;
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
    LicenseStatus,
    openneuro_doi_is_valid,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CITATION_INVENTORY = REPO_ROOT / "docs" / "citation_inventory.md"
DATA_USAGE = REPO_ROOT / "docs" / "data_usage.md"
ACQUISITION_REGISTER = REPO_ROOT / "docs" / "acquisition_register.md"
MANIFEST_TEMPLATE = REPO_ROOT / "data" / "manifests" / "subject_manifest.template.tsv"

PLACEHOLDER = "Authoritative verification required before acquisition."

# The portable data root from the setup documentation. A literal home path or
# username must never appear in a committed governance record.
DATA_ROOT = "$HOME/neuromultiverse-data"

VERIFICATION_DATE = date(2026, 7, 17)

# Optional datasets that must never be authorized for acquisition here.
OPTIONAL_IDS = frozenset({"cobre_raw", "aomic_id1000"})

# Planning-scope controls for ds000030. These are NOT participant selections.
# The next acquisition unit is a bounded five-subject pilot; the planned
# controlled RQ5 subset is ~20 subjects, reached only after the pilot gates pass.
DS000030_PILOT_SUBJECT_COUNT = 5
DS000030_PLANNED_RQ5_SUBJECT_COUNT = 20

# External hash-manifest evidence a dataset must reference to claim a verified
# hash strategy. The manifest itself is created outside Git at acquisition.
HASH_MANIFEST_BASENAME = "checksums.sha256"

# The exact citation DOI required for each verified citation-inventory topic.
REQUIRED_CITATION_DOIS = {
    "Preprocessed Connectomes Project ABIDE derivatives": "10.3389/conf.fninf.2013.09.00041",
    "OpenNeuro ds000030": "10.18112/openneuro.ds000030.v1.0.0",
}

# For a pinned OpenNeuro snapshot, the DOI suffix must encode its version.
SNAPSHOT_DOI_SUFFIX = {"ds000030": ("1.0.0", "openneuro.ds000030.v1.0.0")}

# Access states that gate acquisition and therefore require a documented manual
# action in the acquisition register.
_BLOCKING_STATES = frozenset(
    {
        AccessStatus.MANUAL_AUTHORIZATION_REQUIRED,
        AccessStatus.AUTHORIZATION_PENDING,
        AccessStatus.SOURCE_AMBIGUOUS,
        AccessStatus.PROVIDER_UNAVAILABLE,
        AccessStatus.BLOCKED,
    }
)

# A permissive license placed next to a re-identification clause would falsely
# attribute the project's own ethics rule to that license.
_FALSE_ATTRIBUTION_RE = re.compile(r"(?i)(CC0|CC BY 4\.0)[^.\n]{0,80}re-?identification")

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
            license_status=LicenseStatus.VERIFIED,
            repository_license_id="CC BY-NC-SA 3.0",
            upstream_license_ids=[],
            effective_use_restrictions=[
                "no_commercial_use",
                "no_redistribution",
                "attribution_required",
                "share_alike",
                "registration_required",
            ],
            access_status=AccessStatus.MANUAL_AUTHORIZATION_REQUIRED,
            registration_required=True,
            approval_required=False,
            redistribution_allowed=False,
            commercial_use_allowed=False,
            # The published usage-agreement page states the data are anonymized
            # and contain no PHI, but does not state an explicit contractual
            # re-identification clause. Anonymization is not that clause, so this
            # provider fact is False; the project's own prohibition is separate.
            provider_reidentification_restricted=False,
            expected_size_bytes=None,
            expected_size_source=(
                "FCP-INDI S3 object listing at acquisition; phenotypic file "
                "Phenotypic_V1_0b_preprocessed1.csv verified at 449443 bytes"
            ),
            verification_date=VERIFICATION_DATE,
            citation_ids=["ABIDE-I", "Preprocessed Connectomes Project ABIDE derivatives"],
            target_root=f"{DATA_ROOT}/abide_i_pcp",
            hash_algorithm="sha256",
            citation_verified=True,
            size_verified=False,
            storage_verified=False,
            hash_strategy_verified=True,
            required_manual_action=(
                "Register a NITRC account and join the 1000 Functional Connectomes "
                "Project / INDI resource, then be logged in at download time."
            ),
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
            license_status=LicenseStatus.VERIFIED,
            repository_license_id="CC0",
            upstream_license_ids=[],
            # CC0 imposes no license restriction; the project still never
            # redistributes participant-level data (a standing prohibition).
            effective_use_restrictions=["no_redistribution"],
            access_status=AccessStatus.READY,
            registration_required=False,
            approval_required=False,
            redistribution_allowed=False,
            commercial_use_allowed=True,
            provider_reidentification_restricted=False,
            expected_size_bytes=85127263296,
            expected_size_source=(
                "OpenNeuro GraphQL snapshot size for tag 1.0.0 (full snapshot). The "
                f"whole snapshot is NOT acquired: the next unit is a bounded "
                f"{DS000030_PILOT_SUBJECT_COUNT}-subject pilot whose size is computed "
                "from per-file snapshot metadata for the selected subjects before download; "
                f"the planned controlled RQ5 subset is ~{DS000030_PLANNED_RQ5_SUBJECT_COUNT} "
                "subjects, reached only after the pilot gates pass."
            ),
            verification_date=VERIFICATION_DATE,
            citation_ids=["OpenNeuro ds000030"],
            target_root=f"{DATA_ROOT}/ds000030",
            hash_algorithm="sha256",
            citation_verified=True,
            size_verified=True,
            storage_verified=False,
            hash_strategy_verified=True,
            required_manual_action=None,
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
            # Layered-license conflict: the figshare record displays CC BY 4.0,
            # but its own description states the data was "originally released
            # under Creative Commons -- Attribution Non-Commercial" (upstream
            # INDI COBRE). Unresolved until the publisher clarifies.
            license_id="AMBIGUOUS: figshare CC BY 4.0 vs upstream COBRE CC BY-NC",
            license_status=LicenseStatus.CONFLICT,
            repository_license_id="CC BY 4.0",
            upstream_license_ids=["CC BY-NC"],
            effective_use_restrictions=[
                "no_commercial_use",
                "no_redistribution",
                "attribution_required",
            ],
            access_status=AccessStatus.SOURCE_AMBIGUOUS,
            registration_required=False,
            approval_required=False,
            redistribution_allowed=False,
            commercial_use_allowed=False,
            provider_reidentification_restricted=False,
            expected_size_bytes=657308547,
            expected_size_source="figshare API article 4197885 (297 files, total bytes)",
            verification_date=VERIFICATION_DATE,
            citation_ids=["COBRE", "NIAK COBRE derivative release"],
            target_root=f"{DATA_ROOT}/cobre_niak",
            hash_algorithm="sha256",
            citation_verified=True,
            size_verified=True,
            storage_verified=False,
            hash_strategy_verified=True,
            required_manual_action=(
                "Obtain written clarification from the derivative publisher on the "
                "figshare CC BY 4.0 vs upstream COBRE CC BY-NC layered-license conflict."
            ),
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
            if record.license_status is not LicenseStatus.VERIFIED:
                problems.append(f"{rid}: READY dataset must have a VERIFIED license status")
            if not record.citation_ids:
                problems.append(f"{rid}: READY dataset lacks a citation")
            if record.expected_size_bytes is None:
                problems.append(f"{rid}: READY dataset lacks a verified size")
            if not record.target_root:
                problems.append(f"{rid}: READY dataset lacks a storage target")
            if record.hash_algorithm not in ("sha256", "sha512"):
                problems.append(f"{rid}: READY dataset lacks a supported hash strategy")

        # A conflicted or ambiguous license can never authorize acquisition.
        if record.license_status is LicenseStatus.CONFLICT:
            if record.acquisition_permitted:
                problems.append(f"{rid}: CONFLICT license must not be acquisition_permitted")
            if record.access_status is AccessStatus.READY:
                problems.append(f"{rid}: CONFLICT license must not be READY")
        if record.access_status is AccessStatus.SOURCE_AMBIGUOUS and record.acquisition_permitted:
            problems.append(f"{rid}: SOURCE_AMBIGUOUS must not be acquisition_permitted")

        # Layered licenses must be represented, not collapsed to one.
        differs = record.repository_license_id is not None and any(
            u != record.repository_license_id for u in record.upstream_license_ids
        )
        if differs and record.license_status is not LicenseStatus.CONFLICT:
            problems.append(
                f"{rid}: repository and upstream licenses differ but status is not CONFLICT"
            )

        # A pinned snapshot's DOI must encode its version exactly.
        if rid in SNAPSHOT_DOI_SUFFIX:
            version, _suffix = SNAPSHOT_DOI_SUFFIX[rid]
            if record.version != version:
                problems.append(f"{rid}: record version {record.version!r} != pinned {version!r}")
            doi = _extract_openneuro_doi(_citation_doi("OpenNeuro ds000030"))
            if doi is None or not openneuro_doi_is_valid(doi, rid, version):
                problems.append(
                    f"{rid}: snapshot DOI must be a valid versioned OpenNeuro DOI for v{version}"
                )

        # Explicit prerequisite consistency.
        if record.citation_verified and any(c not in verified_topics for c in record.citation_ids):
            problems.append(f"{rid}: citation_verified=true but a citation id is not Verified")
        if record.size_verified and record.expected_size_bytes is None:
            problems.append(f"{rid}: size_verified=true but expected_size_bytes is absent")
        if record.hash_strategy_verified and record.hash_algorithm not in ("sha256", "sha512"):
            problems.append(f"{rid}: hash_strategy_verified=true but hash_algorithm unsupported")
        if record.storage_verified and not _register_documents_capacity(rid):
            problems.append(
                f"{rid}: storage_verified=true without documented capacity evidence in the register"
            )
        # ABIDE-specific: the published usage agreement has no explicit provider
        # re-identification clause, so this provider fact must stay False.
        if rid == "abide_i_pcp" and record.provider_reidentification_restricted:
            problems.append(
                f"{rid}: provider_reidentification_restricted=true without a verified explicit "
                "provider re-identification clause"
            )

    problems.extend(_check_citation_dois())
    problems.extend(_check_false_attribution())
    problems.extend(_check_manual_actions(records))
    problems.extend(_check_pilot_scope())
    problems.extend(_check_template())
    return problems


def _extract_openneuro_doi(cell: str | None) -> str | None:
    """Pull the OpenNeuro DOI token out of a DOI cell that may list several."""
    if cell is None:
        return None
    match = re.search(r"10\.18112/openneuro\.\S+", cell)
    return match.group(0).rstrip(".,;") if match else None


def _citation_doi(topic: str) -> str | None:
    """Return the DOI cell of a citation-inventory row by topic."""
    for line in CITATION_INVENTORY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == topic:
            return cells[2]
    return None


def _check_citation_dois() -> list[str]:
    problems: list[str] = []
    for topic, required_doi in REQUIRED_CITATION_DOIS.items():
        doi = _citation_doi(topic)
        if doi is None:
            problems.append(f"citation inventory missing DOI row for {topic!r}")
        elif required_doi not in doi:
            problems.append(f"citation {topic!r} must record DOI {required_doi!r}")
    return problems


def _check_false_attribution() -> list[str]:
    """Reject text that pins a project ethics rule onto a permissive license."""
    problems: list[str] = []
    for doc in (DATA_USAGE, ACQUISITION_REGISTER):
        for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
            if _FALSE_ATTRIBUTION_RE.search(line):
                problems.append(
                    f"{doc.name}:{i}: a permissive license is stated alongside a "
                    "re-identification clause (project ethics must not be attributed to it)"
                )
    return problems


# Explicit dataset -> register heading substring. No fuzzy first-word matching:
# each dataset is mapped to the exact heading fragment of its register section.
REGISTER_SECTION_KEY = {
    "abide_i_pcp": "ABIDE-I Preprocessed Connectomes Project derivatives",
    "ds000030": "OpenNeuro ds000030",
    "cobre_niak": "COBRE NIAK derivative",
}


def _register_sections() -> dict[str, str]:
    """Split the acquisition register into ``## heading -> body`` sections."""
    sections: dict[str, str] = {}
    heading: str | None = None
    buffer: list[str] = []
    for line in ACQUISITION_REGISTER.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections[heading] = "\n".join(buffer)
            heading = line[3:].strip()
            buffer = []
        else:
            buffer.append(line)
    if heading is not None:
        sections[heading] = "\n".join(buffer)
    return sections


def _section_for(dataset_id: str, sections: dict[str, str]) -> str | None:
    key = REGISTER_SECTION_KEY.get(dataset_id)
    if key is None:
        return None
    for heading, body in sections.items():
        if key in heading:
            return body
    return None


def _register_documents_capacity(dataset_id: str) -> bool:
    """Whether the register section records measured storage capacity evidence."""
    body = _section_for(dataset_id, _register_sections())
    if body is None:
        return False
    return "capacity" in body.lower() and "measured" in body.lower()


def _check_manual_actions(records: list[DatasetAccessRecord]) -> list[str]:
    """Structured per-record cross-check of manual actions against the register.

    The decision is driven by the typed ``required_manual_action`` field, not a
    document-wide substring search. Each blocked dataset's register section must
    state its exact access-status value and carry a manual-action line; a READY
    section must not present a required authorization action.
    """
    problems: list[str] = []
    sections = _register_sections()
    for record in records:
        rid = record.dataset_id
        body = _section_for(rid, sections)
        if body is None:
            problems.append(f"{rid}: no acquisition-register section found")
            continue
        lower = body.lower()
        if record.access_status in _BLOCKING_STATES:
            if record.access_status.value not in body:
                problems.append(
                    f"{rid}: register section omits the exact access status "
                    f"{record.access_status.value}"
                )
            if "required manual authorization:" not in lower and "manual action" not in lower:
                problems.append(f"{rid}: blocked dataset lacks a manual-action line in its section")
        elif "required manual authorization:" in lower:
            problems.append(
                f"{rid}: READY dataset must not present a required authorization action"
            )
    return problems


_PILOT_CONFLATE_RE = re.compile(
    r"(?i)"
    r"20[\s-]*subject[s]?\s+pilot"  # "20-subject pilot"
    r"|pilot\s+(?:of|with|uses|is|=|:|contains|has)\s+(?:approximately\s+|about\s+|~)?20\b"
)


def line_conflates_pilot(line: str) -> bool:
    """Whether a line calls the ~20-subject RQ5 set a pilot (a conflation)."""
    return bool(_PILOT_CONFLATE_RE.search(line))


def _check_pilot_scope() -> list[str]:
    """The five-subject pilot and ~20-subject RQ5 subset must stay distinct."""
    problems: list[str] = []
    if DS000030_PILOT_SUBJECT_COUNT != 5:
        problems.append("pilot subject count must be 5")
    if DS000030_PLANNED_RQ5_SUBJECT_COUNT != 20:
        problems.append("planned controlled RQ5 subject count must be 20")
    if DS000030_PILOT_SUBJECT_COUNT == DS000030_PLANNED_RQ5_SUBJECT_COUNT:
        problems.append("pilot and planned RQ5 counts must be distinct")
    for doc in (DATA_USAGE, ACQUISITION_REGISTER):
        for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
            if line_conflates_pilot(line):
                problems.append(
                    f"{doc.name}:{i}: the ~20-subject RQ5 set must not be called a pilot"
                )
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
                "license_status": r.license_status.value,
                "repository_license_id": r.repository_license_id,
                "upstream_license_ids": r.upstream_license_ids,
                "prerequisites": {
                    "citation_verified": r.citation_verified,
                    "size_verified": r.size_verified,
                    "storage_verified": r.storage_verified,
                    "hash_strategy_verified": r.hash_strategy_verified,
                },
                "required_manual_action_present": r.required_manual_action is not None,
                "acquisition_permitted": r.acquisition_permitted,
            }
            for r in records
        ],
        "pilot_subject_count": DS000030_PILOT_SUBJECT_COUNT,
        "planned_rq5_subject_count": DS000030_PLANNED_RQ5_SUBJECT_COUNT,
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
