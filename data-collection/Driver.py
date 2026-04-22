#!/usr/bin/env python3
"""
Driver.py
----------------------------
Run run_refactoringminer.py for every repository found inside a given
input folder, using the repository's current (checked-out) branch.

Only commits on or after 2015-01-01 are analysed.  For each project the script
locates the first commit in 2015, then passes its parent SHA as the start of a
-bc range up to HEAD.  If the repository itself started in 2015 (no parent),
the full history is analysed with -a instead.

Progress is persisted in a checkpoint file so that an interrupted run (e.g.
machine shutdown) can be resumed exactly where it left off.

Each project's output is written to <output-dir>/logs/<project>.log so that
parallel runs don't produce interleaved terminal noise.

Usage examples
--------------
  # Process all repos under /data/repos, write results to /data/output
  python Driver.py /data/repos --output-dir /data/output

  # Resume a previously interrupted run (checkpoint is read automatically)
  python Driver.py /data/repos --output-dir /data/output

  # Run 4 projects in parallel (tune --jvm-args to fit available RAM)
  python Driver.py /data/repos --output-dir /data/output \\
      --workers 4 --jvm-args "-Xmx8g" --batch-size 100

  # Use a custom checkpoint file location
  python Driver.py /data/repos --output-dir /data/output \\
      --checkpoint /data/progress.json
"""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Defaults — override via CLI flags
_JVM_ARGS   = "-Xmx96g"
_BATCH_SIZE = 200

# Only analyse commits on or after this date (exclusive lower bound for git)
_SINCE_DATE = "2014-12-31"  # git --after is exclusive, so this means >= 2015-01-01

_COLLECT_SCRIPT = Path(__file__).resolve().parent / "run_refactoringminer.py"


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _default_checkpoint(output_dir: Path) -> Path:
    return output_dir / "checkpoint.json"


def load_checkpoint(path: Path) -> dict:
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    return {"completed": [], "failed": []}


def save_checkpoint(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Project discovery
# ---------------------------------------------------------------------------

def discover_projects(input_dir: Path) -> list[Path]:
    """Return sorted list of direct subdirectories that look like git repos."""
    projects = sorted(
        p for p in input_dir.iterdir()
        if p.is_dir() and (p / ".git").exists()
    )
    if not projects:
        sys.exit(f"[error] No git repositories found in {input_dir}")
    return projects


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True,
        text=True,
    )


def resolve_sha(repo: Path, rev: str) -> str | None:
    """Return the full SHA for *rev*, or None if it cannot be resolved."""
    r = _git(repo, "rev-parse", rev)
    return r.stdout.strip() if r.returncode == 0 else None


def first_commit_since(repo: Path, since_date: str) -> str | None:
    """Return the SHA of the oldest commit with committer-date > since_date."""
    r = _git(repo, "log", f"--after={since_date}", "--reverse", "--format=%H")
    lines = [l for l in r.stdout.splitlines() if l]
    return lines[0] if lines else None


def build_range_args(repo: Path) -> list[str] | None:
    """
    Return the mode arguments for run_refactoringminer.py that cover
    commits from 2015-01-01 up to HEAD.

    Strategy
    --------
    1. Find the first commit in 2015.
    2. If that commit has a parent, use -bc <parent> <HEAD> so the range is
       (parent, HEAD] = [first-2015, HEAD].
    3. If it has no parent (repo started in 2015), use -a <repo> to cover all
       history (which is already >= 2015).
    4. If there are no commits after _SINCE_DATE, return None (skip project).
    """
    first = first_commit_since(repo, _SINCE_DATE)
    if first is None:
        return None  # no commits in 2015+

    head = resolve_sha(repo, "HEAD")
    if head is None:
        return None

    parent = resolve_sha(repo, f"{first}^")
    if parent is None:
        # first 2015 commit is the initial commit — no parent, use -a
        return ["-a", str(repo)]

    return ["-bc", str(repo), parent, head]


# ---------------------------------------------------------------------------
# Per-project runner  (executed inside a worker process)
# ---------------------------------------------------------------------------

