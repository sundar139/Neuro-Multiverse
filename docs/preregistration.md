# NeuroMultiverse Scientific Protocol

Version: 1.0
Protocol date: 2026-07-17
Document owner: study lead
Status: locked prior to outcome modeling

---

## 1. Protocol status and governance

This document is the scientific source of truth for the NeuroMultiverse study. It was authored and committed before any outcome modeling was performed.

### 1.1 Declarations

- This document was committed before outcome modeling.
- No ROC-AUC, log loss, QC-FC association, pipeline ranking, or model-comparison result has been produced or inspected for the purpose of making any decision recorded here.
- No dataset has been downloaded, no preprocessing has been executed, and no model has been fitted at the time of protocol lock.
- This protocol governs all subsequent implementation. Where implementation and protocol disagree, the protocol prevails until amended.
- Any later change to a locked decision requires an entry in [deviations.md](deviations.md).
- Each deviation entry must disclose whether any predictive or quality-control outcome had already been viewed at the time of the change.
- Negative, null, unstable, and non-replicating results will be reported with the same prominence as positive results.
- The study is intended to characterize analytic variability in resting-state functional-connectivity biomarkers. It is not intended to maximize a favorable score, and no result is treated as a success condition.

### 1.2 Deterministic seed policy

The project-wide base seed is frozen at:

```
20260717
```

All derived randomness must be generated deterministically from the tuple:

- Base seed
- Dataset identifier
- Subject-manifest version
- Specification identifier
- Outer fold index
- Inner fold index
- Replicate seed

The implementation must derive seeds using a stable, reproducible hash function whose output does not vary between processes or interpreter invocations. Python's built-in `hash()` is process-randomized for string inputs and must not be used for seed derivation. A stable digest (for example a cryptographic hash of a canonical string encoding, reduced to a 32-bit integer) is required.

Every recorded run must persist the full seed-derivation tuple alongside its outputs so that any single result can be regenerated in isolation.

---

## 2. Central research question

> How much variation in out-of-sample resting-state functional-connectivity biomarker performance is attributable to defensible preprocessing, parcellation, connectivity, harmonization, and model choices rather than stable neurobiological signal?

The primary scientific contribution is estimation of:

- Multiverse dispersion of out-of-sample performance across defensible analytic specifications
- Attribution of that dispersion to specific methodological factors
- The trade-off between artifact removal and predictive performance
- Transportability of methodological effects across cohorts and diagnoses
- Agreement between independent software pipelines applied to identical raw inputs

Success is defined as a complete, transparent, reproducible characterization of these quantities. Success is explicitly **not** defined as achieving a particular best ROC-AUC value, and no threshold of predictive accuracy constitutes a positive or negative outcome for this study.

---

## 3. Research questions and hypotheses

Five research questions are locked. No research question may be added, removed, or reworded after outcome inspection without a recorded deviation.

### 3.1 RQ1 — Multiverse dispersion

**Question.** How much does out-of-sample prediction vary across defensible analysis specifications?

**Primary hypothesis.** The 90th-minus-10th percentile ROC-AUC spread across valid core specifications will be scientifically meaningful and larger than trivial split-to-split variation observed under a fixed specification.

**Primary outcome.** The 90th-minus-10th percentile ROC-AUC spread across valid core specifications on the frozen ABIDE common-subject cohort.

**Secondary outcomes.**

- ROC-AUC interquartile range
- Median ROC-AUC
- Distribution of cross-validated log loss
- Proportion of specifications exceeding the demographics-only baseline
- Proportion of specifications exceeding site-restricted permutation expectations

The maximum-minus-minimum range is recorded for completeness but is explicitly **not** a primary dispersion measure, because it is determined by two extreme specifications and is unstable under resampling.

**Unit of analysis.** The specification, evaluated on the frozen outer splits of the common-subject cohort.

**Planned uncertainty estimate.** Hierarchical bootstrap over sites and subjects within sites, recomputing the percentile spread on each resample.

**Null interpretation.** If the percentile spread is small and its bootstrap interval excludes practically meaningful dispersion, the conclusion is that out-of-sample performance in this domain is robust to the surveyed analytic choices. This is a publishable and informative result.

**Alternative interpretation.** If the percentile spread is large, the conclusion is that reported single-specification performance figures in this literature are weakly identified by the data alone and are substantially determined by analyst choices.

**Conditions preventing a strong conclusion.** Fewer than 300 valid specifications; systematic failure concentrated in one factor level such that the surviving universe is no longer balanced; evidence of leakage in a substantial share of specifications.

### 3.2 RQ2 — Variance attribution

**Question.** Which methodological decisions account for the greatest share of performance variation?

**Factors under study.**

- Preprocessing pipeline (Preprocessed Connectomes Project derivative pipeline)
- Temporal filtering
- Global signal regression
- Atlas
- Connectivity estimator
- Model family
- Predeclared major interactions: preprocessing-by-global-signal-regression, and connectivity-by-model

**Hypothesis.** Preprocessing and feature-construction choices will explain a substantial share of performance variation, while model family will explain less variation than is commonly assumed in the applied literature.

This is stated as a falsifiable expectation. A finding that model family dominates, or that no factor explains appreciable variation, is an equally reportable outcome and must not trigger a rewritten hypothesis.

**Primary outcome.** The share of validated performance variation associated with each preregistered factor and each predeclared interaction.

**Secondary outcomes.** Marginal contrasts within each factor; rank stability of factor levels under bootstrap; interaction contrast estimates.

**Unit of analysis.** The specification-by-outer-fold performance record, with subject-level out-of-fold log loss used for the proper-scoring analysis.

**Planned uncertainty estimate.** Bootstrap intervals on variance shares, resampling sites and subjects within sites, refitting the attribution model on each resample.

**Null interpretation.** No factor accounts for appreciable variance beyond fold-level noise; analytic choices are exchangeable in their effect on performance.

**Alternative interpretation.** One or more factors account for a substantial and stable share of variance, identifying where methodological standardization would most reduce reported heterogeneity.

