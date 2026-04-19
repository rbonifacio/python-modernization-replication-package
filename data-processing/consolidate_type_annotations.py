#!/usr/bin/env python3
"""
Two-pass pipeline that converts raw type-annotation refactoring rows into a
clean, commit-level dataset with cross-commit completeness classification.

Pass 1 — Consolidation (Option A → Option B):
  Collapses multiple "Add Parameter Type Annotation" rows for the same
  (commit, method) into one row.  "Add Return Type Annotation" rows are
  deduplicated.  All other refactoring types are deduplicated and passed
  through unchanged.

Pass 2 — Cross-commit classification:
  For each (repository, method) tracks which parameters and whether the return
  type have been annotated cumulatively across all commits in chronological
  order.  Each annotation event is then re-labelled as one of:

    • Add complete type annotation for function
        – After this commit every parameter AND the return type are annotated.

    • Add partial type annotation for function (missing type information for return type)
        – After this commit every parameter is annotated but the return type is not.

    • Add partial type annotation for function (missing type information for parameter)
        – After this commit the return type is annotated but at least one parameter is not.

    • Add Parameter Type Annotation   (unchanged)
        – Some parameters are annotated in this commit but the function still
          has un-annotated parameters and no return type is annotated yet.

Usage:
    python3 scripts/consolidate_type_annotations.py
    python3 scripts/consolidate_type_annotations.py \\
        --input  /path/to/full_ds.csv \\
        --output /path/to/final_ds.csv
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARAM_TYPE  = "Add Parameter Type Annotation"
RETURN_TYPE = "Add Return Type Annotation"

COMPLETE         = "Add complete type annotation for function"
PARTIAL_RETURN   = "Add partial type annotation for function (missing type information for return type)"
PARTIAL_PARAM    = "Add partial type annotation for function (missing type information for parameter)"

# ---------------------------------------------------------------------------
# Test-code detection
# ---------------------------------------------------------------------------

_TEST_PATH_SEGMENTS = re.compile(r"(^|/)(tests?|testing)/", re.IGNORECASE)
_TEST_FILENAME      = re.compile(r"(^|/)test_[^/]+\.py$|[^/]+_test\.py$|conftest\.py$", re.IGNORECASE)


def _is_test_file(path: str) -> bool:
    """Return True if *any* pipe-separated file path looks like test code."""
    for p in path.split(" | "):
        p = p.strip()
        if _TEST_PATH_SEGMENTS.search(p) or _TEST_FILENAME.search(p):
            return True
    return False


def _row_is_test(row: dict) -> str:
    right = row.get("right_file_path", "") or ""
    left  = row.get("left_file_path",  "") or ""
    return "test" if (_is_test_file(right) or _is_test_file(left)) else "production"


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Single-param raw description (Pass 1 input)
_RAW_PARAM_RE = re.compile(
    r"^Add Parameter Type Annotation (.+?) in parameter (\S+) (in method .+ from class .+)$"
)
# Return-type description
_RETURN_RE = re.compile(
    r"^Add Return Type Annotation (.+?) (in method .+ from class .+)$"
)
# "in method ... from class ..." anchor at end of any description
_METHOD_ID_RE = re.compile(r"(in method .+ from class .+)$")


def _extract_method_identity(description: str) -> str:
    m = _METHOD_ID_RE.search(description)
    return m.group(1) if m else description


def _extract_annotated_params(description: str) -> set[str]:
    """Return the set of parameter names annotated in a (possibly consolidated) description."""
    # Multi-param consolidated format: "Add Parameter Type Annotation [...] in method ..."
    # Greedy match of \[...\] correctly handles nested brackets in type names
    # (e.g. Optional[Dict[str, int]]) because the regex engine backtracks to the
    # last ']' that is followed by ' in method'.
    m = re.match(r"^Add Parameter Type Annotation \[(.+)\] in method", description)
    if m:
        return set(re.findall(r"in parameter (\S+)", m.group(1)))
    # Single-param format
    m = re.match(r"^Add Parameter Type Annotation .+? in parameter (\S+) in method", description)
    if m:
        return {m.group(1)}
    return set()


def _count_params_in_signature(method_identity: str) -> int:
    """Count annotatable parameters from 'in method <vis> <name>(<params>) from class <cls>'."""
    before_class = method_identity.split(" from class ", 1)[0]
    paren_open  = before_class.rfind("(")
    paren_close = before_class.rfind(")")
    if paren_open == -1 or paren_close <= paren_open:
        return 0
    params_str = before_class[paren_open + 1 : paren_close].strip()
    if not params_str:
        return 0
    params = [p.strip() for p in params_str.split(",")]
    return sum(1 for p in params if p and p != "self")


def _parse_time(t: str) -> int:
    try:
        return int(t)
    except (ValueError, TypeError):
        return 0

# ---------------------------------------------------------------------------
# Pass 1 – consolidation
# ---------------------------------------------------------------------------

def pass1_consolidate(input_path: Path) -> tuple[list[dict], list[str]]:
    """
    Collapse per-parameter annotation rows into one row per (commit, method).
    Returns (rows, fieldnames).
    """
    print(f"Pass 1 — reading {input_path} …")

    param_groups:      dict[tuple, dict]      = {}
    param_annotations: dict[tuple, set]       = defaultdict(set)
    return_groups:     dict[tuple, dict]      = {}
    other_rows:        list[dict]             = []
    other_seen:        set[tuple]             = set()

    fieldnames     = []
    total_in       = 0
    skipped        = 0

    with input_path.open(newline="", encoding="utf-8") as fh:
        reader     = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []

        for row in reader:
            total_in += 1
            rtype = row.get("refactoring_type", "").strip()

            if rtype == PARAM_TYPE:
                m = _RAW_PARAM_RE.match(row["description"])
                if not m:
                    skipped += 1
                    continue
                ann_type, param_name = m.group(1), m.group(2)
                mid = m.group(3)                        # "in method … from class …"
                key = (row["commit_id"], row["repository"], mid)
                if key not in param_groups:
                    param_groups[key] = row
                param_annotations[key].add((ann_type, param_name))

            elif rtype == RETURN_TYPE:
                m = _RETURN_RE.match(row["description"])
                if not m:
                    skipped += 1
                    continue
                mid = m.group(2)
                key = (row["commit_id"], row["repository"], mid)
                return_groups[key] = row

            else:
                fingerprint = tuple(row.get(f, "") for f in fieldnames)
                if fingerprint not in other_seen:
                    other_seen.add(fingerprint)
                    other_rows.append(row)

    consolidated_param: list[dict] = []
    for key, base_row in param_groups.items():
        mid         = key[2]
        sorted_anns = sorted(param_annotations[key])
        if len(sorted_anns) == 1:
            t, p = sorted_anns[0]
            desc = f"{PARAM_TYPE} {t} in parameter {p} {mid}"
        else:
            parts = ", ".join(f"{t} in parameter {p}" for t, p in sorted_anns)
            desc  = f"{PARAM_TYPE} [{parts}] {mid}"
        consolidated_param.append({**base_row, "description": desc})

    consolidated_return = list(return_groups.values())
    rows = other_rows + consolidated_param + consolidated_return

    print(f"  input rows          : {total_in:>10,}")
    print(f"  skipped (malformed) : {skipped:>10,}")
    print(f"  other (deduped)     : {len(other_rows):>10,}")
    print(f"  param groups        : {len(consolidated_param):>10,}")
    print(f"  return groups       : {len(consolidated_return):>10,}")
    print(f"  → pass-1 output rows: {len(rows):>10,}")
    return rows, fieldnames

# ---------------------------------------------------------------------------
# Pass 2 – cross-commit classification
# ---------------------------------------------------------------------------

def pass2_classify(rows: list[dict]) -> list[dict]:
    """
    Re-label each annotation event using the cumulative annotation state of its
    function up to and including the current commit.
    """
    print("\nPass 2 — cross-commit classification …")

    # Index annotation rows; pass other rows through unchanged
    param_index:  dict[tuple, dict] = {}   # (commit_id, repo, mid) -> row
    return_index: dict[tuple, dict] = {}
    other_rows:   list[dict]        = []

    for row in rows:
        rtype = row["refactoring_type"].strip()
        if rtype == PARAM_TYPE:
            mid = _extract_method_identity(row["description"])
            param_index[(row["commit_id"], row["repository"], mid)] = row
        elif rtype == RETURN_TYPE:
            mid = _extract_method_identity(row["description"])
            return_index[(row["commit_id"], row["repository"], mid)] = row
        else:
            other_rows.append(row)

    # Collect all (repo, mid) → sorted list of (commit_id, commit_time)
    commits_per_method: dict[tuple, set] = defaultdict(set)
    for commit_id, repo, mid in param_index:
        t = _parse_time(param_index[(commit_id, repo, mid)]["commit_time"])
        commits_per_method[(repo, mid)].add((commit_id, t))
    for commit_id, repo, mid in return_index:
        t = _parse_time(return_index[(commit_id, repo, mid)]["commit_time"])
        commits_per_method[(repo, mid)].add((commit_id, t))

    # Classify each annotation event
    result: list[dict] = []

    counters = defaultdict(int)

    for (repo, mid), commit_set in commits_per_method.items():
        total_params      = _count_params_in_signature(mid)
        cumulative_params: set[str] = set()
        cumulative_return = False

        for commit_id, _ in sorted(commit_set, key=lambda x: (x[1], x[0])):
            p_row = param_index.get((commit_id, repo, mid))
            r_row = return_index.get((commit_id, repo, mid))

            this_params = _extract_annotated_params(p_row["description"]) if p_row else set()
            this_return = r_row is not None

            cumulative_params |= this_params
            cumulative_return  = cumulative_return or this_return

            all_params_covered = len(cumulative_params) >= total_params

            base_row = p_row or r_row   # guaranteed non-None

            if all_params_covered and cumulative_return:
                new_type = COMPLETE
                new_desc = f"{COMPLETE} {mid}"
            elif all_params_covered and not cumulative_return:
                new_type = PARTIAL_RETURN
                new_desc = f"{PARTIAL_RETURN} {mid}"
            elif not all_params_covered and cumulative_return:
                new_type = PARTIAL_PARAM
                new_desc = f"{PARTIAL_PARAM} {mid}"
            else:
                # Some params covered, no return yet — function was/is partially annotated.
                # Keep the simple label; preserve the consolidated description.
                new_type = PARAM_TYPE
                new_desc = base_row["description"]

            counters[new_type] += 1
            result.append({**base_row, "refactoring_type": new_type, "description": new_desc})

    final = other_rows + result

    print(f"  {COMPLETE:<75}: {counters[COMPLETE]:>8,}")
    print(f"  {PARTIAL_RETURN:<75}: {counters[PARTIAL_RETURN]:>8,}")
    print(f"  {PARTIAL_PARAM:<75}: {counters[PARTIAL_PARAM]:>8,}")
    print(f"  {PARAM_TYPE:<75}: {counters[PARAM_TYPE]:>8,}")
    print(f"  other (pass-through)                                                       : {len(other_rows):>8,}")
    print(f"  → pass-2 output rows: {len(final):>10,}")
    return final

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _root = Path(__file__).parent.parent
    parser.add_argument(
        "--input",
        default=str(_root / "dataset" / "full_ds.csv"),
    )
    parser.add_argument(
        "--output",
        default=str(_root / "dataset" / "final_ds.csv"),
    )
    args = parser.parse_args()

    rows, fieldnames = pass1_consolidate(Path(args.input))
    rows             = pass2_classify(rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out_fields = list(fieldnames) + ["is_test_code"]
    for row in rows:
        row["is_test_code"] = _row_is_test(row)

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWritten → {output_path}")


if __name__ == "__main__":
    main()
