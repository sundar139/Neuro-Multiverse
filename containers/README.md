# Container Version Locking

Governing documents: [../docs/reproducibility.md](../docs/reproducibility.md), [../docs/preregistration.md](../docs/preregistration.md)

The pipeline-agreement analysis compares fMRIPrep, FSL, and AFNI on identical raw inputs. That comparison is only meaningful if the software versions are pinned exactly: an unpinned image silently changes what is being compared, and would turn a software-agreement result into an artifact of when it happened to run.

---

## 1. Recorded images

Two images are pinned. The values below were read from the local images on this
machine on 2026-07-17 (UTC); they are measurements, not intentions.

| Tool | Application version | Tag | Architecture | OS |
| --- | --- | --- | --- | --- |
| fMRIPrep | 25.2.5 | `nipreps/fmriprep:25.2.5` | amd64 | linux |
| fMRIPost-AROMA | 0.0.12 | `nipreps/fmripost-aroma:0.0.12` | amd64 | linux |

Immutable digests:

- `nipreps/fmriprep@sha256:15cbf8dcd17440d26ff5e80e9f7313f1cb3c54f13673f1ec4aed4465e8e12d77`
- `nipreps/fmripost-aroma@sha256:06388c67ebb8a07b7f9a4ec065e7bcaf7ece0e03cdceee20b4d42a657c338668`

The per-tool detail lives in `fmriprep.version` and `fmripost_aroma.version`; the
digests are collected in `checksums.txt`. Each version file records the tool, the
application version, the image reference, the immutable digest, the image ID, the
architecture, the operating system, the verification date, and the exact
verification commands.

## 2. Why digests rather than tags

A tag is a mutable pointer. `nipreps/fmriprep:25.2.5` can be repointed to different
content, so a tag records an intention, not an identity. An immutable digest
(`sha256:...`) names exact content and is the only pin that supports the
reproducibility claim this study needs. Full digests are always recorded: never a
`latest`/`main`/`unstable` tag, never a shortened or Docker Hub UI-abbreviated
digest.

## 3. Re-verification

The recorded identities are re-checked against the live images by
`scripts/verify_system.ps1`, which fails if any application version, image ID,
architecture, operating system, or digest drifts from what the committed lock
files record. To re-verify by hand:

```powershell
docker run --rm nipreps/fmriprep:25.2.5 --version
docker image inspect nipreps/fmriprep:25.2.5 --format '{{.Id}} {{.Architecture}} {{.Os}}'
docker image inspect nipreps/fmriprep:25.2.5 --format '{{range .RepoDigests}}{{println .}}{{end}}'
```

Images are pulled deliberately by the user, never automatically by tooling, because
a pull is a network fetch of several gigabytes with licensing implications.

## 4. ICA-AROMA compatibility

`fMRIPost-AROMA` is locked to the versioned image and full digest above. It is a
post-processing step over fMRIPrep derivatives, so it requires compatible fMRIPrep
outputs: any future fMRIPrep run used for ICA-AROMA must write the
`MNI152NLin6Asym:res-02` standard-space derivatives that AROMA consumes.

Both fMRIPrep and fMRIPost-AROMA must be invoked with `--notrack` unless telemetry
has been explicitly approved and recorded, so that no run phones home by default.

ICA-AROMA remains a sensitivity analysis. It is not part of the core 384 universes,
and no ICA-AROMA execution has occurred: recording these images pins the toolchain,
it does not run it.

## 5. Scope boundary

This directory records versions. It does not run research preprocessing. Container work directories live on the WSL2 filesystem under the data root, never in this repository and never under `/mnt/c`; see [../docs/setup_windows.md](../docs/setup_windows.md).

Built or pulled image layers are never committed here.
