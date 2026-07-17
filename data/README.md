# Tracked Data Area

Governing documents: [../docs/data_usage.md](../docs/data_usage.md), [../docs/preregistration.md](../docs/preregistration.md)

**No imaging data live in Git. None ever will.**

This directory is tracked only so that small, disclosure-safe manifests have a reviewed home. Everything else under it is excluded by the repository ignore rules.

---

## 1. What belongs here

`manifests/` — small, disclosure-safe tabular files that record *which* subjects, specifications, and splits an analysis used, so that a result can be regenerated and audited.

Nothing else. This area is not a cache, not a staging directory, and not a scratch space.

## 2. What never belongs here

- Raw imaging in any format
- Derivatives, connectomes, or feature matrices
- Model weights or checkpoints
- Archives of any dataset
- Phenotype tables obtained from a data provider
- Anything covered by a data-use agreement that restricts redistribution

The ignore rules exclude `data/raw/`, `data/derivatives/`, `data/interim/`, and `data/features/`, and exclude imaging, array, and model-weight formats repository-wide. Both verification scripts fail if any such path becomes tracked.

## 3. Where the real data live

Raw data and derivatives live outside the repository, on the WSL2 filesystem under `$HOME/neuromultiverse-data`, per the split-stack architecture in [../docs/setup_windows.md](../docs/setup_windows.md). That location is configuration, not a hardcoded constant, and no junction or symbolic link into this repository is created.

**No dataset has been acquired.** Acquisition requires the completed checklist in [../docs/data_usage.md](../docs/data_usage.md).

## 4. Requirements for future manifests

Each manifest must:

- Be small and human-reviewable, and remain far below the 1 MB pre-commit threshold.
- Carry a version identifier, so a result can name the exact manifest it used.
- Record only provider-issued research identifiers. **No participant identifier beyond the provider-issued research identifier may appear** — no name, no date of birth, no scan date, no site-local identifier, no free-text note, and no value that could narrow a participant to an individual in combination with the rest of the row.
- Contain **no absolute local path**. A path such as `C:\Users\...` or `/home/<user>/...` is machine-specific, is not reproducible on any other machine, and leaks a username. Manifests reference data by relative path or by dataset-relative identifier, resolved against the configured data root at run time.
- Be reproducible from the recorded seed and selection rule, per the protocol.
- Contain no imaging content and no feature values.

Manifests are the audit trail that connects a published number back to the subjects behind it. They are the one thing in this directory worth versioning, which is exactly why they must stay disclosure-safe.
