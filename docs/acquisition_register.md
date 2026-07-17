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
- **License / data-use summary:** Creative Commons Attribution-NonCommercial-Share Alike (CC BY-NC-SA 3.0). Non-commercial research use only; share-alike on redistribution; anonymized per HIPAA; re-identification prohibited.
- **Citation obligations:** ABIDE-I — Di Martino et al. 2014 (DOI 10.1038/mp.2013.78). PCP derivatives — Craddock et al. 2013, The Neuro Bureau Preprocessing Initiative (DOI 10.3389/conf.fninf.2013.09.00041). Both are recorded and Verified in the citation inventory and must both be cited.
- **Access status:** MANUAL AUTHORIZATION REQUIRED. The derivative objects are readable from the public FCP-INDI S3 bucket, but the governing ABIDE-I terms still require registration and acceptance; public object-store reachability does not remove them.
- **Required manual authorization:** Create or sign into a NITRC account; join the 1000 Functional Connectomes Project / INDI resource; be logged in and in compliance with CC BY-NC-SA at download time.
- **Planned acquisition subset:** Per-subject ROI time series for atlases `rois_aal` and `rois_cc200` across pipelines `ccs`, `cpac`, `dparsf`, `niak`, plus the phenotypic and quality-control table, for the common-subject cohort defined in the protocol. The cohort is not frozen in this record.
- **Expected size:** Computed from the FCP-INDI S3 object listing at acquisition time (per-object sizes are provider-reported; sample `rois_cc200` files measured ~0.47 MB each). The phenotypic file `Phenotypic_V1_0b_preprocessed1.csv` was HEAD-probed at 449,443 bytes.
- **External target root:** `$HOME/neuromultiverse-data/abide_i_pcp`
- **Hash algorithm:** SHA-256
- **External hash-manifest location:** `$HOME/neuromultiverse-data/abide_i_pcp/checksums.sha256` (created at acquisition, never committed)
- **Re-verification command:** `curl -s "https://s3.amazonaws.com/fcp-indi?list-type=2&prefix=data/Projects/ABIDE_Initiative/Outputs/&delimiter=/"` (object listing, metadata only)
- **Redistribution policy:** Not redistributed by this project; share-alike terms apply if it ever were.
- **Re-identification prohibition:** No re-identification attempt permitted.
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
- **Access status:** READY. Public download; no authentication required for the pinned snapshot.
- **Required manual authorization:** None beyond confirming the selected snapshot `1.0.0`.
- **Planned acquisition subset:** The 20-subject controlled subset (T1-weighted and resting-state BOLD, with sidecar metadata), per the protocol. The resting-state BOLD modality is confirmed present (`task-rest_bold.json` in the snapshot); subject selection is not frozen in this record.
- **Expected size:** Full snapshot size is 85,127,263,296 bytes (provider-reported via OpenNeuro GraphQL). The pilot subset is a small fraction and is computed from per-file snapshot metadata at acquisition; the whole dataset is not downloaded.
- **External target root:** `$HOME/neuromultiverse-data/ds000030`
- **Hash algorithm:** SHA-256
- **External hash-manifest location:** `$HOME/neuromultiverse-data/ds000030/checksums.sha256` (created at acquisition, never committed)
- **Re-verification command:** `curl -s -X POST https://openneuro.org/crn/graphql -H "Content-Type: application/json" -d '{"query":"{ snapshot(datasetId:\"ds000030\", tag:\"1.0.0\"){ tag size description{ License DatasetDOI BIDSVersion } } }"}'`
- **Redistribution policy:** CC0 permits redistribution; this project still does not redistribute imaging.
- **Re-identification prohibition:** No re-identification attempt permitted; raw imaging never enters version control.
- **Approval status:** Pending independent approval of this governance record.
- **Approval date:** Not approved.
- **Acquisition permitted:** No.
- **Reason:** Access is READY, but the governance gate is not yet independently approved, and pilot acquisition is the next implementation unit.

---

## COBRE NIAK derivative

- **Dataset identifier:** `cobre_niak`
- **Scientific role:** Independent schizophrenia replication (Estimand 4).
- **Selected version:** COBRE preprocessed with NIAK 0.17 - lightweight release, DOI `10.6084/m9.figshare.4197885.v1`.
- **Authoritative sources:** figshare article 4197885 page and API (`api.figshare.com/v2/articles/4197885`); SIMEXP `cobre_preprocessed` project.
- **License / data-use summary:** CC BY 4.0, read from the figshare article metadata. Attribution required; no registration for the derivative. The underlying COBRE acknowledgment (NIH COBRE grant 1P20RR021938; Mind Research Network / University of New Mexico) is honored.
- **Citation obligations:** NIAK derivative — Bellec 2016 (figshare DOI above). COBRE — Aine et al. 2017 (DOI 10.1007/s12021-017-9338-9). Both are recorded and Verified in the citation inventory.
- **Access status:** READY. Public figshare download; no authentication required.
- **Required manual authorization:** None for the NIAK derivative.
- **Planned acquisition subset:** The full lightweight derivative (preprocessed resting-state fMRI in MNI space, per-subject confound/time-series tables, and the accompanying phenotype table). Local usable counts are determined at analysis time, not here.
- **Expected size:** 657,308,547 bytes across 297 files (figshare API article 4197885).
- **External target root:** `$HOME/neuromultiverse-data/cobre_niak`
- **Hash algorithm:** SHA-256
- **External hash-manifest location:** `$HOME/neuromultiverse-data/cobre_niak/checksums.sha256` (created at acquisition, never committed)
- **Re-verification command:** `curl -s https://api.figshare.com/v2/articles/4197885` (metadata only: license, version, per-file sizes and md5)
- **Redistribution policy:** Not redistributed by this project; CC BY 4.0 attribution applies if it ever were.
- **Re-identification prohibition:** No re-identification attempt permitted.
- **Approval status:** Pending independent approval of this governance record.
- **Approval date:** Not approved.
- **Acquisition permitted:** No.
- **Reason:** Access is READY, but the governance gate is not yet independently approved.

---

## Optional datasets (not acquired)

- **COBRE raw (`cobre_raw`):** Optional extension only. Governing terms reviewed on the INDI COBRE page — Creative Commons Attribution-NonCommercial (CC BY-NC), NITRC + 1000 FCP/INDI registration with approval typically within one business day. Not required for core completion and **not acquired**; acquisition would require separate scientific, access, and compute review, and a recorded deviation or approved extension.
- **AOMIC-ID1000 (`aomic_id1000`):** Optional healthy-population sensitivity analysis. Not authoritatively verified in this record and **not acquired**. Omitting it entirely is a valid outcome.

Neither optional dataset is permitted for acquisition, and neither appears as a required governance record.

---

## Acquisition gate

No dataset is permitted for acquisition. The three required datasets have verified governance; ABIDE-I PCP additionally requires manual NITRC + INDI authorization before it could proceed. Pilot acquisition is a separate implementation unit that runs only after this record is independently approved.
