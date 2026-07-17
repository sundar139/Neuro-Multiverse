# Windows and WSL2 Environment Setup

Version: 1.0
Document date: 2026-07-17
Governing protocol: [preregistration.md](preregistration.md)

This document describes how to establish and verify the NeuroMultiverse development environment. It does not acquire data. Dataset acquisition is governed by [data_usage.md](data_usage.md) and requires the completed checklist there.

---

## 1. Split-stack architecture

The project deliberately splits responsibilities across two filesystems.

| Location | Holds | Rationale |
| --- | --- | --- |
| Windows repository (this working tree) | Git, VS Code, Python analysis, machine learning, statistical orchestration, quality-control utilities, documentation, tests, local dashboards, experiment configuration | Source is small, benefits from native tooling, and belongs in version control |
| WSL2 filesystem, `$HOME/neuromultiverse-data` | Raw BIDS datasets, large derivatives, fMRIPrep working directories, FSL processing, AFNI processing, container-mounted neuroimaging paths, FreeSurfer license | Neuroimaging workloads are I/O-bound and must not cross the Windows/Linux filesystem boundary |

Source code may remain on the Windows volume. Large neuroimaging data and container work directories live in WSL2. The two are kept separate on purpose.

### 1.1 Why data must not live under `/mnt/c`

**Running fMRIPrep against data under `/mnt/c` is prohibited by project policy.**

The `/mnt/c` mount is a network-style translation layer between the Linux VM and the Windows NTFS volume. It does not faithfully support the POSIX semantics that neuroimaging pipelines rely on: file locking, permission bits, symbolic links, inode behaviour, and case sensitivity all differ from a native Linux filesystem. Beyond correctness, per-file latency across the boundary is orders of magnitude worse than on the native ext4 volume, and pipelines that touch hundreds of thousands of intermediate files degrade from hours to days. Failures that arise this way are silent and intermittent, which is the worst possible property for a study whose entire subject is analytic variability.