def run_project(project: Path, output_dir: Path,
                jvm_args: str, batch_size: int) -> bool:
    """
    Invoke run_refactoringminer.py for *project* covering commits from
    2015-01-01 to HEAD.  All output is written to <output_dir>/logs/<name>.log.
    Returns True on success (exit code 0), False otherwise.
    """
    range_args = build_range_args(project)
    if range_args is None:
        log_dir = output_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{project.name}.log"
        with open(log_file, "w", encoding="utf-8") as lf:
            lf.write(f"[{_ts()}] skip: no commits found after {_SINCE_DATE}\n")
        return True  # nothing to do — not a failure

    cmd = [
        sys.executable,
        str(_COLLECT_SCRIPT),
        *range_args,
        f"--jvm-args={jvm_args}",
        "--batch-size", str(batch_size),
    ]

    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{project.name}.log"

    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write(f"[{_ts()}] command: {' '.join(cmd)}\n")
        lf.write(f"[{_ts()}] cwd: {output_dir}\n\n")
        lf.flush()
        result = subprocess.run(cmd, cwd=str(output_dir), stdout=lf, stderr=lf)

    return result.returncode == 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch-run RefactoringMiner over a folder of git repositories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "input_dir",
        help="Directory containing cloned git repositories (one repo per sub-folder)",
    )
    p.add_argument(
        "--output-dir",
        default=".",
        help="Directory where results/ and the checkpoint file are written "
             "(default: current working directory)",
    )
    p.add_argument(
        "--checkpoint",
        default=None,
        metavar="PATH",
        help="Path to the checkpoint JSON file "
             "(default: <output-dir>/checkpoint.json)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of projects to process in parallel (default: 1). "
             "With N workers, each JVM gets roughly total_RAM/N — "
             "tune --jvm-args accordingly.",
    )
    p.add_argument(
        "--jvm-args",
        default=_JVM_ARGS,
        metavar="ARGS",
        help=f"JVM arguments for each worker (default: '{_JVM_ARGS}'). "
             "When running multiple workers, lower this proportionally "
             "to available RAM, e.g. --workers 4 --jvm-args '-Xmx24g'.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=_BATCH_SIZE,
        metavar="N",
        help=f"Max commits per JAR invocation to avoid OOM (default: {_BATCH_SIZE}).",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    input_dir  = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = (
        Path(args.checkpoint).resolve() if args.checkpoint
        else _default_checkpoint(output_dir)
    )

    if not input_dir.is_dir():
        sys.exit(f"[error] Input directory does not exist: {input_dir}")

    if not _COLLECT_SCRIPT.is_file():
        sys.exit(f"[error] run_refactoringminer.py not found at {_COLLECT_SCRIPT}")

    projects = discover_projects(input_dir)
    state    = load_checkpoint(checkpoint_path)

    completed_set = set(state["completed"])
    failed_set    = set(state["failed"])

    pending = [p for p in projects if p.name not in completed_set]
    skipped = len(projects) - len(pending)

    workers = max(1, args.workers)

    print(f"[{_ts()}] Found {len(projects)} project(s) in {input_dir}")
    if skipped:
        print(f"[{_ts()}] Skipping {skipped} already-completed project(s) "
              f"(checkpoint: {checkpoint_path})")
    print(f"[{_ts()}] {len(pending)} project(s) to process "
          f"({workers} worker(s), jvm-args: {args.jvm_args})")
    print(f"[{_ts()}] Logs: {output_dir / 'logs'}\n")

    done_count = 0

    with ProcessPoolExecutor(max_workers=workers) as pool:
        future_to_project = {
            pool.submit(run_project, p, output_dir, args.jvm_args, args.batch_size): p
            for p in pending
        }

        for future in as_completed(future_to_project):
            project = future_to_project[future]
            done_count += 1
            prefix = f"[{_ts()}] [{done_count}/{len(pending)}]"

            try:
                success = future.result()
            except Exception as exc:
                success = False
                print(f"{prefix} ERROR: {project.name} raised {exc}", flush=True)

            if success:
                state["completed"].append(project.name)
                if project.name in failed_set:
                    state["failed"] = [n for n in state["failed"] if n != project.name]
                    failed_set.discard(project.name)
                print(f"{prefix} Done:   {project.name}", flush=True)
            else:
                state["failed"].append(project.name)
                failed_set.add(project.name)
                print(f"{prefix} FAILED: {project.name} "
                      f"(see logs/{project.name}.log)", flush=True)

            save_checkpoint(checkpoint_path, state)

    # Final summary
    print(f"\n{'='*70}")
    print(f"[{_ts()}] Batch complete.")
    print(f"  Total    : {len(projects)}")
    print(f"  Completed: {len(state['completed'])}")
    if state["failed"]:
        print(f"  Failed   : {len(state['failed'])}")
        for name in state["failed"]:
            print(f"    - {name}")
    print(f"  Checkpoint: {checkpoint_path}")
    print(f"{'='*70}")

    if state["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
