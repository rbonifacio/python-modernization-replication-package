"""
Driver.py
---------
Runs the analysis pipeline for the Python modernization study.

Data collection (run once, before this script) lives in scripts/:
  scripts/clone_projects.py              – clone all project repos
  scripts/collect_all_refactorings.py   – run RefactoringMiner (jar/RM-fat.jar)
  scripts/json_to_csv.py                – merge JSON outputs → dataset/full_ds.csv
  scripts/consolidate_type_annotations.py – classify → dataset/final_ds.csv

Pipeline
--------
  Step 1  rq1a  – rq1_distribution.py  : RQ1 – per-repo transformation stats
  Step 2  rq1b  – rq1_evolution.py     : RQ1 – temporal evolution
  Step 3  rq2   – rq2_commits.py       : RQ2 – transformation types & commit analysis
  Step 4  rq3   – rq3_contributors.py  : RQ3 – contributor concentration

Usage
-----
    python Driver.py                        # runs all steps
    python Driver.py --steps rq1a rq1b rq2 # runs only the named steps

Options
-------
--steps STEP ...    Run only the listed step names (space-separated)
"""

import argparse
import sys
import time
from pathlib import Path

# ── step registry ─────────────────────────────────────────────────────────────
STEPS: list[tuple[str, str]] = [
    ("rq1a", "rq1_distribution"),
    ("rq1b", "rq1_evolution"),
    ("rq2",  "rq2_commits"),
    ("rq3",  "rq3_contributors"),
]

STEP_NAMES = [s[0] for s in STEPS]


def _import(module_name: str):
    import importlib
    return importlib.import_module(module_name)


def run_step(name: str, module_name: str) -> bool:
    """Import and call main() for one step. Returns True on success."""
    print(f"\n{'='*60}")
    print(f"  STEP: {name}  ({module_name}.py)")
    print(f"{'='*60}")
    t0 = time.perf_counter()
    try:
        mod     = _import(module_name)
        main_fn = getattr(mod, "main")
        main_fn()
        elapsed = time.perf_counter() - t0
        print(f"\n  [OK] {name} finished in {elapsed:.1f}s")
        return True
    except SystemExit as exc:
        print(f"\n  [FAIL] {name} exited: {exc}", file=sys.stderr)
        return False
    except Exception as exc:
        import traceback
        print(f"\n  [FAIL] {name} raised {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run the Python modernization analysis pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--steps", nargs="+", choices=STEP_NAMES, metavar="STEP",
        help=f"Steps to run (choices: {', '.join(STEP_NAMES)})",
    )
    args = parser.parse_args()

    selected = args.steps if args.steps else STEP_NAMES
    print(f"Pipeline steps to run: {', '.join(selected)}")

    sys.path.insert(0, str(Path(__file__).parent))

    results: dict[str, bool] = {}
    for name, module_name in STEPS:
        if name not in selected:
            continue
        ok = run_step(name, module_name)
        results[name] = ok
        if not ok:
            print(f"\nPipeline aborted at step '{name}'.", file=sys.stderr)
            break

    print(f"\n{'='*60}")
    print("  PIPELINE SUMMARY")
    print(f"{'='*60}")
    for step in selected:
        status = "OK" if results.get(step) else ("FAILED" if step in results else "SKIPPED")
        print(f"  {step:<10} {status}")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
