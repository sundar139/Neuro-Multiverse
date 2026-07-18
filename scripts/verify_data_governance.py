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
from neuromultiverse.ds000030_pilot import (
    CONTROLLED_RESERVE_BYTES,
    DS000030_PILOT_EXPECTED_BYTES,
    DS000030_PILOT_FILE_COUNT,
    DS000030_PILOT_PLAN_REFERENCE,
    DS000030_STORAGE_REFERENCE,
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

# Aggregate pilot evidence is the single source of truth in ``ds000030_pilot``
# (imported above): file count, transfer bytes, plan reference, storage
# reference, and the 250 GiB reserve. Only the measured available capacity is
# local to the preflight record.
DS000030_STORAGE_AVAILABLE_BYTES = 996303314944

# External hash-manifest evidence a dataset must reference to claim a verified
# hash strategy. The manifest itself is created outside Git at acquisition.
HASH_MANIFEST_BASENAME = "checksums.sha256"

# Executor + approval surfaces this validator inspects (never reads private
# selected identifiers or the external plan).
EXECUTOR = REPO_ROOT / "scripts" / "acquire_ds000030_pilot.py"
PILOT_MODEL = REPO_ROOT / "src" / "neuromultiverse" / "ds000030_pilot.py"
APPROVAL_DIR = REPO_ROOT / "data" / "acquisition_authorizations"

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
            acquisition_scope_id="abide_i_pcp_core_derivative_set",
            expected_size_bytes=None,
            size_scope_id=None,
            expected_size_source=(
                "FCP-INDI S3 object listing at acquisition; phenotypic file "
                "Phenotypic_V1_0b_preprocessed1.csv verified at 449443 bytes"
            ),
            verification_date=VERIFICATION_DATE,
            citation_ids=["ABIDE-I", "Preprocessed Connectomes Project ABIDE derivatives"],
            target_root=f"{DATA_ROOT}/abide_i_pcp",
            hash_algorithm="sha256",
            hash_manifest_location=f"{DATA_ROOT}/abide_i_pcp/{HASH_MANIFEST_BASENAME}",
            storage_available_bytes=None,
            storage_required_bytes=None,
            storage_margin_bytes=None,
            storage_evidence_reference=None,
            citation_verified=True,
            size_verified=False,
            storage_verified=False,
            hash_strategy_verified=True,
            independent_approval_verified=False,
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
            acquisition_scope_id="ds000030_pilot_5_subjects",
            # Pilot size is the exact sum of provider-reported file sizes for the
            # five-subject metadata plan (scope ds000030_pilot_5_subjects). The
            # full snapshot (85,127,263,296 bytes) is informational only and does
            # not authorize this subset.
            expected_size_bytes=DS000030_PILOT_EXPECTED_BYTES,
            size_scope_id="ds000030_pilot_5_subjects",
            size_evidence_reference=DS000030_PILOT_PLAN_REFERENCE,
            expected_size_source=(
                "Exact sum of OpenNeuro provider-reported file sizes for the "
                f"{DS000030_PILOT_SUBJECT_COUNT}-subject pilot plan (scope "
                "ds000030_pilot_5_subjects). The full-snapshot total of 85,127,263,296 "
                "bytes is informational only and is not acquired; the planned controlled "
                f"RQ5 subset is ~{DS000030_PLANNED_RQ5_SUBJECT_COUNT} subjects, reached only "
                "after pilot gates pass."
            ),
            verification_date=VERIFICATION_DATE,
            citation_ids=["OpenNeuro ds000030"],
            target_root=f"{DATA_ROOT}/ds000030",
            hash_algorithm="sha256",
            hash_manifest_location=f"{DATA_ROOT}/ds000030/{HASH_MANIFEST_BASENAME}",
            storage_available_bytes=DS000030_STORAGE_AVAILABLE_BYTES,
            storage_required_bytes=DS000030_PILOT_EXPECTED_BYTES,
            storage_margin_bytes=CONTROLLED_RESERVE_BYTES,
            storage_evidence_reference=DS000030_STORAGE_REFERENCE,
            storage_scope_id="ds000030_pilot_5_subjects",
            citation_verified=True,
            size_verified=True,
            storage_verified=True,
            hash_strategy_verified=True,
            independent_approval_verified=False,
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
            acquisition_scope_id="cobre_niak_lightweight_release_v1",
            expected_size_bytes=657308547,
            size_scope_id="cobre_niak_lightweight_release_v1",
            size_evidence_reference="cobre-niak-figshare-article-sha256:4197885-v1",
            expected_size_source="figshare API article 4197885 (297 files, total bytes)",
            verification_date=VERIFICATION_DATE,
            citation_ids=["COBRE", "NIAK COBRE derivative release"],
            target_root=f"{DATA_ROOT}/cobre_niak",
            hash_algorithm="sha256",
            hash_manifest_location=f"{DATA_ROOT}/cobre_niak/{HASH_MANIFEST_BASENAME}",
            storage_available_bytes=None,
            storage_required_bytes=None,
            storage_margin_bytes=None,
            storage_evidence_reference=None,
            citation_verified=True,
            size_verified=True,
            storage_verified=False,
            hash_strategy_verified=True,
            independent_approval_verified=False,
            required_manual_action=(
                "Obtain written clarification from the derivative publisher on the "
                "figshare CC BY 4.0 vs upstream COBRE CC BY-NC layered-license conflict."
            ),
            acquisition_permitted=False,
        ),
    ]