**Conditions preventing a strong conclusion.** Severe imbalance in valid specifications across factor levels; non-convergence of the attribution model; variance shares whose bootstrap intervals span the plausible range.

### 3.3 RQ3 — Denoising and prediction trade-off

**Question.** Do specifications that best reduce motion-related artifact also provide the strongest clinical prediction?

**Primary outcome.** The association between QC-FC artifact measures and out-of-sample prediction, estimated across specifications while accounting for specification structure and repeated evaluation.

**Secondary outcomes.**

- Mean absolute QC-FC
- Percentage of nominally significant QC-FC edges
- QC-FC distance-dependence slope
- Association of connectivity with mean framewise displacement
- Retained volumes
- Remaining scan duration
- Lost temporal degrees of freedom
- ROC-AUC
- Log loss

**Hypothesis.** More aggressive denoising will not necessarily maximize clinical prediction; artifact-optimal and prediction-optimal specifications may diverge.

**Unit of analysis.** The specification, with edge-level QC-FC statistics summarized to specification level before the cross-specification analysis.

**Planned uncertainty estimate.** Hierarchical bootstrap over sites and subjects within sites for the QC-FC summaries, and bootstrap intervals on the artifact-versus-performance association.

**Null interpretation.** Artifact-removal quality and predictive performance are unrelated across specifications, implying that denoising choices cannot be justified by predictive gain and must be justified on artifact grounds alone.

**Alternative interpretation.** A systematic trade-off exists, in which case the study reports its direction, magnitude, and stability rather than recommending a single optimum.

**Conditions preventing a strong conclusion.** Insufficient variation in QC-FC across the compatible specifications; motion metrics unavailable or non-comparable across derivative pipelines; confounding of denoising with pipeline identity such that the two cannot be separated.

### 3.4 RQ4 — Model capacity and deep learning

**Question.** Under the available sample sizes, do BrainNetCNN, graph neural networks, temporal convolutional networks, or compact transformers outperform a leakage-safe tangent-space linear baseline?

**Hypothesis.** Any apparent deep-learning gain may be smaller than the variation caused by preprocessing choice, and may be unstable across random seeds.

**Primary outcome.** Paired difference in ROC-AUC between each deep-learning family and the tangent-space L2 logistic-regression baseline, on identical outer folds and identical subjects, summarized across five final seeds.

**Secondary outcomes.** Log loss; calibration slope and intercept; seed-to-seed standard deviation; label-shuffle control performance; parameter counts; runtime and GPU-hour cost per unit of performance.

**Requirements.**

- Identical outer folds for every model family
- Identical subject manifests
- Identical frozen sentinel configurations
- Five final seeds per model family per sentinel configuration
- Early stopping using a validation split drawn exclusively from the outer-training partition
- Logged training and validation curves
- Reported parameter counts
- Reported runtime and GPU-hour accounting
- Label-shuffle controls
- Reported mean, standard deviation, and the complete distribution of all five seeds

**Unit of analysis.** The model-family-by-sentinel-configuration-by-seed record, evaluated on the frozen outer folds.

**Planned uncertainty estimate.** Hierarchical bootstrap on paired out-of-fold predictions for the model contrast, plus the empirical seed distribution reported in full.

**Null interpretation.** Deep-learning families do not exceed the tangent-space linear baseline by a practically meaningful margin at these sample sizes.

**Alternative interpretation.** One or more deep-learning families exceed the baseline stably across seeds and sentinel configurations, in which case the gain is reported alongside its cost and its size relative to preprocessing-induced variation.

**Conditions preventing a strong conclusion.** Seed variance comparable to or larger than the model contrast; label-shuffle controls exceeding chance; training instability or systematic non-convergence; sample size insufficient to resolve the smallest interpretable difference.

No single-seed result is admissible as evidence for any claim under RQ4.

### 3.5 RQ5 — Software-pipeline agreement

**Question.** Do fMRIPrep, FSL, and AFNI produce interchangeable derivatives and connectivity representations from identical raw inputs?

**Primary outcomes.**

- Brain-mask Dice coefficient
- Jaccard similarity
- Registration similarity
- Temporal signal-to-noise ratio
- Retained-volume differences
- Connectome-edge intraclass correlation
- Matrix correlation
- Frobenius distance
- Bland-Altman agreement
- Subject-identification accuracy
- Representation-level similarity

**Secondary outcomes.** Distributional summaries of the above by region and by edge distance; downstream classification performance, which is exploratory only.

**Unit of analysis.** The subject-by-pipeline-pair record for agreement metrics; the edge for intraclass correlation summaries.

**Planned uncertainty estimate.** Bootstrap confidence intervals over subjects for central agreement estimates.

**Hypothesis.** Independent software pipelines applied to identical raw inputs will not produce interchangeable derivatives, and disagreement will be large enough to matter for downstream connectivity estimates.

**Null interpretation.** Pipelines agree closely on all recorded metrics, supporting the interchangeability assumed implicitly in much of the literature.

**Alternative interpretation.** Pipelines disagree materially, in which case the magnitude and locus of disagreement are reported without attributing either pipeline's output to biology.

**Conditions preventing a strong conclusion.** With approximately 20 participants, downstream classification comparisons are exploratory and must not be presented as strong inferential evidence. Agreement estimates themselves are reported with confidence intervals reflecting the small sample.

---

## 4. Primary estimands

Five primary estimands are locked.

### 4.1 Estimand 1 — Multiverse dispersion

**Definition.** The 90th-minus-10th percentile difference in outer-validation ROC-AUC across valid core specifications on the frozen ABIDE common-subject cohort.

