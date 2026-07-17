# Computational Budget and Resource Controls

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

This document records the binding compute, storage, and spending controls for the NeuroMultiverse study. No compute has been executed and no resource has been purchased at the time of writing. All figures below are authorizations and caps, not measurements.

---

## 1. Local-first decision

The study is executed on local hardware by default. Cloud resources are not used unless the user explicitly approves them in advance for a named workload.

Rationale: the core multiverse operates on region-of-interest time series and connectivity matrices, which are small relative to volumetric imaging, and the controlled raw-preprocessing arm is deliberately capped at a subject count that local hardware can absorb. Local execution also removes the egress, idle-resource, and credential-handling risks that dominate small cloud budgets.

---

## 2. Spending authorization

| Control | Authorized value |
| --- | --- |
| Dataset purchase budget | $0 |
| Default cloud-spend authorization | $0 until the user explicitly approves cloud use |
| Conservative Spot ceiling, if cloud use is later approved | $300 |
| Conservative on-demand ceiling, if cloud use is later approved | $600 |

The Spot and on-demand ceilings are **conditional authorizations**. They take effect only after the user explicitly approves cloud use for a named workload. Until that approval exists, the effective cloud budget is $0.

No paid resource of any kind may be provisioned without explicit prior user approval recorded in the repository.

---

## 3. Cost-control rules for approved cloud use

If, and only if, cloud use is approved:

- Budget alerts are configured at 50%, 75%, 90%, and 100% of the approved ceiling before the first instance is launched.
- No idle compute and no idle storage. Resources are stopped immediately after derivative validation completes.
- No cloud GPU is used for fMRIPrep. fMRIPrep is CPU-bound and a GPU instance would be paid for and not used.
- One resumable subject job per instance, so that an interruption costs one subject rather than a batch.
- Object storage is emptied once derivatives are validated and retained locally.
- Credentials are never committed and never written into the repository.

### 3.1 Price information

No cloud prices are quoted in this document.

Cloud instance and storage prices are mutable, region-specific, and change without notice. Any price used in a future decision must be recorded with the date checked, the region, the authoritative source, and a warning that the price must be re-verified immediately before purchase. A price recorded in this repository is a snapshot of a past observation and is never a permanent fact.

---

## 4. Stop-loss rules

Execution halts and the user is consulted when any of the following occur:

- Cumulative approved spend reaches 90% of the authorized ceiling.
- A workload exceeds its predeclared wall-clock budget by more than a factor of two.
- Free storage on the working volume falls below the reserve required by Section 5.
- A resource is discovered running without an active workload attached to it.
- Any cost is incurred that was not covered by an explicit prior approval.

Reaching a stop-loss condition is a reason to consult the user, never a reason to reduce scientific scope silently. A scope reduction taken for compute reasons is a protocol deviation and must be recorded in [deviations.md](deviations.md).

---

## 5. Storage assumptions and safeguards

All storage figures below are **estimates and planning reserves, not verified dataset sizes**. Actual dataset sizes must be read from the authoritative source before acquisition, per [data_usage.md](data_usage.md).

| Control | Value | Nature |
| --- | --- | --- |
| Free space required before controlled raw-processing work | At least 250 GB | Planning reserve, not a measurement |
| Acquisition order | Region-of-interest time series and phenotype tables first; NIfTI derivatives only afterward | Binding rule |
| Speculative downloads | Prohibited | Binding rule |
| Raw preprocessing without confirmed free storage | Prohibited | Binding rule |
| Temporary work directory deletion | Permitted only after derivative validation and a recorded success | Binding rule |
| Committing imaging data, model weights, caches, or restricted files | Prohibited | Binding rule |

---

## 6. Scope caps

These caps are protocol-binding and duplicate the authoritative statement in the protocol, Section 22.2.

| Cap | Value |
| --- | --- |
| Core specifications | Exactly 384 |
| Valid specifications required for completion | At least 300 |
| Subjects in the controlled full three-pipeline arm | Maximum 20, unless amended before outcome inspection |
| Optional ds000030 volumetric cohort | Maximum 80 subjects |
| Deep-learning sentinel preprocessing configurations | Maximum 5 |
| Deep-learning model families | Maximum 4 |
| Final seeds per deep-learning family per sentinel configuration | 5 |
| Full deep-learning replication on COBRE | Not performed unless separately justified before viewing replication outcomes |
| Raw COBRE reprocessing | Not performed without an approved cost and scientific justification |

The optional ds000030 volumetric arm uses `--fs-no-reconall`, which removes surface reconstruction from the workload. This is a compute decision with a scientific consequence: no surface-based derivative is available from that arm, and none is claimed.

---

## 7. Resource accounting requirements

Every future execution must log, per unit of work:

- CPU time
- GPU time
- Peak memory
- Storage consumed and storage released
- Wall-clock time

Deep-learning runs must additionally report parameter counts and GPU-hour accounting per model family, per sentinel configuration, per seed, as required by the protocol, Section 10.3.

### 7.1 Estimates versus measurements

Estimates and measurements must be recorded in separate fields and never merged. A planning estimate is labeled as an estimate at the point of use. A measurement is labeled with the hardware, the software version, and the date on which it was taken. This document currently contains only estimates and authorizations, because no workload has been executed.

---

## 8. Approval requirements

Explicit prior user approval, recorded in the repository, is required before:

- Provisioning any paid compute or storage resource
- Acquiring any dataset that is not free
- Initiating the COBRE raw reprocessing arm
- Initiating the ds000030 volumetric cohort arm
- Extending the deep-learning analysis beyond the frozen sentinel configurations, model families, or seed count
- Any action whose cost is not covered by an authorization already recorded in this document