_SELECTED_ID_RE = re.compile(r"\bsub-\d{5}\b")
# A signed/pre-authenticated provider URL (S3 query-string credentials).
_SIGNED_URL_RE = re.compile(
    r"\?(?:[^ \n]*&)?(?:versionId|X-Amz-Signature|X-Amz-Credential|Signature|AWSAccessKeyId)="
)
# A real, non-portable rendering of the external data root (an absolute /home or
# /mnt path that reaches neuromultiverse-data). The portable "$HOME/..." form and
# unrelated /mnt/c split-stack discussion are intentionally not matched.
_EXTERNAL_ABS_PATH_RE = re.compile(r"(?:/home/|/mnt/)[^\s`]*neuromultiverse-data")


def _valid_size_reference(dataset_id: str, reference: str) -> bool:
    """An opaque, non-secret evidence reference: no path, no whitespace, no home."""
    if "/" in reference or any(ch.isspace() for ch in reference):
        return False
    if _HOME_RE.search(reference) or _EXTERNAL_ABS_PATH_RE.search(reference):
        return False
    return ":" in reference


def _tracked_text_files() -> list[Path]:
    """Disclosure surfaces to scan for leaked identifiers/absolute paths.

    Only documentation and data manifests are scanned: source and test files
    legitimately contain path-guard regexes and rejection fixtures (e.g. a
    ``/home/...`` string used to prove such a path is *refused*), which are not
    leaks. A real leak would land in the governance docs or a manifest.
    """
    globs = ("docs/*.md", "data/**/*.tsv", "data/**/*.md")
    found: list[Path] = []
    for pattern in globs:
        found.extend(REPO_ROOT.glob(pattern))
    return [p for p in found if p.is_file()]


def _check_no_selected_identifiers() -> list[str]:
    """No pilot subject identifier, external absolute path, or signed URL committed."""
    problems: list[str] = []
    for path in _tracked_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _SELECTED_ID_RE.search(text):
            problems.append(f"{rel}: a ds000030 subject identifier appears in a tracked file")
        if _EXTERNAL_ABS_PATH_RE.search(text):
            problems.append(f"{rel}: an external absolute path appears in a tracked file")
        if _SIGNED_URL_RE.search(text):
            problems.append(f"{rel}: a signed provider URL appears in a tracked file")
    return problems


