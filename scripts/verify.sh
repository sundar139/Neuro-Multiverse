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

# Capture the complete working-tree state, tracked and untracked, in a stable
# machine-readable format. Used to prove that validation did not modify the
# repository: auto-fixing hooks are allowed to run, but a run that changes files
# and still reports success would be reporting a result it just manufactured.
git_available=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_available=1
fi

porcelain_state() {
    if [ "${git_available}" -ne 1 ]; then
        return 1
    fi
    git status --porcelain=v1 --untracked-files=all 2>/dev/null
}

initial_state=""
if [ "${git_available}" -eq 1 ]; then
    initial_state="$(porcelain_state)"
fi

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
check_git_diff() {
    if [ "${git_available}" -ne 1 ]; then
        echo "  git not available"
        return 1
    fi
    if ! git diff --check; then
        echo "  git diff --check (working tree) reported problems"
        return 1
    fi
    if ! git diff --cached --check; then
        echo "  git diff --cached --check (staged) reported problems"
        return 1
    fi
    echo "  No whitespace errors or conflict markers in the working-tree or staged diff."
}

# Must remain the last gate: it compares against the state captured at startup,
# so every preceding gate has had its chance to modify the tree.
check_tree_stability() {
    if [ "${git_available}" -ne 1 ]; then
        echo "  git not available"
        return 1
    fi
    local final_state
    final_state="$(porcelain_state)"
    if [ "${initial_state}" != "${final_state}" ]; then
        echo "  Validation MODIFIED the working tree. State before:"
        if [ -z "${initial_state}" ]; then
            echo "    (clean)"
        else
            printf '%s\n' "${initial_state}" | sed 's/^/    /'
        fi
        echo "  State after:"
        if [ -z "${final_state}" ]; then
            echo "    (clean)"
        else
            printf '%s\n' "${final_state}" | sed 's/^/    /'
        fi
        echo "  Nothing was reverted automatically. Review and stage or discard as intended."
        return 1
    fi
    # A dirty starting tree is fine; an unchanged dirty tree still passes.
    if [ -z "${initial_state}" ]; then
        echo "  Working tree unchanged by validation (started clean)."
    else
        local count
        count="$(printf '%s\n' "${initial_state}" | wc -l | tr -d ' ')"
        echo "  Working tree unchanged by validation (started dirty, ${count} entr(y/ies))."
    fi
}

run_gate 'Credential scan' check_credentials
run_gate 'Git diff check' check_git_diff
run_gate 'Working-tree stability' check_tree_stability

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
