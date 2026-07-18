# Data Usage and Governance

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

This document governs which datasets the NeuroMultiverse study may use, under what terms, and what must be true before any byte is downloaded.

**Current acquisition state: no dataset has been downloaded. No participant table, imaging file, ROI time series, derivative, or archive has been retrieved.** Governance for the three required datasets was verified from authoritative sources on 2026-07-17 using metadata-only probes (provider metadata APIs, object-store list operations, and HEAD requests that transfer no participant data). The exact phrase "Authoritative verification required before acquisition." still marks any field not yet filled from an authoritative source; it is not a drafting marker and must not be replaced by an assumption. Verification of governance is not authorization to acquire: acquisition is gated on the completed checklist in Section 2 and on independent approval of this governance record.

---

## 1. Dataset governance table

| Field | ABIDE-I PCP | OpenNeuro ds000030 | COBRE NIAK derivative | COBRE raw | AOMIC-ID1000 |
| --- | --- | --- | --- | --- | --- |
| Scientific role | Main large-N multiverse and primary model comparison (RQ1-RQ4) | Controlled raw-pipeline comparison (RQ5); optional mid-scale clinical bridge | Independent schizophrenia replication (Estimand 4) | Optional extension only | Optional healthy-population sensitivity analysis |
| Required or optional | Required | Required for RQ5 | Required | Optional | Optional |
| Authoritative source | INDI ABIDE-I page (fcon_1000.projects.nitrc.org/indi/abide/abide_I.html) and PCP ABIDE; derivatives on the FCP-INDI public S3 bucket. Verified 2026-07-17. | OpenNeuro dataset ds000030, snapshot 1.0.0 metadata (openneuro.org). Verified 2026-07-17. | figshare article 4197885, NIAK 0.17 lightweight release (api.figshare.com). Verified 2026-07-17. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Verified license / data-use status | Provider terms: Creative Commons Attribution-NonCommercial-Share Alike (CC BY-NC-SA 3.0); non-commercial, share-alike, attribution; NITRC/FCP registration; the provider states the data are anonymized and contain no protected health information. The published usage-agreement page does not state an explicit provider re-identification clause; the prohibition on re-identification is a NeuroMultiverse project standing rule, not a provider term. Verified 2026-07-17. | CC0 public-domain dedication, read from the snapshot 1.0.0 metadata. Verified 2026-07-17. | **License CONFLICT (unresolved).** figshare metadata displays CC BY 4.0, but the same figshare description states the upstream COBRE data were "originally released under Creative Commons -- Attribution Non-Commercial." Repository license CC BY 4.0; upstream license CC BY-NC; effective project restriction: non-commercial, no redistribution. Verified as conflicting 2026-07-17. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Access procedure | Register with NITRC and the 1000 Functional Connectomes Project / INDI and be logged in; PCP ROI time series and phenotypic file are read from the FCP-INDI S3 bucket. Verified 2026-07-17. | Public download of the pinned snapshot 1.0.0; no authentication required. Verified 2026-07-17. | Public download from figshare; no authentication required. Verified 2026-07-17. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Registration or approval requirement | NITRC + 1000 FCP/INDI registration required; no separate per-project approval. Verified 2026-07-17. | None. Verified 2026-07-17. | None for the NIAK derivative. Verified 2026-07-17. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Permitted local use | Governed by the verified license; local secondary research analysis only, pending verification | Governed by the verified license; local secondary research analysis only, pending verification | Governed by the verified data-use terms; local secondary research analysis only, pending verification | Governed by the verified data-use terms; not acquired without separate approval | Governed by the verified license; local secondary research analysis only, pending verification |
| Public redistribution status | Not redistributed by this project unless the verified license explicitly permits it | Not redistributed by this project unless the verified license explicitly permits it | Not redistributed by this project unless the verified terms explicitly permit it | Not redistributed by this project | Not redistributed by this project unless the verified license explicitly permits it |
| Expected data type | Participant phenotype tables and preprocessed region-of-interest time series | BIDS-organized raw T1-weighted and resting-state BOLD imaging with sidecar metadata | Derivative connectivity or region-of-interest time series with a phenotype table | Raw imaging with metadata | Raw or derivative imaging with participant metadata |
| Planned external storage location | Local directory outside the Git working tree, recorded in the acquisition log at download time | Local directory outside the Git working tree, recorded in the acquisition log at download time | Local directory outside the Git working tree, recorded in the acquisition log at download time | Not applicable until approved | Local directory outside the Git working tree, recorded in the acquisition log at download time |
| Integrity method | Content hash per file at download; manifest stored outside the repository; re-verified before each analysis run | Content hash per file at download; manifest stored outside the repository; re-verified before preprocessing | Content hash per file at download; manifest stored outside the repository | Not applicable until approved | Content hash per file at download; manifest stored outside the repository |
| Version identifier | ABIDE-I PCP, phenotypic Phenotypic_V1_0b_preprocessed1; pipelines ccs/cpac/dparsf/niak; atlases include rois_aal and rois_cc200. Verified 2026-07-17. | Snapshot 1.0.0, DOI 10.18112/openneuro.ds000030.v1.0.0, BIDS 1.0.2. Verified 2026-07-17. | NIAK 0.17 lightweight release, DOI 10.6084/m9.figshare.4197885.v1. Verified 2026-07-17. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Citation | Di Martino et al. 2014 (ABIDE-I) and Craddock et al. 2013 (PCP Neuro Bureau) — both Verified in [citation_inventory.md](citation_inventory.md). | OpenNeuro ds000030 snapshot 1.0.0 and Poldrack et al. 2016 acknowledgment — Verified in [citation_inventory.md](citation_inventory.md). | Bellec 2016 (figshare NIAK derivative) and Aine et al. 2017 (COBRE) — Verified in [citation_inventory.md](citation_inventory.md). | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). |
| Ethical / privacy notes | Secondary research data; multi-site composition and diagnostic ascertainment vary by site and may bias results; site confounds diagnosis and is handled by grouped validation and a site-only baseline; no re-identification attempt permitted | Secondary research data; limited-site acquisition limits generalization, and the number of contributing imaging sites must be read from the authoritative source rather than assumed; raw imaging is identifiable-adjacent and must never leave the local machine or enter version control; no re-identification attempt permitted | Secondary research data under its own data-use terms; diagnostic labels are research labels; local usable counts may differ from published counts and any mismatch is documented | Secondary research data; acquisition requires separate access, cost, and scientific review | Secondary research data; healthy population only; no diagnostic contrast |
| Expected acquisition size | Computed from the FCP-INDI S3 object listing at acquisition; phenotypic file Phenotypic_V1_0b_preprocessed1.csv verified at 449,443 bytes. | Full snapshot 85,127,263,296 bytes (provider-reported, OpenNeuro GraphQL). The whole snapshot is not acquired: the next unit is a bounded 5-subject pilot whose size is computed from per-file snapshot metadata for the selected subjects before download. The planned controlled RQ5 subset is approximately 20 subjects, reached only after pilot gates pass. | 657,308,547 bytes across 297 files (figshare API article 4197885). | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Verification date | 2026-07-17 | 2026-07-17 | 2026-07-17 | Not verified | Not verified |
| Verification status | Source, license, and citation verified; access authorization pending manual user registration (NITRC + INDI) — MANUAL AUTHORIZATION REQUIRED | Source, license, and citation verified; access READY | Source and citation verified; license CONFLICT (figshare CC BY 4.0 vs upstream CC BY-NC); access SOURCE_AMBIGUOUS — not READY | Unverified (optional, not acquired) | Unverified (optional, not acquired) |