def _check_executor_hardening() -> list[str]:
    """The executor and pilot schema must keep the acquisition gate strong."""
    problems: list[str] = []
    executor = EXECUTOR.read_text(encoding="utf-8")
    model = PILOT_MODEL.read_text(encoding="utf-8")

    if 'add_argument("--approved"' in executor:
        problems.append("executor still defines a --approved boolean bypass")
    if "--approval-record" not in executor:
        problems.append("executor does not require an external approval record")
    if "completion_status" not in executor or "sha256_file" not in executor:
        problems.append("executor lacks integrity-aware (SHA-256) completion")
    if "return target.exists() and target.stat().st_size == expected_size" in executor:
        problems.append("executor still uses size-only completion")
    # The checksum manifest lives under the external target root, not in Git.
    if "checksums.sha256" not in executor:
        problems.append("executor does not reference an external checksum manifest")

    if 'extra="forbid"' not in model:
        problems.append("pilot schema is not strict (extra must be forbidden)")
    if re.search(r"(?i)\b(download_url|signed_url)\b|\burl\b\s*[:=]\s*str", model):
        problems.append("pilot plan schema appears to accept a download-URL field")

    templates = list(APPROVAL_DIR.glob("*.template.json"))
    if not templates:
        problems.append("acquisition approval template is missing")
    for tpl in templates:
        data = json.loads(tpl.read_text(encoding="utf-8"))
        if data.get("decision") != "not_approved":
            problems.append(f"{tpl.name}: approval template must be decision=not_approved")
    for record in APPROVAL_DIR.glob("*.json"):
        if record.name.endswith(".template.json"):
            continue
        data = json.loads(record.read_text(encoding="utf-8"))
        if data.get("decision") == "approved":
            problems.append(f"{record.name}: a committed approval record must not authorize")
    return problems


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

        # READY means access mechanics and authorization are verified. It does
        # NOT imply size or storage are verified: those are separate prerequisites
        # gated only at acquisition_permitted. A READY dataset may legitimately
        # have a pending pilot size.
        if record.access_status is AccessStatus.READY:
            if record.license_id == "":
                problems.append(f"{rid}: READY dataset lacks a license")
            if record.license_status is not LicenseStatus.VERIFIED:
                problems.append(f"{rid}: READY dataset must have a VERIFIED license status")
            if not record.citation_ids:
                problems.append(f"{rid}: READY dataset lacks a citation")
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

        # Explicit prerequisite consistency. The typed model already enforces
        # these at construction; the redundant checks here keep the failure
        # legible if a future record is built by another path.
        if record.citation_verified and any(c not in verified_topics for c in record.citation_ids):
            problems.append(f"{rid}: citation_verified=true but a citation id is not Verified")
        if record.size_verified and record.expected_size_bytes is None:
            problems.append(f"{rid}: size_verified=true but expected_size_bytes is absent")
        if record.size_verified and record.size_scope_id != record.acquisition_scope_id:
            problems.append(f"{rid}: size_verified evidence is for a different acquisition scope")
        if record.hash_strategy_verified:
            location = record.hash_manifest_location
            expected_ext = f".{record.hash_algorithm}"
            if not location or not location.endswith(expected_ext):
                problems.append(
                    f"{rid}: hash_strategy_verified=true but manifest location is missing or "
                    f"does not end with {expected_ext}"
                )
        # ABIDE-specific: the published usage agreement has no explicit provider
        # re-identification clause, so this provider fact must stay False.
        if rid == "abide_i_pcp" and record.provider_reidentification_restricted:
            problems.append(
                f"{rid}: provider_reidentification_restricted=true without a verified explicit "
                "provider re-identification clause"
            )
        # Evidence references, when present, must use the approved opaque formats.
        if record.size_evidence_reference and not _valid_size_reference(
            rid, record.size_evidence_reference
        ):
            problems.append(f"{rid}: size_evidence_reference uses an unapproved format")
        if record.storage_evidence_reference and not record.storage_evidence_reference.startswith(
            "storage-readiness-sha256:"
        ):
            problems.append(f"{rid}: storage_evidence_reference uses an unapproved format")
        # ds000030 pilot must be scope-bound to the five-subject plan, not the
        # full snapshot. Evidence-based, replacing the old blanket rejection.
        if rid == "ds000030" and record.size_verified:
            if record.acquisition_scope_id != "ds000030_pilot_5_subjects":
                problems.append("ds000030: verified size must be scoped to the five-subject pilot")
            if record.expected_size_bytes != DS000030_PILOT_EXPECTED_BYTES:
                problems.append("ds000030: expected_size_bytes does not match the recorded plan")
            if record.size_evidence_reference != DS000030_PILOT_PLAN_REFERENCE:
                problems.append(
                    "ds000030: size_evidence_reference does not match the approved plan"
                )
        # Independent approval must remain unverified in this preflight.
        if record.independent_approval_verified:
            problems.append(f"{rid}: independent_approval_verified must be false in this preflight")

    problems.extend(_check_no_selected_identifiers())
    problems.extend(_check_executor_hardening())
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


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return " ".join(text.split())


