# Acquisition Register

Version: 1.0
Document date: 2026-07-17
Governing documents: [data_usage.md](data_usage.md), [preregistration.md](preregistration.md), [citation_inventory.md](citation_inventory.md)

This is a governance record, not a data manifest. It records what each required dataset is, under what terms it may be acquired, what remains to be authorized, and whether acquisition is permitted. It contains no participant data and no acquired file.

All governance below was verified on 2026-07-17 using metadata-only probes: provider metadata APIs, object-store list operations, DOI resolution, and HEAD requests that transfer no participant data. No dataset has been downloaded.

The external data root is portable and is expressed as `$HOME/neuromultiverse-data` inside WSL2, per [setup_windows.md](setup_windows.md). No literal home path or username is recorded. Hash manifests live outside the repository, next to the data, and are never committed until the files they describe have actually been acquired.

---

## ABIDE-I Preprocessed Connectomes Project derivatives

- **Dataset identifier:** `abide_i_pcp`
- **Scientific role:** Main large-N multiverse and primary model comparison (RQ1-RQ4).
- **Selected version:** ABIDE-I PCP derivatives; phenotypic table `Phenotypic_V1_0b_preprocessed1`. Pipelines `ccs`, `cpac`, `dparsf`, `niak`; strategies `filt_global`, `filt_noglobal`, `nofilt_global`, `nofilt_noglobal`; ROI atlases include `rois_aal` and `rois_cc200`.
- **Authoritative sources:** INDI ABIDE-I data-usage page (`fcon_1000.projects.nitrc.org/indi/abide/abide_I.html`); PCP ABIDE (`preprocessed-connectomes-project.github.io/abide/`); FCP-INDI public S3 bucket (`s3://fcp-indi/data/Projects/ABIDE_Initiative/Outputs/`).
- **Provider terms:** Creative Commons Attribution-NonCommercial-Share Alike (CC BY-NC-SA 3.0). The provider states the data are anonymized (HIPAA-oriented procedures) and contain no protected health information, requires non-commercial use, attribution and share-alike on redistribution, and NITRC + 1000 FCP/INDI registration. The published usage-agreement page does not state an explicit contractual re-identification prohibition; anonymization is not equivalent to such a clause, so no provider re-identification clause is asserted here.
- **Project standing prohibition:** Independently of provider terms, the NeuroMultiverse protocol prohibits any re-identification attempt, forbids public redistribution of participant-level data, keeps no participant-level file in Git, and permits only secondary research and disclosure-safe aggregate outputs.
- **Citation obligations:** ABIDE-I — Di Martino et al. 2014 (DOI 10.1038/mp.2013.78). PCP derivatives — Craddock et al. 2013, The Neuro Bureau Preprocessing Initiative (DOI 10.3389/conf.fninf.2013.09.00041). Both are recorded and Verified in the citation inventory and must both be cited.
- **Acquisition scope:** `abide_i_pcp_core_derivative_set` (the exact file set the next acquisition would retrieve).
- **Access status:** MANUAL_AUTHORIZATION_REQUIRED. The derivative objects are readable from the public FCP-INDI S3 bucket, but the governing ABIDE-I terms still require registration and acceptance; public object-store reachability does not remove them.
- **Prerequisites:** citation verified; hash strategy verified (SHA-256, external manifest below); size verification **pending** (no scope-matched total yet; computed from the S3 listing at acquisition); storage verification **pending**.
- **Required manual authorization:** Register a NITRC account and join the 1000 Functional Connectomes Project / INDI resource, then be logged in at download time.
- **Planned acquisition subset:** Per-subject ROI time series for atlases `rois_aal` and `rois_cc200` across pipelines `ccs`, `cpac`, `dparsf`, `niak`, plus the phenotypic and quality-control table, for the common-subject cohort defined in the protocol. The cohort is not frozen in this record.
- **Expected size:** Computed from the FCP-INDI S3 object listing at acquisition time (per-object sizes are provider-reported; sample `rois_cc200` files measured ~0.47 MB each). The phenotypic file `Phenotypic_V1_0b_preprocessed1.csv` was HEAD-probed at 449,443 bytes.
- **External target root:** `$HOME/neuromultiverse-data/abide_i_pcp`
- **Hash algorithm:** SHA-256
- **External hash-manifest location:** `$HOME/neuromultiverse-data/abide_i_pcp/checksums.sha256` (created at acquisition, never committed)
- **Re-verification command:** `curl -s "https://s3.amazonaws.com/fcp-indi?list-type=2&prefix=data/Projects/ABIDE_Initiative/Outputs/&delimiter=/"` (object listing, metadata only)
- **Redistribution policy:** Not redistributed by this project; the provider's share-alike terms would apply if it ever were.
- **Re-identification:** Prohibited by the NeuroMultiverse project protocol. The provider's usage-agreement page states anonymization and no PHI but does not state an explicit re-identification clause.
- **Approval status:** Pending independent approval of this governance record.
- **Approval date:** Not approved.
- **Acquisition permitted:** No.
- **Reason:** Manual NITRC + INDI authorization is not yet completed, and the governance gate is not yet approved.