Dataset purchase budget: **$0**. Any dataset requiring payment is out of scope for this study.

---

## 2. Acquisition checklist

Every item below must be completed and recorded **before** any download of a given dataset begins. A dataset with an incomplete checklist must not be acquired.

- [ ] **License verification.** The governing license or data-use agreement has been read from the authoritative source, its identifier recorded, and the verification date recorded in the table above.
- [ ] **Citation verification.** The required citation has been read from the authoritative source and recorded in [citation_inventory.md](citation_inventory.md) with its verification date and stable identifier.
- [ ] **Access authorization.** Any registration, application, or approval required by the data provider has been completed, and the authorization evidence has been recorded outside the repository.
- [ ] **Storage capacity confirmation.** Free space on the target volume has been measured and recorded, and exceeds the reviewed expected size with margin.
- [ ] **Expected-size review.** The download size has been read from the authoritative source rather than estimated, and recorded.
- [ ] **Checksum or content-hash strategy.** The hash algorithm, manifest location outside the repository, and re-verification point in the workflow have been fixed.
- [ ] **Local path confirmation.** The target directory is outside the Git working tree and its absolute path has been recorded in the acquisition log.
- [ ] **`.gitignore` confirmation.** The repository ignore rules have been confirmed to exclude the data directories, derivative formats, and cache locations that the acquisition will produce.
- [ ] **Data-use restriction acknowledgment.** The restrictions on redistribution, publication, and re-identification imposed by the verified license have been read and recorded, and the analysis plan has been confirmed to comply with them.