- **Population.** Participants in the frozen ABIDE-I common-subject cohort as defined in Section 6.
- **Methodological factor.** The full core specification, treated as the unit whose variation is being characterized.
- **Outcome.** Outer-validation ROC-AUC, pooled across outer folds using out-of-fold predictions.
- **Summary measure.** Difference between the 90th and 10th percentiles of the specification-level ROC-AUC distribution.
- **Handling of invalid specifications.** Invalid specifications are excluded from the percentile computation, counted in the specification ledger, and classified by failure reason. The count and classification are reported alongside the estimate. A sensitivity analysis reports the dispersion estimate under the assumption that failures are non-random with respect to factor levels.
- **Handling of missing subjects.** The common-subject cohort is complete by construction. The maximum-available cohort sensitivity analysis quantifies the effect of availability-driven missingness.
- **Uncertainty method.** Hierarchical bootstrap resampling sites, then subjects within sites, recomputing all specification metrics and the percentile spread on each resample.
- **Sensitivity analyses.** Maximum-available cohort; leave-one-site-out outer validation; alternative percentile pairs reported descriptively; dispersion recomputed excluding each pipeline in turn.
- **Interpretation limits.** The estimate characterizes dispersion within the surveyed universe only. It does not bound the dispersion of the full space of defensible analyses, and it does not identify a correct specification.

### 4.2 Estimand 2 — Factor variance attribution

**Definition.** The share of validated performance variation associated with each preregistered methodological factor and each predeclared interaction.

- **Population.** Frozen ABIDE common-subject cohort.
- **Methodological factors.** Preprocessing pipeline, temporal filtering, global signal regression, atlas, connectivity estimator, model family, and the two predeclared interactions.
- **Outcome.** Subject-level out-of-fold log loss for the proper-scoring analysis; logit-transformed fold-level ROC-AUC for the supporting descriptive analysis.
- **Summary measure.** Variance share attributable to each factor, with marginal contrasts between factor levels.
- **Handling of invalid specifications.** Excluded from model fitting, reported in the ledger with counts by factor level. Imbalance induced by exclusion is reported and its effect assessed by refitting on the largest fully balanced sub-universe.
- **Handling of missing subjects.** Not applicable within the common-subject cohort by construction.
- **Uncertainty method.** Bootstrap variance decomposition, resampling sites and subjects within sites.
- **Sensitivity analyses.** Attribution recomputed on the maximum-available cohort; recomputed with ROC-AUC as the outcome; recomputed on the balanced sub-universe.
- **Interpretation limits.** Variance shares are conditional on the surveyed universe and its balance. They are descriptive of this design, not of neuroimaging analysis in general.

### 4.3 Estimand 3 — Artifact and prediction association

**Definition.** The association between QC-FC artifact measures and out-of-sample prediction, accounting for specification structure and repeated evaluation.

- **Population.** Frozen ABIDE common-subject cohort for the core arm; ds000030 and COBRE cohorts for the confound-strategy sensitivity arm.
- **Exposure.** QC-FC artifact summary of a specification.
- **Outcome.** Specification-level ROC-AUC and log loss.
- **Summary measure.** Regression slope of performance on artifact summary, with the specification structure represented in the model.
- **Handling of invalid specifications.** Excluded and reported; a specification lacking a computable QC-FC summary is excluded from this estimand only, not from other estimands.
- **Handling of missing subjects.** Motion metrics must be present for a subject to contribute to a QC-FC summary. Subjects lacking motion metrics are counted and reported by pipeline.
- **Uncertainty method.** Hierarchical bootstrap over sites and subjects within sites.
- **Sensitivity analyses.** Association recomputed using each QC-FC summary variant separately; recomputed excluding specifications with global signal regression; recomputed within pipeline.
- **Interpretation limits.** Observational across specifications. A lower QC-FC value is not evidence of greater biological validity, and the association is not causal.

### 4.4 Estimand 4 — Transportability of methodological effects

**Definition.** The consistency of methodological-factor rankings and effects across ds000030 and COBRE.

- **Population.** ds000030 cohort and COBRE derivative cohort, analyzed independently.
- **Methodological factors.** Those factors of the core universe that are reproducible on each replication cohort.
- **Outcome.** Factor-level performance effects and their rank ordering.
- **Summary measure.** Rank correlation and effect-agreement statistics between the ABIDE factor effects and each replication cohort's factor effects.
- **Handling of invalid specifications.** As for Estimand 2, computed per cohort.
- **Handling of missing subjects.** Cohort-specific eligibility rules apply; counts reported per cohort.
- **Uncertainty method.** Bootstrap intervals on the rank-agreement statistics.
- **Sensitivity analyses.** Agreement recomputed restricting to factors present in all three cohorts; recomputed with the alternative outcome metric.
- **Interpretation limits.** This estimand evaluates whether methodological influences behave similarly in different cohorts and diagnoses. It is **not** the transfer of an autism classifier to schizophrenia, and no cross-diagnostic biological claim follows from it. Cohorts differ in population, acquisition, and diagnostic ascertainment and are not biologically interchangeable.

### 4.5 Estimand 5 — Pipeline agreement

**Definition.** Agreement of fMRIPrep, FSL, and AFNI derivatives on identical ds000030 subjects.

- **Population.** The ds000030 controlled subset defined in Section 6.
- **Exposure.** Preprocessing software identity, with all other analytic choices held constant to the extent technically possible.
- **Outcome.** The spatial, temporal, and connectome agreement metrics listed in Section 3.5 and Section 18.
- **Summary measure.** Central agreement estimate per metric per pipeline pair, with confidence interval.
- **Handling of invalid specifications.** A subject failing preprocessing under any compared pipeline is excluded from paired agreement for that pair, retained in the ledger, and the exclusion reported with its reason.
- **Handling of missing subjects.** Paired analyses require the subject to complete all compared pipelines. Counts of complete triples are reported.
- **Uncertainty method.** Bootstrap over subjects.
- **Sensitivity analyses.** Agreement recomputed per pipeline pair; recomputed with an alternative atlas where technically compatible.
- **Interpretation limits.** With approximately 20 participants, agreement estimates carry wide intervals and downstream classification is exploratory. Pipeline differences are software-engineering differences and must never be described as biological differences.

---

## 5. Dataset roles

