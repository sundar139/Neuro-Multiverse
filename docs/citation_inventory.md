# Citation Inventory

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

This inventory enumerates every dataset, method, reporting framework, and major software component that will require citation in the NeuroMultiverse manuscript. It exists so that citation obligations are identified before use rather than reconstructed afterward.

**Only the rows explicitly marked `Verified` have been read from an authoritative source.** The five required-dataset rows in Section 1 (ABIDE-I, the PCP ABIDE derivatives, OpenNeuro ds000030, COBRE, and the NIAK COBRE derivative) were verified on 2026-07-17; every other row remains `Unverified`. Full citations and stable identifiers are recorded only after being read from an authoritative source, at which point the verification status and verification date are updated in the same row. Bibliographic details are never reconstructed from memory, and no citation is fabricated. Where a dataset citation is a condition of the data-use terms, verification is also an acquisition prerequisite under [data_usage.md](data_usage.md).

Verification status values: `Unverified` (identified as required, not yet read from source) or `Verified` (read from an authoritative source, with the date recorded).

---

## 1. Datasets

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| ABIDE-I | Di Martino A, Yan C-G, Li Q, et al. The autism brain imaging data exchange: towards a large-scale evaluation of the intrinsic brain architecture in autism. Molecular Psychiatry. 2014;19(6):659-667. | 10.1038/mp.2013.78 | Molecular Psychiatry, via Crossref metadata | Verified | 2026-07-17 | Main large-N multiverse cohort for RQ1-RQ4 |
| Preprocessed Connectomes Project ABIDE derivatives | Craddock C, Benhajali Y, Chu C, Chouinard F, Evans A, Jakab A, Khundrakpam BS, Lewis JD, Li Q, Milham M, Yan C, Bellec P. The Neuro Bureau Preprocessing Initiative: open sharing of preprocessed neuroimaging data and derivatives. Frontiers in Neuroinformatics. 2013; Conference Abstract: Neuroinformatics 2013. | 10.3389/conf.fninf.2013.09.00041 | Frontiers in Neuroinformatics; PCP ABIDE provider acknowledgment | Verified | 2026-07-17 | Source of the CCS, C-PAC, DPARSF, and NIAK derivative pipelines and their quality-control flags |
| OpenNeuro ds000030 | Poldrack R, Bilder R, Cannon T, London E, Freimer N, Congdon E, Karlsgodt K, Sabb F. UCLA Consortium for Neuropsychiatric Phenomics LA5c Study. OpenNeuro; 2020. Snapshot 1.0.0. Provider HowToAcknowledge additionally requires citing Poldrack RA, et al. A phenome-wide examination of neural and cognitive function. Scientific Data. 2016;3:160110. | 10.18112/openneuro.ds000030.v1.0.0 (dataset); 10.1038/sdata.2016.110 (acknowledgment publication) | OpenNeuro snapshot 1.0.0 metadata (DatasetDOI, License CC0); Scientific Data via Crossref | Verified | 2026-07-17 | Controlled raw inputs for the pipeline-agreement analysis (RQ5) |
| COBRE | Aine CJ, Bockholt HJ, Bustillo JR, et al. Multimodal Neuroimaging in Schizophrenia: Description and Dissemination. Neuroinformatics. 2017;15(4):343-364. Provider acknowledgment: NIH COBRE grant 1P20RR021938; Mind Research Network / University of New Mexico. | 10.1007/s12021-017-9338-9 | Neuroinformatics, via Crossref metadata; COBRE INDI page acknowledgment | Verified | 2026-07-17 | Independent schizophrenia replication cohort |
| NIAK COBRE derivative release | Bellec P. COBRE preprocessed with NIAK 0.17 - lightweight release. figshare; 2016. Dataset. | 10.6084/m9.figshare.4197885.v1 | figshare API article 4197885 (citation verified; license status CONFLICT — figshare CC BY 4.0 vs upstream CC BY-NC, see acquisition_register.md) | Verified | 2026-07-17 | Lightweight derivative used for the replication analysis |
| AOMIC-ID1000 | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Optional healthy-population sensitivity analysis |

