#!/usr/bin/env python3
"""Recompute spreadsheet formulas in examples/ and write results in place."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from md_spreadsheet_engine.engine import MarkDownSpreadsheetEngine  # noqa: E402


@dataclass(frozen=True)
class ExampleGroup:
    """A set of markdown files that must be evaluated together."""

    names: tuple[str, ...]
    files: tuple[Path, ...]


EXAMPLE_GROUPS: tuple[ExampleGroup, ...] = (
    ExampleGroup(("invoice",), (REPO_ROOT / "examples" / "invoice.md",)),
    ExampleGroup(("cross_table",), (REPO_ROOT / "examples" / "cross_table.md",)),
    ExampleGroup(("budget",), (REPO_ROOT / "examples" / "budget.md",)),
    ExampleGroup(
        ("inventory", "summary"),
        (
            REPO_ROOT / "examples" / "cross_document" / "inventory.md",
            REPO_ROOT / "examples" / "cross_document" / "summary.md",
        ),
    ),
)

ENGINE_PATHS = (
    REPO_ROOT / "src",
    REPO_ROOT / "pyproject.toml",
)


def changed_paths(base_ref: str = "HEAD^") -> set[Path]:
    """Return repository paths changed relative to base_ref."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()

    return {REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()}


def groups_to_recompute(
    *,
    only_changed: bool,
    base_ref: str,
) -> list[ExampleGroup]:
    """Select example groups that need recomputation."""
    if not only_changed:
        return list(EXAMPLE_GROUPS)

    changed = changed_paths(base_ref)
    if not changed:
        return []

    if any(path in changed for path in ENGINE_PATHS) or any(
        path.is_relative_to(REPO_ROOT / "src") for path in changed
    ):
        return list(EXAMPLE_GROUPS)

    selected: list[ExampleGroup] = []
    for group in EXAMPLE_GROUPS:
        if any(path in changed for path in group.files):
            selected.append(group)
    return selected


def compute_group(group: ExampleGroup) -> None:
    """Load, evaluate, and write one example group in place."""
    engine = MarkDownSpreadsheetEngine()

    for doc_name, file_path in zip(group.names, group.files):
        content = file_path.read_text(encoding="utf-8")
        engine.load_markdown_document(doc_name, content)

    engine.evaluate()

    for doc_name, file_path in zip(group.names, group.files):
        output = engine.regenerate_markdown_document(doc_name)
        file_path.write_text(output, encoding="utf-8")
        print(f"updated {file_path.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Only recompute groups touched in the latest commit.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD^",
        help="Git ref to compare against when using --changed (default: HEAD^).",
    )
    args = parser.parse_args()

    groups = groups_to_recompute(only_changed=args.changed, base_ref=args.base_ref)
    if not groups:
        print("No example groups to recompute.")
        return 0

    for group in groups:
        compute_group(group)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
