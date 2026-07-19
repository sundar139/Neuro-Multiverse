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

## Validating a filled plan

Fill a copy of `configs/preprocessing/one_subject_pilot.template.yaml` **outside**
the repository, then validate it without running anything:

```powershell
& '.venv\Scripts\python.exe' scripts\prepare_preprocessing_pilot.py --plan <external plan path>
```

Exit `0` means the plan is well formed and the accepted evidence still matches;
exit `1` means it was rejected and lists why. The validator reads only the plan
file. It never opens the FreeSurfer license, never lists an external root's
contents, and never echoes an external path into its output — a path appears in
the verdict only as a boolean about its shape.

Validation fails closed unless `authorizes_execution` is false, the dataset is
`ds000030` at scope `ds000030_pilot_5_subjects`, every accepted evidence
identity matches, the selection reference is a valid opaque digest recorded
outside Git, all three external roots are absolute and outside the repository,
output spaces and CPU/memory limits are explicitly filled for all three
pipelines, the fMRIPrep container reference and FreeSurfer license path are
declared, every claim is false, and no expansion, acquisition, ABIDE, COBRE, or
push authorization is asserted. A valid plan still authorizes nothing.

## Recording the subject selection

The selection is yours to make; this repository must never learn which subject
it is. Run the following **outside Git**, against the external pilot plan, and
return only the printed digest.

1. Choose the selection deterministically from the five acquired subjects using
   the project's frozen seed, so the choice is reproducible and not
   result-driven: order the five acquired subject identifiers lexicographically
   and take the one minimising
   `SHA256("20260717|ds000030|1.0.0|one-subject-pilot-v1|<subject id>")`.
   This mirrors the selection rule already used for the five-subject pilot, with
   its own version label, so it cannot collide with that earlier draw.
2. Write an external selection record at mode 600, outside Git, containing the
   selected identifier, the rule version, the seed, the source plan digest, and
   a UTC timestamp.
3. Compute the reference as the SHA-256 over the record's canonical JSON
   serialisation (`sort_keys=True`, `separators=(",", ":")`), matching how every
   other receipt digest in this project is derived.
4. Return only:

   ```text
   ds000030-one-subject-selection-sha256:<64 lowercase hex>
   ```

Print nothing else. The selected identifier must not reach stdout, a log, a
commit, a plan committed to Git, or a message to me. I have not run this
procedure, have not selected a subject, and cannot verify the digest's preimage
— by design, the gate checks only its shape.

## Output-space strategy — recommendation, not a decision

Choosing output spaces is a scientific decision, so the plan template leaves the
fields empty and validation only insists they be filled. Recording the rationale
before execution is what keeps the later comparison honest.

The comparison question is whether independent implementations agree given
identical raw inputs. That argues for **holding the target space fixed across
all three pipelines** and letting the pipelines differ only in how they get
there. If each tool writes to its own preferred template, any disagreement you
observe confounds the pipeline with the resampling target, and the result
becomes uninterpretable.

Two defensible options:

| Option | Setup | Trade-off |
| --- | --- | --- |
| Common target (recommended) | `MNI152NLin2009cAsym:res-2` for all three | Isolates pipeline effects; requires configuring FSL and AFNI to a non-default target, so some of the difference you measure is configuration effort, not tool behaviour |
| Native defaults | fMRIPrep `MNI152NLin2009cAsym`, FSL `MNI152NLin6Asym`, AFNI its default | Measures each tool as typically used; disagreement then mixes pipeline and template effects and needs a resampling stage before any comparison |

My recommendation is the common target at `MNI152NLin2009cAsym:res-2`, with the
native-default run recorded as a documented deviation if you later want the
as-typically-used view. But the protocol governs this, and it is your call —
tell me which you want and I will record it in the plan and the deviation log if
needed. Nothing in the code chooses for you.

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
