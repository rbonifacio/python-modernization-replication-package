#!/usr/bin/env python3
"""
clone_projects.py
-----------------
Clone repositories listed in projects.csv to a given target directory.

Two modes
---------
Default — new execution:
    Clones each repository at HEAD. Use this when running the study on a
    fresh or updated snapshot of the projects.

        python clone_projects.py /path/to/repos

Replicate — exact replication:
    Clones each repository then checks out the specific commit recorded in
    the `study_revision` column of projects.csv. Use this to reproduce the
    original study results exactly.

        python clone_projects.py /path/to/repos --replicate
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def clone_repo(repo: str, target_dir: Path) -> bool:
    url  = f"https://github.com/{repo}.git"
    dest = target_dir / repo.split("/")[1]

    if dest.exists():
        print(f"  [skip]  {repo} — already exists at {dest}")
        return True

    print(f"  [clone] {repo}")
    result = run(["git", "clone", url, str(dest)])
    if result.returncode != 0:
        print(f"  [error] {repo}: {result.stderr.strip()}", file=sys.stderr)
        return False

    return True


def checkout_revision(repo: str, target_dir: Path, revision: str) -> bool:
    dest = target_dir / repo.split("/")[1]
    result = run(["git", "-C", str(dest), "checkout", "--quiet", revision])
    if result.returncode != 0:
        print(f"  [error] {repo}: could not checkout {revision[:12]}: "
              f"{result.stderr.strip()}", file=sys.stderr)
        return False

    print(f"  [checkout] {repo} → {revision[:12]}")
    return True


def load_projects(csv_path: Path, replicate: bool) -> list[dict]:
    projects = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("name", "").strip()
            if not name:
                continue
            revision = row.get("study_revision", "").strip()
            if replicate and not revision:
                print(f"  [warn] {name}: no study_revision — will be skipped in --replicate mode",
                      file=sys.stderr)
                continue
            projects.append({"name": name, "revision": revision})
    return projects


def main():
    parser = argparse.ArgumentParser(
        description="Clone repositories from projects.csv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "target_dir",
        help="Directory where repositories will be cloned",
    )
    parser.add_argument(
        "--replicate", action="store_true",
        help="Check out the exact study_revision after cloning "
             "(replication mode — reproduces the original study)",
    )
    parser.add_argument(
        "--csv",
        default=Path(__file__).parent / "projects.csv",
        help="Path to projects.csv (default: projects.csv next to this script)",
    )
    args = parser.parse_args()

    target   = Path(args.target_dir)
    csv_path = Path(args.csv)

    target.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        sys.exit(f"[error] CSV file not found: {csv_path}")

    projects = load_projects(csv_path, args.replicate)

    mode = "replication (fixed revisions)" if args.replicate else "new execution (HEAD)"
    print(f"Mode      : {mode}")
    print(f"Projects  : {len(projects)}")
    print(f"Target    : {target}\n")

    failed = []
    for p in projects:
        ok = clone_repo(p["name"], target)
        if ok and args.replicate:
            ok = checkout_revision(p["name"], target, p["revision"])
        if not ok:
            failed.append(p["name"])

    print(f"\nDone. {len(projects) - len(failed)}/{len(projects)} successful.")
    if failed:
        print("Failed:")
        for r in failed:
            print(f"  {r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