The dataset allocation below resolves a conflict with an earlier project blueprint that proposed OpenNeuro ds000030 as the principal dataset. The rationale is recorded in [decisions/0001-study-design.md](decisions/0001-study-design.md). The refined allocation separates statistical power, raw preprocessing-method evaluation, and independent clinical replication into distinct datasets, because no single moderate-sized dataset can credibly serve all three roles at once.

### 5.1 Dataset-role table

| Dataset | Scientific role | Required | Main contrast | Purchase cost | Verification status |
| --- | --- | --- | --- | --- | --- |
| ABIDE-I PCP | Main large-N multiverse and primary model comparison for RQ1-RQ4 | Required | ASD versus control | None expected | Authoritative verification required before acquisition. |
| OpenNeuro ds000030 | Controlled raw-pipeline comparison for RQ5; optional mid-scale clinical bridge analysis | Required for RQ5 | Schizophrenia versus control | None expected | Authoritative verification required before acquisition. |
| COBRE NIAK derivative | Independent schizophrenia replication for RQ4 transportability | Required | Schizophrenia versus control | None expected | Authoritative verification required before acquisition. |
| COBRE raw | Optional extension only | Optional | Schizophrenia versus control | None expected | Authoritative verification required before acquisition. |
| AOMIC-ID1000 | Optional healthy-population sensitivity analysis | Optional | Not applicable | None expected | Authoritative verification required before acquisition. |

The dataset purchase budget is zero. Any dataset requiring payment is out of scope.

### 5.2 ABIDE-I PCP

- **Role.** Main large-sample multiverse and primary model-comparison dataset for RQ1 through RQ4.
- **Expected content.** Participant phenotype tables and preprocessed region-of-interest time series derived by the Preprocessed Connectomes Project.
- **Core pipelines used.** CCS, C-PAC, DPARSF, NIAK.
- **Main contrast.** Autism spectrum disorder versus typical control.
- **Primary cohort.** Common-subject cohort (Section 6.1).
- **Sensitivity cohort.** Maximum-available cohort (Section 6.2).
- **Authoritative source.** Authoritative verification required before acquisition.
- **Access mechanism.** Authoritative verification required before acquisition.
- **License or data-use terms.** Authoritative verification required before acquisition.
- **Expected file formats.** Tabular phenotype data and per-subject region-of-interest time-series files. Exact formats: Authoritative verification required before acquisition.
- **Planned repository-external storage location.** A local directory outside the Git working tree, recorded in the acquisition log at download time and never committed.
- **Approximate size.** Estimate only, not verified. The region-of-interest time series and phenotype tables are expected to be small relative to volumetric derivatives; no numeric estimate is asserted here because it would not be verifiable. Authoritative verification required before acquisition.
- **Integrity-check strategy.** Record a content hash for every downloaded file at acquisition time, store the manifest of hashes outside the repository, and re-verify before each analysis run.
- **Dataset-version recording.** Record the release or revision identifier reported by the authoritative source at download time, together with the download date.
- **Citation requirements.** Authoritative verification required before acquisition. Tracked in [citation_inventory.md](citation_inventory.md).
- **Ethical, privacy, and bias considerations.** Secondary research data. Site composition, age range, sex imbalance, and diagnostic ascertainment differ across contributing sites and may bias both performance and its variance attribution. Site is a known confounder of diagnosis in this collection and is handled by grouped validation and a site-only diagnostic baseline.
- **Prohibition.** No raw data or restricted derivative may be committed to this repository.

### 5.3 OpenNeuro ds000030

- **Role.** Controlled raw-pipeline comparison dataset for RQ5, and optional mid-scale clinical bridge analysis.
- **Main contrast.** Schizophrenia versus control.
- **Controlled subset.** 20 subjects, 10 per class (Section 6.3).
- **Constraint.** All compared pipelines must consume the same raw T1-weighted and resting-state BOLD inputs for the same subjects.
- **Authoritative source.** Authoritative verification required before acquisition.
- **Access mechanism.** Authoritative verification required before acquisition.
- **License or data-use terms.** The dataset's license status must be read from the authoritative source at acquisition time. Authoritative verification required before acquisition.
- **Expected file formats.** BIDS-organized NIfTI imaging data with sidecar metadata and participant tables. Exact organization: Authoritative verification required before acquisition.
- **Planned repository-external storage location.** A local directory outside the Git working tree, recorded in the acquisition log and never committed.
- **Approximate size.** Estimate only, not verified. Raw imaging data for the controlled subset plus three sets of derivatives are expected to dominate project storage. Authoritative verification required before acquisition.
- **Integrity-check strategy.** Content hash per downloaded file, manifest stored outside the repository, re-verified before preprocessing.
- **Dataset-version recording.** Record the exact dataset version or snapshot identifier reported by the authoritative source at download time.
- **Citation requirements.** Authoritative verification required before acquisition.
- **Ethical, privacy, and bias considerations.** Secondary research data. Limited-site acquisition limits generalization. The number of contributing imaging sites, participant counts by diagnosis, and demographic composition must be read from the authoritative source rather than assumed. Authoritative verification required before acquisition.
- **Prohibition.** No raw data or derivative imaging may be committed to this repository.

### 5.4 COBRE NIAK derivative

- **Role.** Independent schizophrenia replication supporting Estimand 4.
- **Analysis scope.** Begin with the lightweight derivative rather than raw full reprocessing. Use linear-model and QC-FC analyses. The full deep-learning analysis is **not** automatically extended to this cohort.
- **Authoritative source.** Authoritative verification required before acquisition.
- **Access mechanism.** Authoritative verification required before acquisition.
- **License or data-use terms.** Authoritative verification required before acquisition.
- **Expected file formats.** Derivative connectivity or region-of-interest time-series files with an accompanying phenotype table. Exact content: Authoritative verification required before acquisition.
- **Planned repository-external storage location.** A local directory outside the Git working tree.
- **Approximate size.** Estimate only, not verified. Authoritative verification required before acquisition.
- **Integrity-check strategy.** Content hash per downloaded file, manifest stored outside the repository.
- **Dataset-version recording.** Record the derivative release identifier and download date.
- **Citation requirements.** Authoritative verification required before acquisition.
- **Ethical, privacy, and bias considerations.** Secondary research data governed by its own data-use terms. Diagnostic labels are research labels. Local usable participant counts may differ from published counts and any mismatch must be documented rather than reconciled silently.
- **Prohibition.** No raw data or restricted derivative may be committed to this repository.