def _check_manual_actions(records: list[DatasetAccessRecord]) -> list[str]:
    """Exact per-record cross-check of manual actions against the register.

    The decision is driven by the typed ``required_manual_action`` field. For a
    blocked dataset, that exact text (whitespace-normalized) must appear in the
    dataset's own register section, which must also state the exact access-status
    value. A READY dataset must carry no manual action and its section must not
    present a "Required manual authorization" field. No fuzzy or document-wide
    matching is used.
    """
    problems: list[str] = []
    sections = _register_sections()
    for record in records:
        rid = record.dataset_id
        body = _section_for(rid, sections)
        if body is None:
            problems.append(f"{rid}: no acquisition-register section found")
            continue
        normalized_body = normalize_whitespace(body)
        if record.access_status in _BLOCKING_STATES:
            if record.required_manual_action is None:
                problems.append(f"{rid}: blocking status carries no required_manual_action")
                continue
            if record.access_status.value not in body:
                problems.append(
                    f"{rid}: register section omits the exact access status "
                    f"{record.access_status.value}"
                )
            if normalize_whitespace(record.required_manual_action) not in normalized_body:
                problems.append(
                    f"{rid}: the exact required_manual_action text is absent from its "
                    "register section"
                )
        else:
            if record.required_manual_action is not None:
                problems.append(f"{rid}: READY dataset must not carry a required_manual_action")
            if "required manual authorization:" in body.lower():
                problems.append(
                    f"{rid}: READY dataset section must not present a required authorization field"
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
                "acquisition_scope_id": r.acquisition_scope_id,
                "size_scope_id": r.size_scope_id,
                "expected_size_bytes": r.expected_size_bytes,
                "hash_manifest_location": r.hash_manifest_location,
                "storage_evidence_complete": all(
                    v is not None
                    for v in (
                        r.storage_available_bytes,
                        r.storage_required_bytes,
                        r.storage_margin_bytes,
                        r.storage_evidence_reference,
                    )
                ),
                "size_evidence_reference": r.size_evidence_reference,
                "storage_scope_id": r.storage_scope_id,
                "storage_evidence_reference": r.storage_evidence_reference,
                "prerequisites": {
                    "citation_verified": r.citation_verified,
                    "size_verified": r.size_verified,
                    "storage_verified": r.storage_verified,
                    "hash_strategy_verified": r.hash_strategy_verified,
                    "independent_approval_verified": r.independent_approval_verified,
                },
                "required_manual_action_present": r.required_manual_action is not None,
                "acquisition_permitted": r.acquisition_permitted,
            }
            for r in records
        ],
        "pilot_subject_count": DS000030_PILOT_SUBJECT_COUNT,
        "planned_rq5_subject_count": DS000030_PLANNED_RQ5_SUBJECT_COUNT,
        "ds000030_pilot_file_count": DS000030_PILOT_FILE_COUNT,
        "ds000030_pilot_expected_bytes": DS000030_PILOT_EXPECTED_BYTES,
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
