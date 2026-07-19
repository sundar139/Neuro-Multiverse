# Manual QC checklist — one-subject preprocessing pilot (template)

This template is empty by design and authorizes nothing. Copy it **outside the
repository** before filling it in.

A completed checklist is external evidence. It must never be committed: it
carries an external data root, an opaque selection whose preimage is private,
and reviewer-identifying marks. Screenshots and pipeline reports stay outside
Git for the same reason. Only a sanitized aggregate — counts, accepted/rejected,
and an opaque evidence digest — may ever be quoted in a committed document.

## Run identity

| Field | Value |
| --- | --- |
| Dataset | ds000030 |
| Acquisition scope | ds000030_pilot_5_subjects |
| Subject selection reference (opaque, `ds000030-one-subject-selection-sha256:<64 hex>`) | |
| Raw-validation evidence reference | |
| Review completed at (UTC) | |
| Reviewer initials (kept outside Git) | |

Confirm before starting the review:

- [ ] No participant identifier has been written into this file
- [ ] No absolute external or private path has been written into this file
- [ ] No subject identifier has been entered into Git in any form
- [ ] No screenshot containing participant or private-path information will be committed
- [ ] Reviewer initials and date remain outside Git, or are reduced to a sanitized aggregate

## fMRIPrep

- [ ] Successful completion sentinel present
- [ ] Runtime and resource log present
- [ ] Expected output directories present
- [ ] Registration visually reviewed
- [ ] Brain extraction visually reviewed
- [ ] Susceptibility-correction assumptions reviewed and recorded
- [ ] Output space confirmed
- [ ] Voxel size and template noted
- [ ] Confound output present and noted
- [ ] Temporal length checked against the raw acquisition
- [ ] File naming checked against the expected convention
- [ ] Status: accepted / rejected
- [ ] Rejection reason (required if rejected)

## FSL

- [ ] Successful completion sentinel present
- [ ] Runtime and resource log present
- [ ] Expected output directories present
- [ ] Registration visually reviewed
- [ ] Brain extraction visually reviewed
- [ ] Susceptibility-correction assumptions reviewed and recorded
- [ ] Output space confirmed
- [ ] Voxel size and template noted
- [ ] Confound or nuisance-regressor output noted where applicable
- [ ] Temporal length checked against the raw acquisition
- [ ] File naming checked against the expected convention
- [ ] Status: accepted / rejected
- [ ] Rejection reason (required if rejected)

## AFNI (`afni_proc.py`)

- [ ] Successful completion sentinel present
- [ ] Runtime and resource log present
- [ ] Expected output directories present
- [ ] Registration visually reviewed
- [ ] Brain extraction (skull strip) visually reviewed
- [ ] Susceptibility-correction assumptions reviewed and recorded
- [ ] Output space confirmed
- [ ] Voxel size and template noted
- [ ] Confound or censoring output noted where applicable
- [ ] Temporal length checked against the raw acquisition
- [ ] File naming checked against the expected convention
- [ ] Status: accepted / rejected
- [ ] Rejection reason (required if rejected)

## Cross-pipeline review

- [ ] All three implementations ran on the same single subject and the same raw inputs
- [ ] Differences in output space, template, and voxel size are recorded rather than reconciled
- [ ] No claim of scientific result, pipeline agreement, or preprocessing success is made here
- [ ] Overall status: accepted / rejected
- [ ] Overall rejection reason (required if rejected)