### 5.5 COBRE raw

- **Role.** Optional extension only.
- **Requirement.** Reprocessing COBRE raw data requires separate scientific justification, an access review, a compute review, and either a recorded deviation or an approved extension recorded before execution.
- **Constraint.** This arm must not be required for core project completion and must not be initiated to rescue an unfavorable replication result.
- **Authoritative source, access, license, size, citation.** Authoritative verification required before acquisition.

### 5.6 AOMIC-ID1000

- **Role.** Optional healthy-population sensitivity analysis.
- **Constraint.** Must not delay or block core completion. Omitting this dataset entirely is a valid outcome and does not constitute an incomplete study.
- **Authoritative source, access, license, size, citation.** Authoritative verification required before acquisition.

### 5.7 Fabrication prohibition

No URL, license name, participant count, release version, checksum, or citation may be invented. Where live verification was not available at protocol authoring time, the exact phrase "Authoritative verification required before acquisition." is used and must be replaced only with a value read from the authoritative source, together with the verification date, in [data_usage.md](data_usage.md).

---

## 6. Cohort policies

### 6.1 ABIDE primary common-subject cohort

A participant is included if and only if all of the following hold:

- Present in every core pipeline and strategy combination required for direct comparison
- Satisfies Preprocessed Connectomes Project quality-control eligibility
- Contributes exactly one scan
- Has a valid diagnosis
- Has a valid age
- Has a valid sex
- Has a valid site
- Has valid requested region-of-interest time series
- Has no duplicated participant identifier
- Belongs to a site retained under the frozen site-eligibility rule

**Frozen site-eligibility rule.** A site is retained if it contributes at least 10 participants from each diagnostic class within the candidate common-subject cohort.

Feasibility of this rule will be checked using phenotype metadata before any modeling, and without inspecting any predictive outcome.

If the threshold makes grouped evaluation infeasible or removes an excessive proportion of participants, the rule may be changed only when all of the following hold:

- The change is made before any model outcome is inspected
- Exact participant and site counts under both rules are documented
- The change is recorded in [deviations.md](deviations.md)
- Both the original and revised thresholds are reported in the final manuscript

### 6.2 ABIDE maximum-available cohort

- Includes every otherwise valid subject available for each specification, without requiring presence across all pipelines.
- Used only as a missingness and real-world-availability sensitivity analysis.
- Its raw performance must never be compared directly with the common-subject cohort without identifying and reporting the population differences that separate them, because the two cohorts describe different populations.

### 6.3 ds000030 controlled subset

- Exactly 20 participants when feasible: 10 with schizophrenia and 10 controls.
- Participants must have the required T1-weighted and resting-state BOLD inputs.
- Sex balanced as closely as the candidate pool permits.
- Age matched as closely as possible using metadata only, without examining any imaging-derived outcome.
- Selection performed by a deterministic matching algorithm seeded from the frozen base seed 20260717.
- The complete candidate set and the selection algorithm must be recorded so that the selection can be reproduced exactly.
- Hand-picking subjects on the basis of visually favorable preprocessing is prohibited.

### 6.4 ds000030 mid-scale cohort

- Target 60 to 80 participants.
- Volumetric processing with `--fs-no-reconall`.
- Optional and contingent on available compute capacity and on successful validation of the smaller pilot arm.
- The subject count must not be expanded after outcome inspection in order to obtain statistical significance.

### 6.5 COBRE cohort

- Use all eligible derivative subjects satisfying the frozen metadata, quality, and feature-availability rules.
- Any mismatch between published cohort counts and locally usable counts must be documented with both numbers and an explanation of the difference.
- Removing subjects to improve model performance is prohibited.

---

## 7. Exclusion and quality-control policy

### 7.1 Raw-preprocessed datasets

Predeclared exclusions:

- Exclude subjects with mean framewise displacement greater than 0.5 mm.
- Exclude subjects with fewer than 120 surviving volumes, or with less than four minutes of retained resting-state data, after the applicable scrubbing rule.
- Exclude subjects with failed manual normalization or brain-extraction review.

Requirements:

- Every manual exclusion is recorded in a machine-readable quality-control table.
- Each record requires an explicit reviewer identifier, date, reason code, and free-text explanation.
- A subject must not be excluded solely because a variable is associated with diagnosis.
- Diagnosis-group differences in motion and in retained data must be reported.

### 7.2 ABIDE derivatives

- The quality-control flags supplied with the Preprocessed Connectomes Project derivatives are the initial source of eligibility.
- No claim of equivalence between these supplied flags and locally computed raw-image quality control may be made.
- Record missing regions of interest, non-finite values, zero-variance signals, temporal length, and pipeline availability for every subject and specification.
- Apply identical rule definitions across specifications wherever the underlying derivatives permit, and record every case where they do not.

### 7.3 Subject-level quality-control fields

The following fields must be preserved for every subject in every applicable arm:

- Mean framewise displacement
- Median framewise displacement
- Maximum framewise displacement
- DVARS
- Temporal signal-to-noise ratio
- Censored-volume count and percentage
- Remaining duration
- Registration status
- Brain-mask coverage
- Missing region-of-interest count
- Confound matrix rank
- Confound matrix condition number
- Effective temporal degrees of freedom

### 7.4 Reviewer blinding

Manual quality-control reviewers must be blinded to model performance. Quality-control review must be completed and frozen before the performance of the affected subjects is inspected.

---

## 8. Core multiverse

### 8.1 Locked factors