---

## OpenNeuro ds000030

- **Dataset identifier:** `ds000030`
- **Scientific role:** Controlled raw-pipeline comparison (RQ5); optional mid-scale clinical bridge.
- **Selected version:** Snapshot `1.0.0`, DOI `10.18112/openneuro.ds000030.v1.0.0`, BIDS version 1.0.2. The mutable draft is not used.
- **Authoritative sources:** OpenNeuro dataset page (`openneuro.org/datasets/ds000030/versions/1.0.0`); OpenNeuro GraphQL snapshot metadata (`openneuro.org/crn/graphql`).
- **License / data-use summary:** CC0 public-domain dedication, read from the snapshot metadata. No registration or agreement required.
- **Citation obligations:** OpenNeuro ds000030 snapshot 1.0.0 (dataset DOI above). The provider `HowToAcknowledge` additionally requires citing Poldrack et al. 2016, Scientific Data (DOI 10.1038/sdata.2016.110). Both are recorded and Verified in the citation inventory.
- **Acquisition scope:** `ds000030_pilot_5_subjects` — the next acquisition is the five-subject pilot, not the full snapshot.
- **Access status:** READY. Public download; no authentication required for the pinned snapshot.
- **Manual authorization:** None required (public CC0 snapshot); confirm the selected snapshot `1.0.0`.
- **Prerequisites:** citation verified; hash strategy verified (SHA-256, external manifest below); **pilot size verified** for scope `ds000030_pilot_5_subjects`; **storage verified** for the same scope. The full-snapshot total remains informational and did not authorize the pilot.
- **Storage preflight:** The external ds000030 root was provisioned and its free capacity measured on 2026-07-18 (no dataset body downloaded). Available capacity 996,303,314,944 bytes clears the planned transfer plus the 250 GiB (268,435,456,000-byte) controlled-processing reserve. Evidence: `storage-readiness-sha256:3d28205a55ed386c8b5f5ac1bbb123c8d5efc505e11ee55a612d52ce90fd6acd` (external, mode 600, never committed).
- **Five-subject pilot plan:** Generated from OpenNeuro metadata only. Exact planned file count **22**; exact planned transfer **187,570,603 bytes** (sum of provider-reported sizes for the five selected subjects: dataset metadata, T1w image + sidecar, resting-state BOLD image + sidecar). Selected subject identifiers are retained only in the external plan (mode 600) and never enter Git. The plan is validated by the strict `PilotAcquisitionPlan` schema and **contains no persisted download URL**; at execution time each URL is resolved from the official OpenNeuro metadata endpoint, HTTPS/host-validated, and never persisted. Plan evidence (schema v2, URL-free): `ds000030-pilot-plan-sha256:fb7f62583f00ade72dcba6f85a394c0413516bf949913f31ea68471c3cda0709`.
- **Acquisition result:** The authorized pilot completed on 2026-07-18: 22 files, 187,570,603 bytes, 22 valid manifest SHA-256 entries, zero partials, zero quarantined files, zero integrity failures, and one completed run. No participant, phenotype, behavioral, events, or confound file was acquired; downloaded contents were not inspected. Evidence: `ds000030-pilot-acquisition-sha256:e2b194394687738f62b199539cdc7acca6627b40fcd6a4fbb45143891b7410ea`.
- **Future execution gate:** The approval served only this completed transfer. This evidence commit changes exact `HEAD`, so future acquisition or resume requires a new approval. The approximately 20-subject expansion remains unauthorized.
- **Raw validation status:** Incomplete. The authorized permission correction completed: 22 raw files mode 600, 16 private dirs mode 700, hashes unchanged (evidence: `ds000030-pilot-permissions-sha256:aeb62b14a73926783543311e3953a1542f2dde5f57cb1b9a7e0216407157680e`). The first post-permission validation attempt failed because the committed validator's frozen `PRIVATE_PATH_RE` falsely matched `s:/` inside `https://` metadata URLs, misclassifying public URLs as local drive paths. The repository classifier has been corrected (public HTTP(S) URIs are recognized before local-path analysis; private Windows, UNC, POSIX-home, macOS-user, WSL-user, home-relative paths, file URIs, and credential/signed URIs remain rejected). No raw metadata was rewritten, no data was reacquired, no voxel array was loaded, and preprocessing has not begun. A fresh raw-validation run under the corrected committed validator remains pending separate authorization. ABIDE and COBRE remain blocked; expansion unauthorized.
- **Planned controlled RQ5 subset:** Approximately 20 subjects (T1-weighted and resting-state BOLD, with sidecar metadata), per the protocol. The resting-state BOLD modality is confirmed present (`task-rest_bold.json` in the snapshot). This subset is reached only after the pilot gates pass; it is separate from the pilot and is not selected or frozen.
- **Completed bounded acquisition pilot:** Exactly 5 subjects and the 22 reviewed files above. The whole 85 GB snapshot was not acquired.
- **Expected size:** Pilot transfer is 187,570,603 bytes (scope `ds000030_pilot_5_subjects`). The full snapshot total of 85,127,263,296 bytes (provider-reported via OpenNeuro GraphQL) is informational only and is not acquired.
- **External raw target:** `$HOME/neuromultiverse-data/ds000030/raw`
- **Hash algorithm:** SHA-256
- **External hash-manifest location:** `$HOME/neuromultiverse-data/ds000030/checksums.sha256` (created at acquisition, never committed)
- **Re-verification command:** `curl -s -X POST https://openneuro.org/crn/graphql -H "Content-Type: application/json" -d '{"query":"{ snapshot(datasetId:\"ds000030\", tag:\"1.0.0\"){ tag size description{ License DatasetDOI BIDSVersion } } }"}'`
- **Redistribution policy:** CC0 permits redistribution; this project still does not redistribute imaging.
- **Re-identification prohibition:** No re-identification attempt permitted; raw imaging never enters version control.
- **Approval status:** Independently approved for the bounded pilot only.
- **Approval date:** 2026-07-18.
- **Acquisition permitted:** The exact reviewed pilot completed; no further transfer is authorized by the served approval.
- **Approval reference:** `nm-ds000030-pilot-20260718-chatgpt-audit-001`.

