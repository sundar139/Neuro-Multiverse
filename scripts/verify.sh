#!/usr/bin/env bash
# Source validation for the NeuroMultiverse repository, runnable under WSL2.
#
# This script validates source; it never installs packages or mutates an
# environment. It exits nonzero when any gate fails.
#
# Scope note: this script may read the repository from /mnt/c because source
# code legitimately lives on the Windows volume. It must never write datasets,
# derivatives, or container work directories there. Project policy places all
# heavy neuroimaging work on the WSL2 filesystem; see docs/setup_windows.md.
#
# Usage:
#     bash scripts/verify.sh

set -euo pipefail

# Resolve the repository root from this script's location, never from a
# hardcoded user-specific path.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

# Keep tool caches inside the repository so they are ignored consistently.
export PRE_COMMIT_HOME="${repo_root}/.cache/pre-commit"

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

echo "=== NeuroMultiverse repository verification ==="
echo "Repository root: ${repo_root}"

if commit="$(git rev-parse HEAD 2>/dev/null)"; then
    if [ -z "$(git status --porcelain)" ]; then
        echo "Commit: ${commit} (clean)"
    else
        echo "Commit: ${commit} (dirty)"
    fi
else
    echo "Commit: unavailable (git not found or not a repository)"
fi

# Locate an interpreter. Prefer the Windows project environment when this
# repository is mounted from /mnt/c; otherwise fall back to a POSIX python3.
python_bin=""
if [ -x "${repo_root}/.venv/Scripts/python.exe" ]; then
    python_bin="${repo_root}/.venv/Scripts/python.exe"
elif [ -x "${repo_root}/.venv/bin/python" ]; then
    python_bin="${repo_root}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python_bin="$(command -v python3)"
else
    echo "FAIL: no Python interpreter found"
    exit 1
fi
echo "Interpreter: ${python_bin}"

check_python_version() {
    local version
    version="$("${python_bin}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    echo "  Interpreter reports: ${version}"
    case "${version}" in
        3.11.*) return 0 ;;
        *)
            echo "  expected Python 3.11.x, found ${version}"
            return 1
            ;;
    esac
}

check_runtime_metadata() {
    "${python_bin}" -m neuromultiverse.runtime --json | "${python_bin}" -c 'import json,sys; json.load(sys.stdin)'
    echo "  Runtime metadata emitted parsable JSON."
}

check_large_files() {
    local found=0
    while IFS= read -r file; do
        echo "  ${file}"
        found=$((found + 1))
    done < <(
        find . -type f -size +5M \
            -not -path './.git/*' \
            -not -path './.venv/*' \
            -not -path './renv/*' \
            -not -path './.cache/*' \
            -not -path '*/__pycache__/*' \
            -not -path './.mypy_cache/*' \
            -not -path './.ruff_cache/*' \
            -not -path './.pytest_cache/*' 2>/dev/null
    )
    if [ "${found}" -gt 0 ]; then
        echo "  ${found} file(s) exceed 5 MB outside ignored directories"
        return 1
    fi
    echo "  No file over 5 MB outside ignored directories."
}

check_tracked_artifacts() {
    local offenders
    offenders="$(git ls-files | grep -E '\.(nii|nii\.gz|h5|hdf5|npy|npz|pt|pth|ckpt|safetensors)$|(^|/)(data/raw|data/derivatives|data/interim|data/features|work|scratch|results|artifacts)/' || true)"
    if [ -n "${offenders}" ]; then
        echo "${offenders}" | sed 's/^/  /'
        echo "  prohibited artifact path(s) tracked"
        return 1
    fi
    echo "  No imaging data, derivative, or model weight is tracked."
}

check_credentials() {
    local patterns=(
        'AKIA[0-9A-Z]{16}'
        '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
        'ghp_[A-Za-z0-9]{20,}'
        'sk-[A-Za-z0-9_-]{20,}'
        '(password|api[_-]?key|secret|token)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{6,}["'"'"']'
    )
    local hits=0
    for pattern in "${patterns[@]}"; do
        while IFS= read -r match; do
            [ -n "${match}" ] || continue
            echo "  ${match}"
            hits=$((hits + 1))
        done < <(git ls-files -z | xargs -0 grep -InE "${pattern}" 2>/dev/null || true)
    done
    if [ "${hits}" -gt 0 ]; then
        echo "  ${hits} potential credential match(es)"
        return 1
    fi
    echo "  No credential pattern found in tracked files."
}

run_gate 'Python version' check_python_version
run_gate 'Ruff format' "${python_bin}" -m ruff format --check .
run_gate 'Ruff lint' "${python_bin}" -m ruff check .
run_gate 'Mypy' "${python_bin}" -m mypy src tests
run_gate 'Pytest' "${python_bin}" -m pytest -ra --strict-markers
run_gate 'Runtime metadata' check_runtime_metadata
run_gate 'Pre-commit' "${python_bin}" -m pre_commit run --all-files
run_gate 'Oversized files' check_large_files
run_gate 'Tracked data and model artifacts' check_tracked_artifacts
run_gate 'Credential scan' check_credentials

echo
echo "=== Summary ==="
for i in "${!gate_names[@]}"; do
    printf '%-34s %s\n' "${gate_names[$i]}" "${gate_results[$i]}"
done
echo
if [ "${failures}" -gt 0 ]; then
    echo "RESULT: FAIL (${failures} of ${#gate_names[@]} gates failed)"
    exit 1
fi
echo "RESULT: PASS (all ${#gate_names[@]} gates passed)"
exit 0
