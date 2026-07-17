# Decision Record 0001 — Dataset Roles and Study Design

- **Identifier:** 0001
- **Date:** 2026-07-17
- **Status:** Accepted, before outcome modeling
- **Governing protocol:** [../preregistration.md](../preregistration.md)

---

## Context

An earlier project blueprint proposed OpenNeuro ds000030 as the principal dataset for the study. ds000030 is a moderate, limited-site clinical cohort and should not simultaneously serve as the large-sample multiverse, the controlled raw-pipeline comparison, and the independent replication cohort. Under the blueprint's proposal, one such dataset would have carried three distinct scientific loads at once:

1. Supplying the statistical power needed to estimate dispersion across a large specification universe
2. Providing raw imaging inputs for a controlled comparison of independent preprocessing software
3. Serving as the basis for an independent clinical replication

These three demands are mutually incompatible in one dataset:

- **Power.** Estimating the 90th-minus-10th percentile spread of out-of-sample ROC-AUC across hundreds of specifications, with site-grouped validation, requires many participants distributed across many acquisition sites. A limited-site dataset cannot support five-fold site-grouped outer validation, because there are too few sites to form the required number of disjoint groups, and site-restricted permutation is correspondingly weak. The exact number of imaging sites contributing to ds000030 must be read from the authoritative source and is not assumed here.
- **Raw-pipeline comparison.** Running fMRIPrep, FSL, and AFNI over identical raw inputs is bounded by preprocessing compute and storage, not by statistical power. It requires raw imaging, which the large derivative collections do not distribute, and it is feasible only at small subject counts under a local-first compute strategy.
- **Independent replication.** A replication cohort must be independent of the cohort in which the effects were estimated. A dataset cannot replicate itself, and reusing ds000030 for both the pipeline-agreement analysis and the replication would make the replication conditional on the same data, the same sites, and the same acquisition protocol.

A dataset used for all three roles would additionally couple every failure mode: a cohort-specific artifact, a site-specific acquisition property, or a cohort-specific demographic skew would propagate into the dispersion estimate, the agreement estimate, and the replication simultaneously, with no independent evidence available to detect it.

The conflict was therefore resolved explicitly rather than by silently retaining the blueprint's proposal.

---

## Decision

Dataset roles are allocated so that each scientific demand is met by a dataset suited to it:

| Dataset | Role | Required |
| --- | --- | --- |
| ABIDE-I PCP | Main large-N multiverse and primary model-comparison dataset for RQ1-RQ4 | Required |
| OpenNeuro ds000030 | Controlled raw-data methods arm and pipeline-agreement dataset for RQ5; optional mid-scale clinical bridge analysis | Required for RQ5 |
| COBRE NIAK derivative | Independent schizophrenia replication dataset | Required |
| COBRE raw | Optional extension, requiring separate justification and approval | Optional |
| AOMIC-ID1000 | Optional healthy-population sensitivity analysis | Optional |

Specifically:

- **ABIDE-I PCP is the main large-sample multiverse and primary model-comparison dataset.** It supplies multi-site participants and four independently produced derivative pipelines (CCS, C-PAC, DPARSF, NIAK), which is what makes the preprocessing factor of the specification universe estimable at all.
- **OpenNeuro ds000030 is the controlled raw-data methods arm and pipeline-agreement dataset.** It supplies raw T1-weighted and resting-state BOLD inputs so that fMRIPrep, FSL, and AFNI can be compared on identical data with all downstream choices held constant.
- **COBRE is the independent schizophrenia replication dataset**, entered through its lightweight NIAK derivative rather than raw reprocessing.
- **AOMIC-ID1000 is optional** and must never become required for project completion.

The proposal to make ds000030 the principal dataset is explicitly **not** retained.

This decision is recorded in the protocol at Section 5 and is binding on all later work.

---

## Consequences

**Intended.**

- Stronger separation of scientific roles: power, raw preprocessing-method evaluation, and independent clinical replication are supplied by different datasets, so a defect in one does not silently propagate into all three conclusions.
- Lower dataset cost. Every dataset in the core design is expected to be obtainable at no purchase cost, consistent with the $0 dataset budget.
- Better multi-site statistical power for the dispersion and variance-attribution estimands, and site-grouped validation becomes meaningful because multiple sites exist.
- Raw neuroimaging engineering remains represented in the study through the ds000030 controlled arm, rather than being dropped in favor of derivative-only convenience.

**Accepted costs and constraints.**

- Cross-diagnostic replication must be interpreted as methodological transportability. The replication asks whether methodological influences behave consistently across cohorts and diagnoses. It is not the transfer of an autism classifier to schizophrenia, and no such claim may be made.
- Different cohorts cannot be described as biologically interchangeable. ABIDE, ds000030, and COBRE differ in population, diagnosis, acquisition, and ascertainment, and performance figures are not comparable across them as if they measured the same quantity.
- The main multiverse depends on derivative pipelines produced by a third party. Their quality-control flags are not equivalent to locally computed raw-image quality control, and the protocol forbids claiming that they are.
- The pipeline-agreement arm is small by construction. Its agreement estimates carry wide intervals, and its downstream classification results are exploratory only.
- Two diagnoses are studied across the cohorts, so a factor effect observed in ABIDE and absent in COBRE is ambiguous between a cohort difference and a diagnosis difference. The study reports this ambiguity rather than resolving it.

---

## Status

Accepted, before outcome modeling. No dataset had been downloaded and no model had been fitted when this decision was made.

Any change to this allocation requires an entry in [../deviations.md](../deviations.md) disclosing whether any outcome had been inspected at the time of the change.