| Factor | Levels |
| --- | --- |
| Preprocessing pipeline | CCS, C-PAC, DPARSF, NIAK |
| Temporal filtering | Filtered, Unfiltered |
| Global signal regression | Yes, No |
| Atlas | AAL, CC200 |
| Connectivity | Pearson correlation with Fisher-z transformation, Ledoit-Wolf shrinkage covariance converted to correlation, Tangent-space embedding |
| Model | L2 logistic regression, Linear support-vector machine, Elastic-net logistic regression, Extra Trees |

### 8.2 Universe size

The core universe contains exactly 384 specifications:

```
4 (pipeline) x 2 (filtering) x 2 (global signal regression) x 2 (atlas) x 3 (connectivity) x 4 (model) = 384
```

Intermediate confirmation: 4 x 2 = 8; 8 x 2 = 16; 16 x 2 = 32; 32 x 3 = 96; 96 x 4 = 384.

### 8.3 Definition of a valid specification

A specification is valid if and only if it:

- Uses an eligible frozen manifest
- Produces finite features
- Meets the declared matrix and sample constraints
- Completes every required outer fold
- Produces out-of-fold predictions
- Passes all leakage checks
- Has traceable configuration and provenance
- Has no unresolved critical implementation error

### 8.4 Failure handling

Failures must be counted and classified by reason. They must not be silently dropped. The specification ledger retains every attempted specification with its final status. No specification may be added to or removed from the core universe after outcome inspection without a recorded deviation.

---

## 9. Sensitivity universe

The following are predeclared sensitivity analyses. They are **not** additions to the core 384 and are never pooled with the core universe when computing Estimand 1.

### 9.1 Atlas sensitivity

- CC400
- Dosenbach-160
- Harvard-Oxford, where compatible with the available derivatives

### 9.2 Connectivity sensitivity

- Shrinkage partial correlation
- Graphical lasso, only at approximately 100 to 200 regions of interest
- Graph summary metrics

### 9.3 Harmonization sensitivity

- No harmonization
- Train-only ComBat
- Site covariates
- Training-only site centering

### 9.4 Confound sensitivity for ds000030 and COBRE

- Motion-6
- Motion-24
- Motion-24 plus white-matter and cerebrospinal-fluid signals
- Motion-24 plus aCompCor
- Motion-24 plus global signal
- Aggressive strategy with scrubbing
- ICA-AROMA, only where technically valid and supported by verified derivative requirements

For every confound strategy the following must be recorded:

- Number of nuisance columns
- Matrix rank
- Condition number
- Retained frames
- Effective remaining temporal degrees of freedom

### 9.5 Convergence reporting

Graphical lasso convergence failures must be reported as failures. They must not be hidden, and they must not be forced through by adjusting regularization or solver settings until convergence is obtained.

---

## 10. Deep-learning sentinel universe

### 10.1 Frozen sentinel configurations

Deep learning is limited to no more than five frozen sentinel preprocessing configurations:

1. C-PAC, filtered, no global signal regression, CC200
2. C-PAC, filtered, global signal regression, CC200
3. CCS, filtered, no global signal regression, CC200
4. DPARSF, filtered, no global signal regression, CC200
5. NIAK, filtered, no global signal regression, CC200

### 10.2 Model families

- BrainNetCNN
- One compact graph convolutional network or graph attention network, selected before final training
- One-dimensional temporal convolutional network, where compatible region-of-interest time-series inputs exist
- Compact transformer, where compatible time-series inputs exist
- Tangent-space L2 logistic regression on matching subjects and folds, serving as the reference baseline

At most four deep-learning model families are permitted.

### 10.3 Training rules

- Five final seeds per family per sentinel configuration
- Identical outer folds across all families
- Early stopping performed wholly inside the outer-training data
- Fixed maximum epoch and trial budget, chosen before final execution
- Mixed precision where numerically safe
- Gradient clipping
- Training and validation curves logged and retained
- Parameter counts recorded
- Wall-clock and GPU-hour accounting recorded
- Full seed distribution reported, not only its mean
- Label-shuffle experiment executed and reported
- Failed and unstable runs retained in the audit trail

No single-seed claim is admissible.

---

## 11. Validation design

### 11.1 Primary outer validation

- Five-fold grouped validation
- Grouping variable: acquisition site
- Class stratification where feasible
- Frozen seed 20260717
- No site may appear in both the training and the test portion of a single outer split
- All specifications must use the same saved outer splits

Preferred implementation for later work:

```python
StratifiedGroupKFold(
    n_splits=5,
    shuffle=True,
    random_state=20260717
)
```

Exact feasibility of stratified grouped splitting will be verified from cohort metadata before modeling. If site and class structure make five stratified grouped folds infeasible, the fallback is grouped five-fold validation without stratification, and the choice must be recorded in the split manifest and reported.

### 11.2 Sensitivity validation

- Leave-one-site-out validation for sites with adequate cases and controls
- Sites excluded from this sensitivity analysis must be reported together with the reason for exclusion

### 11.3 Inner validation

- Four grouped folds
- Grouped by site
- Class-stratified where feasible
- Hyperparameters selected exclusively using outer-training data

The outer-test fold is used exactly once, for unbiased prediction.

### 11.4 Split manifests

Split manifests must be saved and must contain, per row:

- Subject identifier
- Dataset
- Manifest version
- Outer fold
- Inner fold
- Split seed
- Split version
- Site
- Diagnosis

---

## 12. Leakage-control rules

### 12.1 Fold-scoped operations

Every learned or outcome-informed operation must occur inside the appropriate training fold. This includes, without limitation:

- Missing-value imputation
- Scaling
- Feature selection
- Principal component analysis
- Data-driven decompositions
- Subject-level confound adjustment used as a learned transformation
- ComBat
- Site centering
- Tangent-space reference covariance estimation
- Class weighting derived from prevalence
- Threshold selection
- Calibration
- Hyperparameter optimization

### 12.2 Mandatory tests

The following tests are predeclared and must exist and pass before any core result is reported:

1. Tangent reference means are fit on training subjects only.
2. ComBat cannot access outer-test features, outcomes, or test-derived parameters while fitting.
3. Scaling statistics change when the training subjects change.
4. Shuffled labels produce chance-compatible performance.
5. Site-only performance is calculated and disclosed.
6. Duplicate subject identifiers cannot cross folds.
7. Every specification uses the intended frozen manifest.
8. A feature cache built using all subjects cannot be reused inside nested validation.
9. Split manifests are identical across model families.
10. Deliberately leaky implementations fail the leakage tests.

Test 10 is a mutation check: an intentionally leaky variant must be rejected by the suite, demonstrating that the suite has power to detect leakage rather than merely passing.

---

## 13. Outcomes and metrics

### 13.1 Primary predictive metrics

- ROC-AUC
- Cross-validated log loss

### 13.2 Secondary metrics

- PR-AUC
- Balanced accuracy
- Sensitivity
- Specificity
- Matthews correlation coefficient
- Brier score
- Calibration slope
- Calibration intercept

Plain accuracy must not be used as a main outcome. No decision threshold may be chosen using outer-test data.

### 13.3 Required baselines

For each applicable dataset:

- Chance classifier
- Majority classifier
- Age and sex
- Age, sex, and site
- Site-only
- Mean-connectivity summary
- Tangent-space features with L2 logistic regression
- Linear support-vector machine

The site-only model is presented as a confounding diagnostic. Its performance quantifies how much of the apparent diagnostic signal is recoverable from acquisition site alone, and it must be reported alongside every headline performance figure for the same cohort.

---

## 14. Confidence intervals and model comparisons

### 14.1 Hierarchical bootstrap

The primary uncertainty method resamples the multi-site structure:

1. Resample sites with replacement.
2. Resample subjects with replacement within the selected sites.
3. Preserve paired out-of-fold predictions across the models being compared.
4. Recalculate metrics and paired differences on each resample.

An ordinary flat bootstrap over subjects must not be used as the primary method for multi-site data, because it ignores between-site variance and produces intervals that are too narrow. An uncorrected t-test over cross-validation folds must not be used, because folds are not independent.

### 14.2 Required reporting

For every comparison, report:

- Point estimate
- 95% confidence interval
- Paired difference when comparing models
- Uncertainty for the difference

Numerical superiority without an interval excluding a practically negligible difference must not be described as proven superiority.

### 14.3 Smallest-effect interpretation rule

A model difference smaller than 0.01 ROC-AUC is considered practically small unless accompanied by a compelling improvement in calibration, log loss, robustness, or compute efficiency.

This is an interpretation threshold, not a significance threshold. It does not license declaring a larger difference significant, and it does not replace the confidence interval.

---

## 15. Permutation testing

### 15.1 Primary baseline specification

- 1,000 site-restricted label permutations

### 15.2 Full multiverse

- 100 to 250 site-restricted permutations, subject to the frozen compute cap
- Site structure preserved in every permutation
- The maximum statistic across specifications is recorded
- Family-wise inference uses max-statistic adjustment

### 15.3 Prohibition

Labels must never be permuted globally when site and diagnosis are coupled, because global permutation destroys the site-diagnosis dependence and produces an anticonservative null.

### 15.4 Required records

- Permutation seed
- Exchangeability block
- Number requested
- Number completed
- Failed permutations
- Statistic
- Adjustment procedure

---

## 16. Variance attribution

R is the primary inferential environment for variance attribution.

### 16.1 Predeclared model family

```
performance ~
    preprocessing +
    filtering +
    gsr +
    atlas +
    connectivity +
    model +
    preprocessing:gsr +
    connectivity:model +
    (1 | outer_fold) +
    (1 | subject_manifest)
```

### 16.2 Analysis declarations

- ROC-AUC specification curves are primarily descriptive.
- Logit-transformed fold-level ROC-AUC may be modeled, with caution, because fold AUC is bounded, correlated across folds, and heteroscedastic.
- Bootstrap variance decomposition must confirm the central conclusions. A conclusion supported only by the parametric model fit is not reported as a central finding.
- Subject-level out-of-fold log loss is the preferred outcome for proper-scoring analysis.
- Random effects for subject and site must be used where supported by the data structure; where the structure does not support them, the reduced model and the reason must be reported.
- Hundreds of coefficient-level p-values will not be treated as the main result.

### 16.3 Primary inferential outputs

- Variance shares
- Marginal contrasts
- Bootstrap intervals
- Major interaction patterns
- Rank stability

---

## 17. QC-FC analysis

For every compatible denoising specification, compute:

- Correlation of each connectome edge with mean framewise displacement
- Mean absolute QC-FC
- Percentage of nominally significant QC-FC edges
- Relationship between QC-FC and inter-region distance
- Distance-dependence slope
- Retained volumes
- Effective degrees of freedom
- ROC-AUC
- Log loss

**Predeclared central visualization.** Artifact-removal quality versus predictive performance, one point per specification, with the factor levels distinguishable.

Lower QC-FC must not be equated automatically with better biological validity. An aggressive strategy can reduce QC-FC by removing signal along with artifact, and the retained-degrees-of-freedom columns are reported alongside every QC-FC summary for this reason.

---

## 18. Pipeline-agreement analysis

### 18.1 Held-constant conditions

For the same ds000030 subjects, the following are held constant to the extent technically possible:

- Raw inputs
- Subject set
- Target template
- Spatial resolution
- Atlas
- Temporal filtering
- Confound regression
- Connectivity estimator
- Downstream classifier

Any condition that cannot be held exactly constant across the three software pipelines must be documented, with the residual difference described, before the agreement results are interpreted.

### 18.2 Manipulated factor

Preprocessing software: fMRIPrep, FSL, or AFNI.

### 18.3 Metrics

**Spatial.**

- Dice
- Jaccard
- Normalized mutual information
- Template correlation
- Jacobian summaries, where available
- Region-of-interest coverage

**Temporal.**

- Temporal signal-to-noise ratio
- Framewise-displacement differences
- DVARS differences
- Retained volumes
- Power spectra

**Connectome.**