---

## 3. Per-dataset checklist status

Governance verification is tracked separately from acquisition readiness. A dataset is not "ready for acquisition" until every prerequisite is met **and** the acquisition gate is independently approved. As of 2026-07-17:

| Checklist item | ABIDE-I PCP | OpenNeuro ds000030 | COBRE NIAK derivative |
| --- | --- | --- | --- |
| Source verified | Yes | Yes | Yes |
| License verified | Yes (CC BY-NC-SA 3.0) | Yes (CC0) | **No — CONFLICT** (figshare CC BY 4.0 vs upstream CC BY-NC) |
| Citation verified | Yes | Yes | Yes |
| Access authorization verified | No — manual NITRC + INDI registration required | Yes (public, no auth) | Access mechanics public, but license status ambiguous → not verified |
| Storage verified | Pending (target root not yet provisioned) | Yes for scope `ds000030_pilot_5_subjects` (external root provisioned; available 996,303,314,944 bytes clears transfer + 250 GiB reserve; measured 2026-07-18) | Pending (target root not yet provisioned) |
| Size verified | Pending (scope `abide_i_pcp_core_derivative_set`; computed from S3 listing at acquisition) | Yes for scope `ds000030_pilot_5_subjects` (22 files, 187,570,603 bytes from OpenNeuro metadata; full 85 GB snapshot is informational only) | Yes for scope `cobre_niak_lightweight_release_v1` (657,308,547 bytes, figshare API) |
| Hash strategy verified | Yes (SHA-256, external `$HOME/…/abide_i_pcp/checksums.sha256`) | Yes (SHA-256, external `$HOME/…/ds000030/checksums.sha256`) | Yes (SHA-256, external `$HOME/…/cobre_niak/checksums.sha256`) |
| Ready for acquisition | No | **Completed — bounded five-subject pilot only** | No — license conflict must be resolved first |

Only the bounded ds000030 five-subject pilot has completed acquisition. The full per-dataset record is in [acquisition_register.md](acquisition_register.md).

**ds000030 scope.** The bounded five-subject pilot completed on 2026-07-18 under approval `nm-ds000030-pilot-20260718-chatgpt-audit-001`: exactly 22 approved files and 187,570,603 bytes. The external manifest contains 22 verified SHA-256 entries; independent recomputation matched every file. There were zero partials, quarantined files, or integrity failures, and one successful completed run. No participant table, phenotype, behavioral, events, or confound file was acquired, and no downloaded content was inspected. Evidence: `ds000030-pilot-acquisition-sha256:e2b194394687738f62b199539cdc7acca6627b40fcd6a4fbb45143891b7410ea`.

The approval covered only this completed transfer. This evidence commit invalidates its exact-HEAD binding for future execution; any resume or additional acquisition requires a new approval. ABIDE, COBRE, and the approximately 20-subject expansion remain unauthorized.

Raw structural validation is currently blocked: all 22 acquired files are mode 644, while the read-only validator requires private raw-file permissions. Hashes, sizes, and acquisition evidence still match. A preliminary pinned BIDS Validator 3.0.0 run (schema 1.2.4) reported zero errors and 139 recommendation-only warnings, but the project does not mark raw validation complete until the permission defect is resolved through an approved, auditable correction. No raw file was modified, no voxel array was loaded, and preprocessing has not begun.

## 4. Standing prohibitions

- No raw imaging data, derivative imaging, model weight, feature cache, or restricted file may be committed to this repository.
- No attempt to re-identify any participant is permitted.
- No dataset characteristic may be presented as authoritatively verified unless it was read from an authoritative source and its verification date was recorded. Expected characteristics and planning assumptions may appear only when explicitly labeled as unverified or pending authoritative verification, and they must not authorize acquisition.
- No acquisition may proceed on the basis of an unverified planning assumption. Acquisition requires the completed checklist in Section 2, including license verification, access review, citation verification, and expected-size review read from the authoritative source.
- No dataset may be acquired to rescue an unfavorable result after outcome inspection; such an acquisition requires a recorded deviation disclosing that outcomes had been viewed.
- Only aggregate, disclosure-safe outputs may appear in any public report or artifact.
