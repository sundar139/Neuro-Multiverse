# Data Usage and Governance

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

This document governs which datasets the NeuroMultiverse study may use, under what terms, and what must be true before any byte is downloaded.

**Current acquisition state: no dataset has been downloaded, accessed, or requested.** Every access, license, size, version, and citation field below is unverified. The exact phrase "Authoritative verification required before acquisition." marks a field that must be filled from an authoritative source, with a verification date, before the corresponding dataset is acquired. It is not a drafting marker and must not be replaced by an assumption.

---

## 1. Dataset governance table

| Field | ABIDE-I PCP | OpenNeuro ds000030 | COBRE NIAK derivative | COBRE raw | AOMIC-ID1000 |
| --- | --- | --- | --- | --- | --- |
| Scientific role | Main large-N multiverse and primary model comparison (RQ1-RQ4) | Controlled raw-pipeline comparison (RQ5); optional mid-scale clinical bridge | Independent schizophrenia replication (Estimand 4) | Optional extension only | Optional healthy-population sensitivity analysis |
| Required or optional | Required | Required for RQ5 | Required | Optional | Optional |
| Authoritative source | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Verified license / data-use status | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Access procedure | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Registration or approval requirement | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Permitted local use | Governed by the verified license; local secondary research analysis only, pending verification | Governed by the verified license; local secondary research analysis only, pending verification | Governed by the verified data-use terms; local secondary research analysis only, pending verification | Governed by the verified data-use terms; not acquired without separate approval | Governed by the verified license; local secondary research analysis only, pending verification |
| Public redistribution status | Not redistributed by this project unless the verified license explicitly permits it | Not redistributed by this project unless the verified license explicitly permits it | Not redistributed by this project unless the verified terms explicitly permit it | Not redistributed by this project | Not redistributed by this project unless the verified license explicitly permits it |
| Expected data type | Participant phenotype tables and preprocessed region-of-interest time series | BIDS-organized raw T1-weighted and resting-state BOLD imaging with sidecar metadata | Derivative connectivity or region-of-interest time series with a phenotype table | Raw imaging with metadata | Raw or derivative imaging with participant metadata |
| Planned external storage location | Local directory outside the Git working tree, recorded in the acquisition log at download time | Local directory outside the Git working tree, recorded in the acquisition log at download time | Local directory outside the Git working tree, recorded in the acquisition log at download time | Not applicable until approved | Local directory outside the Git working tree, recorded in the acquisition log at download time |
| Integrity method | Content hash per file at download; manifest stored outside the repository; re-verified before each analysis run | Content hash per file at download; manifest stored outside the repository; re-verified before preprocessing | Content hash per file at download; manifest stored outside the repository | Not applicable until approved | Content hash per file at download; manifest stored outside the repository |
| Version identifier | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. |
| Citation | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). | Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md). |
| Ethical / privacy notes | Secondary research data; multi-site composition and diagnostic ascertainment vary by site and may bias results; site confounds diagnosis and is handled by grouped validation and a site-only baseline; no re-identification attempt permitted | Secondary research data; limited-site acquisition limits generalization, and the number of contributing imaging sites must be read from the authoritative source rather than assumed; raw imaging is identifiable-adjacent and must never leave the local machine or enter version control; no re-identification attempt permitted | Secondary research data under its own data-use terms; diagnostic labels are research labels; local usable counts may differ from published counts and any mismatch is documented | Secondary research data; acquisition requires separate access, cost, and scientific review | Secondary research data; healthy population only; no diagnostic contrast |
| Verification date | Not verified | Not verified | Not verified | Not verified | Not verified |
| Verification status | Unverified | Unverified | Unverified | Unverified | Unverified |

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

## 3. Standing prohibitions

- No raw imaging data, derivative imaging, model weight, feature cache, or restricted file may be committed to this repository.
- No attempt to re-identify any participant is permitted.
- No dataset characteristic may be presented as authoritatively verified unless it was read from an authoritative source and its verification date was recorded. Expected characteristics and planning assumptions may appear only when explicitly labeled as unverified or pending authoritative verification, and they must not authorize acquisition.
- No acquisition may proceed on the basis of an unverified planning assumption. Acquisition requires the completed checklist in Section 2, including license verification, access review, citation verification, and expected-size review read from the authoritative source.
- No dataset may be acquired to rescue an unfavorable result after outcome inspection; such an acquisition requires a recorded deviation disclosing that outcomes had been viewed.
- Only aggregate, disclosure-safe outputs may appear in any public report or artifact.