## 2. Preprocessing software

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| fMRIPrep | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | One of three compared preprocessing pipelines in the agreement analysis; its boilerplate citation requirements must be honored |
| FSL | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | One of three compared preprocessing pipelines |
| AFNI | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | One of three compared preprocessing pipelines |
| Nilearn | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Atlas handling, region-of-interest signal extraction, and connectivity estimation |
| BIDS | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Data organization standard for the raw-input arm |

## 3. Denoising and quality-control methods

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| Framewise displacement | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Motion metric used in exclusion rules, QC-FC analysis, and reporting |
| CompCor and aCompCor | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Confound-regression strategy in the sensitivity universe |
| Confound-strategy benchmarking | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Basis for the predeclared confound-strategy set and QC-FC reporting conventions |
| ICA-AROMA | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Confound strategy used only where technically valid and supported by verified derivative requirements |

## 4. Connectivity and harmonization methods

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| Tangent-space connectivity | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Core connectivity estimator and the reference baseline representation for the deep-learning comparison |
| Ledoit-Wolf shrinkage | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Core connectivity estimator |
| Graphical lasso | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Sensitivity connectivity estimator at approximately 100 to 200 regions of interest |
| ComBat harmonization | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Harmonization sensitivity analysis, fitted training-only |

## 5. Atlases

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| AAL atlas | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Core atlas factor level |
| CC200 and CC400 atlases | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Core atlas factor level (CC200) and atlas sensitivity analysis (CC400) |
| Dosenbach-160 atlas | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Atlas sensitivity analysis |
| Harvard-Oxford atlas | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Atlas sensitivity analysis, where compatible |

## 6. Model architectures

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| BrainNetCNN | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Deep-learning model family evaluated on the sentinel configurations |
| Graph convolutional network | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Candidate compact graph model family; the specific architecture is selected before final training and its citation recorded then |
| Graph attention network | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Candidate compact graph model family; the specific architecture is selected before final training and its citation recorded then |
| Transformer architecture | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Compact transformer model family, where compatible time-series inputs exist |

## 7. Statistical methods

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| Hierarchical and clustered bootstrap methods | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Primary uncertainty method for all multi-site estimates and paired model comparisons |
| Permutation testing with restricted exchangeability | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Site-restricted label permutation and max-statistic family-wise adjustment |
| Intraclass correlation, ICC(3,1) | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Connectome-edge agreement metric in the pipeline-agreement analysis |
| Bland-Altman agreement | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Agreement limits in the pipeline-agreement analysis |
| Mixed-effects modeling software | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Variance attribution in the R inferential environment |

## 8. Reporting frameworks and study motivation

| Topic | Full citation | DOI or stable identifier | Authoritative source | Verification status | Verification date | Intended use in the study |
| --- | --- | --- | --- | --- | --- | --- |
| TRIPOD+AI | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Reporting structure for the prediction-model components of the manuscript |
| PROBAST+AI | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Risk-of-bias appraisal structure for the manuscript |
| Botvinik-Nezer et al., analytic flexibility across independent teams | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Motivating evidence for the multiverse framing and the central research question |
| Multiverse and specification-curve methodology | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Authoritative verification required before acquisition. | Unverified | Not verified | Methodological basis for the specification universe and the dispersion estimand |

---

## 9. Verification rules

- A row moves to `Verified` only when the full citation and a stable identifier have been read from an authoritative source and the verification date has been recorded in that row.
- Software citations are recorded at the exact version used, because version-specific citation requirements are common and a version mismatch misattributes the method actually run.
- Any pipeline that emits a citation boilerplate at runtime has that boilerplate retained verbatim with the run outputs and reconciled against this inventory before submission.
- A method that is used but absent from this inventory is an inventory defect and is added before the manuscript is submitted.
- No missing bibliographic information is ever reconstructed, inferred, or invented.
