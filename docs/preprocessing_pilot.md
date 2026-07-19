# One-subject preprocessing pilot

## Standing

**Nothing has been preprocessed.** This document and the artifacts it describes
prepare a bounded one-subject pilot; they do not run it. fMRIPrep, FSL, and AFNI
remain unexecuted, no container has been run against raw data, and no derivative
exists.

Execution stays blocked until Rohith gives a separate, explicit authorization for
that unit. Readiness is not authorization: the gate below can report *ready to
prepare* while execution remains forbidden, and that is the intended state.

## What is prepared

| Artifact | Purpose |
| --- | --- |
| `src/neuromultiverse/preprocessing_readiness.py` | Fail-closed readiness gate and the accepted evidence identities it binds to |
| `scripts/prepare_preprocessing_pilot.py` | Deterministic preflight command; prints an aggregate decision and runs no pipeline |
| `configs/preprocessing/one_subject_pilot.template.yaml` | Disclosure-safe execution-plan template, filled outside Git |
| `configs/preprocessing/one_subject_qc_checklist.template.md` | Manual QC checklist template, completed outside Git |

Run the preflight from the repository root:

```powershell
& '.venv\Scripts\python.exe' scripts\prepare_preprocessing_pilot.py
```

It exits `0` when the later pilot may be prepared and `1` otherwise, printing
the blocking issues. It imports no process-spawning module, so it cannot start a
pipeline even by accident.

## Inputs the pilot may use

Only the already acquired and already validated ds000030 five-subject pilot,
scope `ds000030_pilot_5_subjects`: 22 files, 187,570,603 bytes, raw validation
completed with 0 errors, 139 warnings, and 0 ignored issues under BIDS Validator
3.0.0 and BIDS schema 1.2.4.

ABIDE and COBRE remain blocked. The approximately 20-subject controlled ds000030
subset remains unauthorized. No acquisition, reacquisition, or permission change
is part of this work.

## The gate

`evaluate_preprocessing_readiness` recomputes every accepted fact rather than
trusting how a governance record was constructed, so a record that drifts — or
one built past its own validation — still fails closed. It refuses unless:

- the dataset is `ds000030` and the scope is exactly `ds000030_pilot_5_subjects`;
- access is READY and the acquisition is both permitted and completed;
- the acquisition and raw-validation evidence references match the accepted
  receipts exactly;
- raw validation is completed with zero errors, zero ignored issues, and the
  accepted nonnegative warning count, whose per-code counts sum to that total;
- the validated file count and byte total match the validated pilot;
- the broader controlled subset is not asserted as authorized;
- any supplied subject selector is an opaque external reference.

The gate prints no raw path, no participant identifier, and no command line, and
it executes nothing.

## Naming the subject

A later unit processes one subject, identified only by an opaque external
reference:

```text
ds000030-one-subject-selection-sha256:<64 lowercase hex characters>
```

The preimage — which subject was selected — lives outside Git with the rest of
the private evidence. No selection has been made or generated here. A value
containing a path separator, whitespace, `@`, a home path, or anything shaped
like a BIDS subject entity is rejected.

## What must stay outside Git

Raw imaging data, derivatives, external manifests, receipts, validator output,
pipeline reports, screenshots, the selected subject identifier, absolute
external paths, the FreeSurfer license, Docker trust records, and every
completed QC checklist. Only aggregate, disclosure-safe summaries and opaque
digests are ever committed.

## What the later authorized unit must do

Run the same single subject through fMRIPrep, FSL, and AFNI `afni_proc.py` on
the same raw inputs, so any difference observed is attributable to the pipeline
rather than to the input.

Then inspect, per implementation: registration, brain extraction,
susceptibility-correction assumptions, output space, voxel size and template,
confound outputs where applicable, temporal length, file naming, and runtime and
resource usage. Record each in the QC checklist, outside Git.

## Evidence Rohith returns afterwards

- the opaque selection reference used;
- per-pipeline completion sentinel, runtime, and resource figures;
- the completed QC checklist, held outside Git, quoted here only as a sanitized
  aggregate and an opaque digest;
- accepted or rejected status per implementation, with a reason for any
  rejection.

## What this work does not claim

It claims no scientific result, no agreement between pipelines, and no
preprocessing success. It establishes only that a bounded one-subject pilot
could be prepared against accepted governance evidence, and that executing it
still requires a separate authorization.