Windows may access WSL2 outputs through `\\wsl$\` when necessary — for example to open a derivative in a Windows viewer. That path is for reading results, not for running pipelines.

### 1.2 The data root is configurable

The future data root must never be hardcoded into source or committed as a user-specific absolute path. It will be supplied through configuration at the time data work begins. No junction or symbolic link into the Git repository is created.

### 1.3 Line endings

Shell scripts require LF line endings. `.gitattributes` enforces LF repository-wide and pins `.ps1`/`.bat`/`.cmd` to CRLF. A `.sh` file checked out with CRLF fails under `bash` with an opaque `\r: command not found`. Do not defeat this by changing `core.autocrlf` locally.

### 1.4 Secrets and licenses

Secrets and licenses remain outside Git. See [security.md](security.md).

---

## 2. Verified environment on the reference machine

Recorded 2026-07-17. These are **measurements from this machine**, not requirements, and not claims about any other machine.

| Component | Status | Evidence |
| --- | --- | --- |
| Windows | Windows 11 Home, build 26200, 64-bit | `Get-CimInstance Win32_OperatingSystem` |
| CPU | AMD Ryzen 9 8945HS, 8 cores / 16 threads | `Get-CimInstance Win32_Processor` |
| Memory | ~32 GB total | `Get-CimInstance Win32_OperatingSystem` |
| Windows Python | 3.11.9 | `py -3.11 --version` |
| Project environment | `.venv`, Python 3.11.9 | `.venv\Scripts\python.exe --version` |
| WSL2 distribution | Ubuntu 24.04.4 LTS, kernel 6.18.33.1-microsoft-standard-WSL2, default distribution, version 2 | `wsl --list --verbose` |
| WSL2 processors | 8 logical processors | `wsl -d Ubuntu-24.04 -- nproc` |
| WSL2 memory | ~23 GiB visible (24 GB configured ceiling) | `wsl -d Ubuntu-24.04 -- free -h` |
| WSL2 swap | 16 GiB | `wsl -d Ubuntu-24.04 -- swapon --show` |
| WSL2 free storage | ~928 GB free on `/` | `df -h /` |
| NVIDIA driver | 610.47, CUDA UMD 13.3 | `nvidia-smi` |
| GPU | NVIDIA GeForce RTX 4070 Laptop GPU, 8 GB | `nvidia-smi` |
| GPU from WSL2 | Visible (NVIDIA-SMI 610.43.02, CUDA UMD 13.3) | `wsl -d Ubuntu-24.04 -- nvidia-smi` |
| PyTorch | 2.13.0+cu130, CUDA build 13.0, `cuda_available` true | see Section 6 |
| Docker | Client 29.5.3, Engine 29.5.3, Docker Desktop 4.77.0, `linux/amd64` | `docker version` |
| Docker from WSL2 | Integrated and reachable | `wsl -d Ubuntu-24.04 -- docker version` |
| Windows R | 4.6.1 (UCRT, 64-bit) | `Rscript --version` |
| WSL2 R (AFNI) | 4.6.1, `R_LIBS=$HOME/R` | `wsl -d Ubuntu-24.04 -- Rscript --version` |
| renv | 1.2.3, bare project lock | `Rscript -e "renv::status()"` |
| FSL | 6.0.7.22 (`$HOME/fsl`) | `wsl -d Ubuntu-24.04 -- cat "$FSLDIR/etc/fslversion"` |
| AFNI | 26.2.01 (linux_ubuntu_24_64, Jul 6 2026) | `wsl -d Ubuntu-24.04 -- afni -ver` |
| FreeSurfer license | Present at `$HOME/licenses/license.txt`, mode 600 | `wsl -d Ubuntu-24.04 -- stat -c '%a' "$HOME/licenses/license.txt"` |

Ubuntu 24.04 is the approved neuroimaging distribution; no other Ubuntu distribution is used for FSL or AFNI. FSL and AFNI append their bin directories to `PATH` from more than one shell startup file, so the environment can carry duplicate `PATH` entries. This is non-blocking: verification resolves tools by command lookup rather than requiring a unique `PATH` entry.

The whole toolchain is re-verifiable non-destructively with `scripts/verify_system.ps1` (Windows) and `scripts/verify_neuroimaging.sh` (WSL2). Neither installs, upgrades, or reconfigures anything.

---

## 3. Required software categories

- **Version control and editor.** Git, VS Code.
- **Python analysis runtime.** CPython 3.11 on Windows, plus this repository's `.venv`.
- **GPU compute.** NVIDIA driver on Windows, CUDA-enabled PyTorch inside `.venv`. WSL2 inherits the Windows driver; do not install a driver inside the distribution.
- **Linux userspace.** WSL2 with an Ubuntu distribution, for neuroimaging tooling.
- **Containers.** Docker Desktop with WSL2 integration, for fMRIPrep.
- **Neuroimaging tools.** FSL and AFNI inside WSL2, for the pipeline-agreement analysis.
- **FreeSurfer license.** Required by fMRIPrep even when surface reconstruction is disabled.
- **Statistical environment.** R and `renv`, for variance attribution.

---

## 4. Repository and data locations

- Repository: this working tree, on the Windows volume.
- Data root: `$HOME/neuromultiverse-data` inside WSL2. **Not created yet** — it is created when data acquisition begins, under the governance in [data_usage.md](data_usage.md).
- FreeSurfer license: `$HOME/licenses/license.txt` inside WSL2, outside the repository.

---

## 5. Python environment

### 5.1 Activate the project environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If activation is blocked by execution policy, either run the interpreter directly (`.\.venv\Scripts\python.exe`) or start the session with `powershell -ExecutionPolicy Bypass`. Do not change the machine-wide execution policy for this project.

### 5.2 Recreate the environment from scratch

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 5.3 Select the environment in VS Code

The repository ships `.vscode/settings.json`, which points `python.defaultInterpreterPath` at `${workspaceFolder}/.venv/Scripts/python.exe`. VS Code normally picks this up automatically. If it does not:

1. Open the Command Palette.
2. Run `Python: Select Interpreter`.
3. Choose the interpreter inside `.venv`.

The workspace configuration is project-local. It does not modify global VS Code settings.

### 5.4 Verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

---

## 6. GPU validation

The PyTorch wheel index depends on the local NVIDIA driver, so the install command must be read from the official PyTorch source at install time and never copied from an older document.

- **Authoritative source:** the PyTorch installation selector at <https://pytorch.org/get-started/locally/>, cross-checked against the wheel index at <https://download.pytorch.org/whl/>.
- **Verification date:** 2026-07-17.
- **Resolved on this machine:** the CUDA 13.0 index `https://download.pytorch.org/whl/cu130` resolved `torch==2.13.0+cu130` for Python 3.11 on Windows. The local driver reports CUDA UMD 13.3, which runs the CUDA 13.0 build.

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.13.0+cu130 --index-url https://download.pytorch.org/whl/cu130
```

`torchvision` is deliberately not installed. This project has no computer-vision requirement, no source imports it, and it pulls in Pillow for nothing. Install it only when a concrete implemented need appears.

Re-verify the index against the official source before reinstalling; wheel availability changes over time. The exact resolved versions are recorded in `requirements-gpu-lock.txt`.

Validate:

```powershell
.\.venv\Scripts\python.exe -c "import torch; assert torch.cuda.is_available(); print(torch.__version__); print(torch.version.cuda); print(torch.cuda.get_device_name(0))"
```

`torch.cuda.is_available()` must return `True`. A CPU-only build that reports `False` means the install fell back to PyPI; reinstall with the index URL.

---

## 7. WSL2 validation

```powershell
wsl --status
wsl --list --verbose
wsl -d Ubuntu-24.04 -- uname -a
wsl -d Ubuntu-24.04 -- bash -lc 'df -h /'
wsl -d Ubuntu-24.04 -- bash -lc 'free -h'
wsl -d Ubuntu-24.04 -- nvidia-smi
```

The distribution must report version 2. The GPU must appear in `nvidia-smi` inside the distribution; this works through the Windows driver, and installing an NVIDIA driver inside WSL2 breaks it.

---

## 8. Docker validation

```powershell
docker version
docker info
wsl -d Ubuntu-24.04 -- bash -lc 'docker version'
```

The Windows client and the Linux server must both report a version. If the client prints a version but the command then fails to connect, Docker Desktop is installed but not running.

For Docker to work inside the distribution, WSL2 integration must be enabled in Docker Desktop settings for that specific distribution. A `docker` binary that resolves to `/mnt/c/Program Files/Docker/...` and then reports that the command could not be found in the distribution indicates the shim is on `PATH` but integration is off.

A `docker run hello-world` validation is appropriate once Docker is running and the image is available locally.

---

## 9. R validation

```powershell
Rscript --version
Rscript -e "cat(R.version.string, '\n')"
Rscript -e "renv::status()"
```

Schema validation of the lockfile uses `renv::lockfile_validate` with **named** arguments; the positional single-string form passes the lockfile as the `project` and does not validate the schema:

```powershell
Rscript -e "invisible(renv::load('.')); stopifnot(isTRUE(renv::lockfile_validate(project='.', lockfile='renv.lock', error=TRUE, verbose=TRUE)))"
```

`renv::load('.')` puts the project `renv` library — which carries the `jsonvalidate` and `V8` schema-validation packages — on the library path. The full R-environment validity contract (lock readable, R version matches runtime, `renv` record present, status consistent, schema valid) is enforced by `scripts/verify_system.ps1`; see [reproducibility.md](reproducibility.md). The tracked `renv` bootstrap and settings files are covered by pre-commit; only the ignored runtime libraries and caches stay out of version control.

Note: a bare `R` in PowerShell resolves to the `Invoke-History` alias, not the R language. Always use `Rscript`, or `where.exe R`, when testing for R on Windows.

---

## 10. FSL and AFNI validation

Both run inside WSL2, not on Windows.

```powershell
wsl -d Ubuntu-24.04 -- bash -lc 'command -v flirt && flirt -version'
wsl -d Ubuntu-24.04 -- bash -lc 'command -v afni_system_check.py && afni_system_check.py -check_all'
```

---

## 11. FreeSurfer license placement

fMRIPrep requires a FreeSurfer license file even when surface reconstruction is disabled with `--fs-no-reconall`.

Placement rules:

- Location: `$HOME/licenses/license.txt` inside WSL2.
- The license lives **outside the repository**. The repository ignore rules exclude `license.txt` as a defence in depth, but the file must not be placed in the working tree at all.
- Permissions: readable only by the owner.

```bash
mkdir -p "$HOME/licenses"
chmod 700 "$HOME/licenses"
# place license.txt into that directory, then:
chmod 600 "$HOME/licenses/license.txt"
```

Verify existence and permissions **without reading the contents**:

```bash
stat -c "%a %U %G %n" "$HOME/licenses/license.txt"
```

Never print, echo, copy into a report, paste into a chat, hash into a public document, or commit the license contents. See [security.md](security.md).

---

## 12. Verifying each prerequisite

| Prerequisite | Verification command | Expected result |
| --- | --- | --- |
| Windows Python 3.11 | `py -3.11 --version` | `Python 3.11.x` |
| Project environment | `.\.venv\Scripts\python.exe --version` | `Python 3.11.x` |
| Repository gates | `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` | `RESULT: PASS` |
| GPU driver | `nvidia-smi` | Driver version and GPU listed |
| GPU in PyTorch | `.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"` | `True` |
| WSL2 | `wsl --list --verbose` | Distribution listed at version 2 |
| GPU in WSL2 | `wsl -d Ubuntu-24.04 -- nvidia-smi` | GPU listed |
| Docker | `docker info` | Server section present |
| Docker in WSL2 | `wsl -d Ubuntu-24.04 -- bash -lc 'docker version'` | Client and Server both listed |
| R | `Rscript --version` | R version printed |
| renv | `Rscript -e "renv::status()"` | Status printed without error |
| FSL | `wsl -d Ubuntu-24.04 -- bash -lc 'flirt -version'` | FSL version printed |
| AFNI | `wsl -d Ubuntu-24.04 -- bash -lc 'afni_system_check.py -check_all'` | Check summary printed |
| FreeSurfer license | `wsl -d Ubuntu-24.04 -- bash -lc 'stat -c "%a" "$HOME/licenses/license.txt"'` | `600` |
| WSL2 storage | `wsl -d Ubuntu-24.04 -- bash -lc 'df -h /'` | At least 250 GB free before raw processing |
