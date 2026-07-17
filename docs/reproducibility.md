# Reproducibility Controls

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

A result that cannot be regenerated is not evidence. This document records the mechanisms that make every future NeuroMultiverse result traceable to the code, dependencies, environment, and configuration that produced it.

---

## 1. Dependency locks

| File | Contents | How it is produced |
| --- | --- | --- |
| `pyproject.toml` | Declared dependency intent and version ranges. The Python source of truth. | Hand-authored |
| `requirements.in` | Runtime intent, referencing the package itself | Hand-authored |
| `requirements-dev.in` | Development intent | Hand-authored |
| `requirements-lock.txt` | Fully pinned resolution of runtime and development dependencies, including transitive packages | Generated, never hand-edited |
| `requirements-gpu-lock.txt` | Pinned PyTorch stack as actually installed | Generated from the installed environment |

### 1.1 Resolver command

```powershell
.\.venv\Scripts\python.exe -m piptools compile `
    --output-file=requirements-lock.txt `
    --strip-extras `
    --no-emit-index-url `
    requirements.in requirements-dev.in
```

`--no-emit-index-url` keeps machine-local index configuration out of the lock. Transitive versions are never hand-authored: they are resolved by installing and compiling, so the lock describes a resolution that actually happened.

### 1.2 Lock provenance

`requirements-lock.txt` was generated on 2026-07-17 with:

- Python 3.11.9 (CPython, Windows x86_64)
- pip 26.1.2
- pip-tools 7.5.3
- Windows 11 Home, build 26200

No machine-specific absolute path appears in either lock file. This is enforced by review and re-checked by the credential and path scans in the verification scripts.

### 1.3 GPU dependencies are locked separately

GPU-enabled PyTorch cannot be resolved from PyPI, because the correct wheel depends on the local NVIDIA driver. It is therefore installed from the official PyTorch index and pinned in `requirements-gpu-lock.txt` from the installed result. That file records the index URL, the driver version, the CUDA build, and the verification date. The install command must be re-read from the official PyTorch source before any reinstall rather than copied from documentation, because wheel availability changes over time.

---

## 2. Seed policy

The project-wide base seed is frozen at `20260717`. Derived seeds are generated deterministically from the base seed, dataset identifier, subject-manifest version, specification identifier, outer fold, inner fold, and replicate seed.

Python's built-in `hash()` is process-randomized for string inputs and must never be used for seed derivation; a stable digest is required. The authoritative statement of this policy is the protocol, Section 1.2. It is referenced here, not restated, so that a single source of truth governs.

---

## 3. Runtime provenance

`src/neuromultiverse/runtime.py` collects a machine-readable description of the environment that produced a result:

```powershell
.\.venv\Scripts\python.exe -m neuromultiverse.runtime --json
```

It records the package version, Python version and interpreter, operating system and architecture, Git commit and dirty state, the versions of every declared key package, the PyTorch and CUDA description when installed, and a UTC timestamp with stable field names.

It deliberately does not record environment-variable values, usernames, home-directory paths or contents, secrets, or any participant or dataset information. Paths under the user home are redacted to `~`. It performs no network access.

The module reports only what it inspected. It makes no claim about FSL, AFNI, or FreeSurfer, because it does not check them.

---

## 4. Git provenance

Every result must be attributable to a commit. The runtime record carries the commit hash and a dirty-state flag; a result produced from a dirty tree is marked as such and is not reproducible from the commit alone.

The scientific protocol was committed before any outcome modeling. That ordering is itself part of the evidence and is why history is never rewritten in this repository.

---

## 5. Environment verification

| Script | Role |
| --- | --- |
| `scripts/verify.ps1` | Primary Windows validation entry point |
| `scripts/verify.sh` | Source validation under WSL2 |

Both run the same gates: Python version, Ruff format, Ruff lint, mypy, pytest, the runtime metadata smoke test, pre-commit across tracked files, an oversized-file scan, a tracked-artifact scan, a credential scan, a `git diff --check` gate, and a working-tree stability gate. Both print a pass/fail summary and exit nonzero on failure. Neither installs packages or mutates an environment — a validator that changes what it validates cannot be trusted.

### 5.1 Working-tree stability

Several pre-commit hooks auto-fix files. That is useful during development and dangerous during validation: a run that reformats a file and then reports success is reporting a result it manufactured, and the green summary describes a tree that no longer matches what was reviewed.

Both scripts therefore capture the complete porcelain state, tracked and untracked, before any gate runs, and compare it after the last one. If validation changed anything, the stability gate fails and prints both states. Nothing is reverted automatically — silently undoing a change would hide the same problem from the other direction.

The gate checks that validation *introduced* no change, not that the tree started clean. Running against an intentionally dirty development tree is supported and passes, so long as validation leaves that tree exactly as it found it.

### 5.2 Toolchain alignment

The mypy pre-commit hook is pinned to the same release as the project lock, and its `additional_dependencies` are pinned to exact locked versions. A hook running a different mypy is a hook checking different rules: it can pass while the local gate fails, or fail while the local gate passes, and neither outcome tells you anything about the code. When the mypy pin in `requirements-lock.txt` moves, the hook `rev` and its dependency pins move with it.

---

## 6. Container digests

Container image versions and immutable digests will be recorded under `containers/` once the images have been obtained and inspected. A digest pins an exact image; a tag does not, because a tag can be repointed.

**No container version or digest is recorded yet**, because no image is present locally. Recording a version or digest that has not been read from an actual image would be a fabrication, so the container-lock control is currently incomplete. See `containers/README.md`.

---

## 7. R environment

Variance attribution runs in R, with `renv` pinning the R package set.

**No `renv.lock` exists yet**, because R is not installed on this machine. A lock file naming an R version that has never run here would be fabricated provenance, which is worse than an absent lock: it would assert reproducibility that had never been demonstrated. The R control is therefore recorded as incomplete rather than approximated. See the manual-prerequisite guidance in [setup_windows.md](setup_windows.md).

---

## 8. Estimates versus measurements

Estimates and measurements are recorded separately and never merged.

- A **measurement** is labeled with the hardware, software version, and date on which it was taken. The environment table in [setup_windows.md](setup_windows.md) and the lock provenance above are measurements.
- An **estimate** is labeled as an estimate at the point of use. The storage reserves in [computational_budget.md](computational_budget.md) are estimates.

The same discipline applies to dataset characteristics under [data_usage.md](data_usage.md): a planning assumption may appear only when labeled unverified, and it never authorizes acquisition.
