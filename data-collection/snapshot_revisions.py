#!/usr/bin/env python3
"""
snapshot_revisions.py
---------------------
Traverses all folders matching the pattern `processamento*` under a given
root directory, identifies every git repository inside them, and records
the current HEAD revision (SHA) of each project.

This is used to freeze the exact state of the cloned repositories at the
time of data collection, so the analysis can be reproduced against the
same commits.

Inputs
------
A root directory containing one or more `processamento*` folders, each
holding cloned git repositories as direct subdirectories.

Outputs
-------
revisions.csv  – one row per project with columns:
    folder      : the processamento* folder name
    project     : the repository subdirectory name
    revision    : full SHA of HEAD
    branch      : current branch name (or 'HEAD' if detached)
    error       : error message if the revision could not be read

Usage
-----
    python snapshot_revisions.py /path/to/root
    python snapshot_revisions.py /path/to/root --output my_revisions.csv
    python snapshot_revisions.py .              # search current directory
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> tuple[str, str]:
    """Run a git command in *repo*. Returns (stdout, stderr)."""
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.stderr.strip()


def get_revision(repo: Path) -> dict:
    """Return revision info for a single git repository."""
    revision, err = git(repo, "rev-parse", "HEAD")
    if err and not revision:
        return {"revision": "", "branch": "", "error": err}

    branch, _ = git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    return {"revision": revision, "branch": branch, "error": ""}


def discover_repos(processamento_dir: Path) -> list[Path]:
    """Return direct subdirectories of *processamento_dir* that are git repos."""
    return sorted(
        p for p in processamento_dir.iterdir()
        if p.is_dir() and (p / ".git").exists()
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record the HEAD revision of every project inside processamento* folders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "root",
        help="Root directory to search for processamento* folders",
    )
    parser.add_argument(
        "--output", default="revisions.csv",
        help="Output CSV file path (default: revisions.csv)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"[error] Directory not found: {root}")

    folders = sorted(root.glob("processamento*"))
    if not folders:
        sys.exit(f"[error] No folders matching 'processamento*' found in {root}")

    print(f"Found {len(folders)} processamento* folder(s) in {root}")

    rows = []
    for folder in folders:
        repos = discover_repos(folder)
        print(f"\n  {folder.name}/ — {len(repos)} project(s)")

        for repo in repos:
            info = get_revision(repo)
            row = {
                "folder":   folder.name,
                "project":  repo.name,
                "revision": info["revision"],
                "branch":   info["branch"],
                "error":    info["error"],
            }
            rows.append(row)

            status = info["revision"][:12] if info["revision"] else f"ERROR: {info['error']}"
            print(f"    {repo.name:<40} {status}")

    output = Path(args.output)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["folder", "project", "revision", "branch", "error"])
        writer.writeheader()
        writer.writerows(rows)

    ok  = sum(1 for r in rows if not r["error"])
    err = sum(1 for r in rows if r["error"])
    print(f"\nTotal: {len(rows)} project(s) — {ok} OK, {err} error(s)")
    print(f"Wrote {output}")

    if err:
        sys.exit(1)


if __name__ == "__main__":
    main()
