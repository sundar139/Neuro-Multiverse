#!/usr/bin/env bash
# Neuroimaging toolchain verification for the NeuroMultiverse project, runnable
# inside the Ubuntu 24.04 WSL2 distribution.
#
# This script VERIFIES an already-installed environment. It never installs,
# upgrades, repairs, or reconfigures software, and it never runs a research
# workload: no dataset, no preprocessing, no modelling. It reads only tool
# versions, resource ceilings, and metadata.
#
# It contains no user-specific absolute path and no username. All host-specific
# locations are derived at runtime from $HOME, $FSLDIR, and the script's own
# location. Portable references such as "$HOME/fsl" and "$HOME/R" describe the
# expected layout without recording whose home directory it is.
#
# The environment loads FSL and AFNI from shell startup files that may append
# their bin directories to PATH more than once. Duplicate PATH entries are
# harmless: every check below resolves commands with `command -v` rather than
# asserting a unique PATH entry, so repeated shell loading does not fail it.
#
# Usage (from inside Ubuntu 24.04):
#     bash scripts/verify_neuroimaging.sh

set -euo pipefail

# --- Expected measurements on the approved reference machine -----------------
readonly EXPECT_FSL_VERSION='6.0.7.22'
readonly EXPECT_AFNI_VERSION='AFNI_26.2.01'
readonly MIN_CPU=8
readonly MIN_MEM_GIB=22
readonly MIN_SWAP_GIB=12
readonly MIN_DISK_GB=250

# --- Repository root, resolved from this script's own location ---------------
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

# --- Load the user profile without letting set -e abort on it ----------------
# FSL's fslconf/fsl.sh ends on a conditional that returns nonzero when optional
# site configs are absent, which is normal. Sourcing it under `set -e` would
# otherwise kill this script, so the profile is loaded with errexit relaxed.
set +e
# shellcheck disable=SC1090
. "${HOME}/.profile" >/dev/null 2>&1 || true
set -e

# The AFNI statistical toolchain uses its own R library (R_LIBS=$HOME/R) and is
# deliberately independent of the project's Windows renv environment. When R is
# started with the repository as its working directory, the project .Rprofile
# would activate renv and mask that AFNI library. Disabling the renv autoloader
# keeps every R check below pointed at the real AFNI environment being verified.
export RENV_CONFIG_AUTOLOADER_ENABLED=FALSE

# --- Git working-tree state, captured before any check runs ------------------
git_available=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_available=1
fi

porcelain_state() {
    [ "${git_available}" -eq 1 ] || return 1
    git status --porcelain=v1 --untracked-files=all 2>/dev/null
}

initial_state=""
if [ "${git_available}" -eq 1 ]; then
    initial_state="$(porcelain_state)"
fi

# --- Gate bookkeeping --------------------------------------------------------
declare -a gate_names=()
declare -a gate_results=()
failures=0

run_gate() {
    local name="$1"
    shift
    echo
    echo "--- ${name} ---"
    if "$@"; then
        gate_names+=("${name}")
        gate_results+=("PASS")
    else
        gate_names+=("${name}")
        gate_results+=("FAIL")
        failures=$((failures + 1))
    fi
}

require_cmd() {
    # Resolve each named command through PATH; tolerant of duplicate entries.
    local ok=0 missing="" c
    for c in "$@"; do
        if command -v "${c}" >/dev/null 2>&1; then
            echo "  ${c}: $(command -v "${c}")"
        else
            echo "  ${c}: NOT FOUND"
            missing="${missing} ${c}"
            ok=1
        fi
    done
    [ -z "${missing}" ] && return 0
    echo "  missing:${missing}"
    return "${ok}"
}

# --- Individual checks -------------------------------------------------------
check_distro() {
    local id ver
    id="$(. /etc/os-release && echo "${ID:-}")"
    ver="$(. /etc/os-release && echo "${VERSION_ID:-}")"
    echo "  distribution: ${id} ${ver}"
    [ "${id}" = "ubuntu" ] && [ "${ver}" = "24.04" ] && return 0
    echo "  expected ubuntu 24.04"
    return 1
}

check_cpu() {
    local n
    n="$(nproc)"
    echo "  logical processors: ${n} (require >= ${MIN_CPU})"
    [ "${n}" -ge "${MIN_CPU}" ]
}

check_mem() {
    local kib gib
    kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    gib=$((kib / 1048576))
    echo "  total memory: ~${gib} GiB (require >= ${MIN_MEM_GIB} GiB, configured 24 GB ceiling)"
    [ "${gib}" -ge "${MIN_MEM_GIB}" ]
}

check_swap() {
    local kib gib
    kib="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
    gib=$((kib / 1048576))
    echo "  swap: ~${gib} GiB (require >= ${MIN_SWAP_GIB} GiB)"
    [ "${gib}" -ge "${MIN_SWAP_GIB}" ]
}

check_disk() {
    local avail_kb gb
    avail_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
    gb=$((avail_kb / 1024 / 1024))
    echo "  free space on /: ~${gb} GB (require >= ${MIN_DISK_GB} GB)"
    [ "${gb}" -ge "${MIN_DISK_GB}" ]
}

check_docker() {
    require_cmd docker || return 1
    if ! docker version --format 'client={{.Client.Version}} server={{.Server.Version}}' 2>/dev/null; then
        echo "  docker client present but server unreachable from this distribution"
        return 1
    fi
    docker info >/dev/null 2>&1 || { echo "  docker info failed"; return 1; }
    echo "  docker engine reachable from Ubuntu 24.04"
}

check_nvidia() {
    require_cmd nvidia-smi || return 1
    nvidia-smi -L || return 1
}