---

## COBRE NIAK derivative

- **Dataset identifier:** `cobre_niak`
- **Scientific role:** Independent schizophrenia replication (Estimand 4).
- **Selected version:** COBRE preprocessed with NIAK 0.17 - lightweight release, DOI `10.6084/m9.figshare.4197885.v1`.
- **Authoritative sources:** figshare article 4197885 page and API (`api.figshare.com/v2/articles/4197885`); SIMEXP `cobre_preprocessed` project.
- **Repository-displayed license:** CC BY 4.0 (figshare article `license` field).
- **Upstream-data license:** Attribution-NonCommercial (CC BY-NC) — the figshare description itself states the data were "originally released under Creative Commons -- Attribution Non-Commercial" (upstream INDI COBRE).
- **License verification status:** **CONFLICT.** The repository license (CC BY 4.0) is more permissive than the stated upstream license (CC BY-NC). This is not resolved by selecting the less restrictive term.
- **Effective project restriction (conservative):** Non-commercial, no redistribution, attribution required, until the conflict is authoritatively reconciled.
- **Citation obligations:** NIAK derivative — Bellec 2016 (figshare DOI above). COBRE — Aine et al. 2017 (DOI 10.1007/s12021-017-9338-9). Both are recorded and Verified in the citation inventory.
- **Acquisition scope:** `cobre_niak_lightweight_release_v1` — the full lightweight release; size is verified for this same scope (657,308,547 bytes, figshare API). Storage verification remains pending.
- **Access mechanics:** Publicly reachable on figshare without authentication.
- **Access status:** **SOURCE_AMBIGUOUS** — public reachability does not make the governing license unambiguous.
- **Required manual authorization:** Obtain written clarification from the derivative publisher on the figshare CC BY 4.0 vs upstream COBRE CC BY-NC layered-license conflict. Until then, treat the release as non-commercial and non-redistributable.
- **Planned acquisition subset:** The full lightweight derivative (preprocessed resting-state fMRI in MNI space, per-subject confound/time-series tables, and the accompanying phenotype table). Local usable counts are determined at analysis time, not here.
- **Expected size:** 657,308,547 bytes across 297 files (figshare API article 4197885).
- **External target root:** `$HOME/neuromultiverse-data/cobre_niak`
- **Hash algorithm:** SHA-256
- **External hash-manifest location:** `$HOME/neuromultiverse-data/cobre_niak/checksums.sha256` (created at acquisition, never committed)
- **Re-verification command:** `curl -s https://api.figshare.com/v2/articles/4197885` (metadata only: license, version, description, per-file sizes and md5)
- **Redistribution policy:** Not redistributed by this project; conservatively treated as non-redistributable while the license conflict is unresolved.
- **Commercial use:** Not permitted under the conservative effective restriction.
- **Re-identification prohibition (project):** The NeuroMultiverse project prohibits any re-identification attempt, independent of provider terms.
- **Approval status:** Pending independent approval, and blocked by the unresolved license conflict.
- **Approval date:** Not approved.
- **Acquisition permitted:** No.
- **Reason:** The layered-license conflict is unresolved (SOURCE_AMBIGUOUS); acquisition cannot proceed until authoritative clarification is obtained.

---

## Optional datasets (not acquired)

- **COBRE raw (`cobre_raw`):** Optional extension only. Governing terms reviewed on the INDI COBRE page — Creative Commons Attribution-NonCommercial (CC BY-NC), NITRC + 1000 FCP/INDI registration with approval typically within one business day. Not required for core completion and **not acquired**; acquisition would require separate scientific, access, and compute review, and a recorded deviation or approved extension.
- **AOMIC-ID1000 (`aomic_id1000`):** Optional healthy-population sensitivity analysis. Not authoritatively verified in this record and **not acquired**. Omitting it entirely is a valid outcome.

Neither optional dataset is permitted for acquisition, and neither appears as a required governance record.

---

## Acquisition gate

The exact ds000030 five-subject pilot completed successfully. Scaling to approximately 20 subjects is not authorized. ABIDE-I PCP remains blocked on manual NITRC + INDI authorization. COBRE NIAK remains blocked by its unresolved layered-license conflict.
