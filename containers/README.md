# Container Version Locking

Governing documents: [../docs/reproducibility.md](../docs/reproducibility.md), [../docs/preregistration.md](../docs/preregistration.md)

The pipeline-agreement analysis compares fMRIPrep, FSL, and AFNI on identical raw inputs. That comparison is only meaningful if the software versions are pinned exactly: an unpinned image silently changes what is being compared, and would turn a software-agreement result into an artifact of when it happened to run.

---

## 1. Current state

**No container version or digest is recorded, and the container-lock control is incomplete.**

Docker Desktop is installed on this machine, but the daemon is not running and WSL2 integration is not enabled for the Ubuntu distribution, so no image could be inspected. No image has been pulled.

`fmriprep.version`, `fmripost_aroma.version`, and `checksums.txt` are deliberately absent. Creating them now would mean inventing a version and a digest, which is a fabrication and is prohibited by the protocol. They will be created only when real values can be read from an actual local image.

## 2. Why digests rather than tags

A tag is a mutable pointer. `nipreps/fmriprep:24.1.1` can be repointed to different content, so a tag records an intention, not an identity. An immutable digest (`sha256:...`) names exact content and is the only pin that supports the reproducibility claim this study needs.

## 3. Recording procedure

Once Docker is running and an image has been obtained manually:

```powershell
docker images --digests
```

Then record, per tool, in `<tool>.version`:

- Tool name
- Human-readable version
- Full image reference
- Immutable digest
- Verification date
- Verification command used

and collect the digests in `checksums.txt`.

Images are pulled deliberately by the user, never automatically by tooling, because a pull is a network fetch of several gigabytes with licensing implications.

## 4. Scope boundary

This directory records versions. It does not run research preprocessing. Container work directories live on the WSL2 filesystem under the data root, never in this repository and never under `/mnt/c`; see [../docs/setup_windows.md](../docs/setup_windows.md).

Built or pulled image layers are never committed here.
