#!/usr/bin/env python
"""Deterministic BIDS compatibility-view builder.

Usage::

    python scripts/build_bids_compatibility_view.py \\
        --source </external/bids/root> \\
        --destination </external/compatibility/path> \\
        --evidence-output </external/evidence.json>

All paths must be absolute and outside the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from neuromultiverse.bids_compatibility import (
    CompatibilityError,
    build_compatibility_view,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--source",
        type=Path,
        required=True,
        help="absolute path to the source BIDS root (read-only, outside repo)",
    )
    result.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="absolute path for the new compatibility view (will be created)",
    )
    result.add_argument(
        "--evidence-output",
        type=Path,
        default=None,
        help="absolute path for the canonical evidence JSON (outside repo, mode 600)",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = build_compatibility_view(
            source=args.source,
            destination=args.destination,
            repo_root=REPO_ROOT,
            evidence_path=args.evidence_output,
        )
    except CompatibilityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"UNEXPECTED ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