check_fsl() {
    [ -n "${FSLDIR:-}" ] || { echo "  FSLDIR is not set"; return 1; }
    [ -d "${FSLDIR}" ] || { echo "  FSLDIR does not exist: ${FSLDIR}"; return 1; }
    echo "  FSLDIR: ${FSLDIR}"
    local ver
    ver="$(cat "${FSLDIR}/etc/fslversion" 2>/dev/null | cut -d: -f1)"
    echo "  FSL version: ${ver} (expect ${EXPECT_FSL_VERSION})"
    [ "${ver}" = "${EXPECT_FSL_VERSION}" ] || return 1
    require_cmd flirt fslhd fslmaths mcflirt feat
}

check_afni() {
    require_cmd afni afni_proc.py 3dTproject 3dvolreg 3dmaskave 3dMVM rPkgsInstall || return 1
    local ver
    ver="$(afni -ver 2>/dev/null)"
    echo "  ${ver}"
    printf '%s' "${ver}" | grep -Fq "${EXPECT_AFNI_VERSION}" || {
        echo "  expected ${EXPECT_AFNI_VERSION}"
        return 1
    }
}

check_r_libs() {
    echo "  R_LIBS: ${R_LIBS:-<unset>} (expect \$HOME/R)"
    [ "${R_LIBS:-}" = "${HOME}/R" ]
}

check_afni_rpkgs() {
    Rscript -e '
        required <- c("afex","phia","snow","lme4","lmerTest","gamm4",
                      "data.table","paran","psych","brms","corrplot","metafor")
        missing <- setdiff(required, rownames(installed.packages()))
        if (length(missing)) {
            cat("  missing R packages:", paste(missing, collapse=", "), "\n")
            quit(status = 1)
        }
        cat("  all required AFNI R packages present\n")
    '
}

check_3dmvm() {
    3dMVM -help >/dev/null 2>&1 && echo "  3dMVM -help succeeded"
}

check_rpkgsinstall() {
    rPkgsInstall -pkgs ALL -check >/dev/null 2>&1 && echo "  rPkgsInstall -pkgs ALL -check succeeded"
}

check_afni_system() {
    # The AFNI system check does not report failure through its exit code, so
    # its output is classified explicitly. The temporary log holds machine
    # paths and is removed on exit; it is never committed.
    local log
    log="$(mktemp)"
    # shellcheck disable=SC2064
    trap "rm -f '${log}'" RETURN
    afni_system_check.py -check_all >"${log}" 2>&1 || true
    if ! grep -Fq 'nothing to fix, yay!' "${log}"; then
        echo "  success phrase 'nothing to fix, yay!' not found"
        return 1
    fi
    if grep -Eq 'FAILURE|missing R packages|summary, please fix' "${log}"; then
        echo "  blocking pattern present in AFNI system check output"
        grep -Ei 'FAILURE|missing R packages|summary, please fix' "${log}" | sed 's/^/    /'
        return 1
    fi
    echo "  AFNI system check: nothing to fix, yay!"
}

check_license() {
    # Existence and mode only. The license contents are never read, printed,
    # copied, or hashed.
    local lic="${HOME}/licenses/license.txt"
    [ -f "${lic}" ] || { echo "  FreeSurfer license not found at \$HOME/licenses/license.txt"; return 1; }
    local mode
    mode="$(stat -c '%a' "${lic}")"
    echo "  FreeSurfer license present at \$HOME/licenses/license.txt, mode ${mode}"
    [ "${mode}" = "600" ]
}

check_git_diff() {
    [ "${git_available}" -eq 1 ] || { echo "  git not available"; return 1; }
    git diff --check || { echo "  git diff --check reported problems"; return 1; }
    echo "  no whitespace errors or conflict markers in the working diff"
}

check_tree_stability() {
    [ "${git_available}" -eq 1 ] || { echo "  git not available"; return 1; }
    local final_state
    final_state="$(porcelain_state)"
    if [ "${initial_state}" != "${final_state}" ]; then
        echo "  verification MODIFIED the working tree"
        return 1
    fi
    echo "  working tree unchanged by verification"
}

# --- Run every gate ----------------------------------------------------------
echo "=== NeuroMultiverse neuroimaging verification ==="
echo "Repository root: ${repo_root}"

run_gate 'Ubuntu 24.04'            check_distro
run_gate 'Logical processors'      check_cpu
run_gate 'Memory'                  check_mem
run_gate 'Swap'                    check_swap
run_gate 'Free storage'            check_disk
run_gate 'Docker from WSL'         check_docker
run_gate 'NVIDIA GPU from WSL'     check_nvidia
run_gate 'FSL'                     check_fsl
run_gate 'AFNI'                    check_afni
run_gate 'AFNI R library'          check_r_libs
run_gate 'AFNI R packages'         check_afni_rpkgs
run_gate '3dMVM help'              check_3dmvm
run_gate 'rPkgsInstall check'      check_rpkgsinstall
run_gate 'AFNI system check'       check_afni_system
run_gate 'FreeSurfer license'      check_license
run_gate 'Git diff check'          check_git_diff
run_gate 'Working-tree stability'  check_tree_stability

echo
echo "=== Summary ==="
for i in "${!gate_names[@]}"; do
    printf '%-28s %s\n' "${gate_names[$i]}" "${gate_results[$i]}"
done
echo
if [ "${failures}" -gt 0 ]; then
    echo "RESULT: FAIL (${failures} of ${#gate_names[@]} gates failed)"
    exit 1
fi
echo "RESULT: PASS (all ${#gate_names[@]} gates passed)"
exit 0