- Intraclass correlation, ICC(3,1)
- Median intraclass correlation
- Proportion of edges above 0.75 intraclass correlation
- Matrix correlation
- Frobenius distance
- Bland-Altman limits of agreement
- Subject identifiability

Confidence intervals are required for central agreement estimates.

With approximately 20 subjects, downstream ROC-AUC comparison is exploratory and is reported as such.

---

## 19. Missingness, failures, and invalid specifications

- Common-subject analyses are primary for direct specification comparison.
- Maximum-available analyses are sensitivity analyses.
- Silent complete-case changes are prohibited.
- Missingness counts must be reported by pipeline, strategy, atlas, site, diagnosis, and reason.
- Invalid specifications remain in the specification ledger with their failure classification.
- Convergence failures remain visible in the reported results.
- Retry rules must be bounded and defined before large-scale execution begins.
- A failed model must not be replaced by a different model after performance inspection.
- No imputation of missing neuroimaging features may use test data.

---

## 20. Ethics, privacy, and bias

- All data are secondary research datasets. No new data are collected.
- Local copies of all data must remain outside the Git working tree.
- No attempt to re-identify participants is permitted under any circumstance.
- Data-use agreements and licenses govern all sharing. Redistribution is not performed unless the governing license explicitly permits it and the permission has been verified and recorded.
- Diagnostic labels are research labels. They are not clinical diagnoses, and this system does not produce clinical diagnoses.
- The system is not intended for clinical deployment and must not be deployed clinically.
- Site, sex, age, race and ethnicity where available, acquisition protocol, motion, and diagnostic ascertainment may all introduce bias into both performance and its attribution. These are reported as limitations rather than adjusted away.
- Group-performance and subgroup analyses must be interpreted cautiously when sample sizes are small; subgroup estimates with wide intervals must not be reported as differences.
- A biomarker prediction score must not be represented as medical advice.
- Only aggregate, disclosure-safe outputs may appear in public reports. No participant-level imaging, identifier, or reconstructable feature vector may be published.

---

## 21. Reporting framework

The final report will be structured around:

- TRIPOD+AI
- PROBAST+AI
- Transparent reporting of null and negative results
- Complete specification accounting, including every invalid and failed specification
- Dataset and model provenance
- Reproducibility from saved predictions and configuration hashes

No claim of compliance with TRIPOD+AI or PROBAST+AI will be made until the corresponding checklist has actually been completed and included with the manuscript.

---

## 22. Compute, storage, and spending limits

The project uses a local-first strategy. Full details are recorded in [computational_budget.md](computational_budget.md); the caps below are protocol-binding.

### 22.1 Spending

- Dataset purchase cap: $0
- Default cloud-spend authorization: $0 until the user explicitly approves cloud use

If cloud use is later approved:

- Conservative Spot ceiling: $300
- Conservative on-demand ceiling: $600
- Budget alerts required at 50%, 75%, 90%, and 100% of the approved ceiling
- No idle compute or storage
- No cloud GPU for fMRIPrep
- One resumable subject job per instance
- Resources stopped immediately after validation

### 22.2 Scope caps

- Exactly 384 core specifications
- At least 300 valid specifications required for project completion
- Maximum 20 subjects in the controlled full three-pipeline arm, unless amended before outcome inspection
- Optional ds000030 volumetric arm capped at 80 subjects
- Deep-learning analysis capped at five sentinel preprocessing configurations
- At most four deep-learning model families
- Five final seeds
- No full deep-learning replication on COBRE unless separately justified before viewing replication outcomes
- No raw COBRE reprocessing without an approved cost and scientific justification

### 22.3 Storage safeguards

- Download region-of-interest time series and phenotype tables before any NIfTI derivatives
- Do not download full datasets speculatively
- Do not begin full raw preprocessing without confirmed sufficient free storage
- Plan for at least 250 GB free before the controlled raw-processing work
- Temporary work directories may be deleted only after derivative validation and a recorded success
- Never commit imaging data, model weights, caches, or restricted files

---

## 23. Stop conditions and excluded scope

### 23.1 Stop conditions

Expansion of the study stops when all of the following are true:

- At least 300 valid specifications are complete
- The main ABIDE multiverse is complete
- One raw pipeline-agreement analysis is complete
- One independent schizophrenia replication is complete
- Linear and deep-learning comparisons are complete
- The QC-FC trade-off is quantified
- The primary variance attribution is stable
- One clean-clone reproduction succeeds
- The manuscript and the explorer are released

### 23.2 Excluded scope

The following are explicitly excluded from the current study:

- Diffusion MRI
- Structural cortical-thickness prediction
- Task fMRI
- Federated learning
- Foundation-model pretraining
- Multiple additional diseases
- Unregistered interpretability expansions
- UK Biobank or paid clinical datasets
- Hospital deployment
- Clinical decision support
- Real-time inference
- Large foundation-model training

Each of these requires a separate study with its own protocol. None may be added to this study by silent scope expansion.

---

## 24. Interpretation rules

The following interpretation rules are locked:

- A null or small dispersion result remains publishable and scientifically meaningful.
- A high best ROC-AUC does not override poor calibration, leakage concerns, site dependence, or instability.
- Deep learning is not declared superior on the basis of one seed or one split.
- Pipeline differences are not described as biological differences.
- Cross-diagnostic replication evaluates methodological influence and transportability. It does not evaluate transfer of an autism model to schizophrenia, and no such claim will be made.
- Observational associations do not establish causation.
- Failed external replication must be reported.
- Unexpected results trigger analysis and documentation, never post hoc rewriting of a hypothesis.

---

## 25. Related governance documents

- [data_usage.md](data_usage.md) — dataset governance, access, and acquisition checklist
- [computational_budget.md](computational_budget.md) — compute, storage, and spending controls
- [deviations.md](deviations.md) — protocol deviation log
- [citation_inventory.md](citation_inventory.md) — citation tracking and verification status
- [decisions/0001-study-design.md](decisions/0001-study-design.md) — dataset-role decision record
