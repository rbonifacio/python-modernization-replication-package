"""
Driver.py  —  data-processing pipeline
---------------------------------------
Converts raw RefactoringMiner JSON output into the analysis-ready dataset.

Steps
-----
  Step 1  json_to_csv               – merge all JSON result files into a single
                                      flat CSV (dataset/full_ds.csv)
  Step 2  consolidate_type_annotations – cross-commit classification and
                                      deduplication → dataset/final_ds.csv

Prerequisites
-------------
  Raw JSON results must already exist under dataset/all-results/ (produced by
  the data-collection pipeline: data-collection/Driver.py).

Usage
-----
    python Driver.py                      # runs both steps
    python Driver.py --steps json_to_csv  # run only step 1
"""

import argparse
import importlib
import sys
import time
from pathlib import Path

STEPS = [
    ("json_to_csv",                "json_to_csv"),
    ("consolidate_type_annotations", "consolidate_type_annotations"),
]

STEP_NAMES = [s[0] for s in STEPS]


def run_step(name: str, module_name: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  STEP: {name}  ({module_name}.py)")
    print(f"{'='*60}")
    t0 = time.perf_counter()
    try:
        mod = importlib.import_module(module_name)
        mod.main()
        print(f"\n  [OK] {name} finished in {time.perf_counter() - t0:.1f}s")
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
        description="Run the data-processing pipeline.",
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
        print(f"  {step:<35} {status}")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
