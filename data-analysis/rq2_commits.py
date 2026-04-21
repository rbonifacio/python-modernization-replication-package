"""
rq2_commits.py
--------------
Answers RQ2: Are there large commits that apply many type-annotation
transformations at once?

Produces a summary of the distribution of transformations per commit and
highlights the top commits (by volume), which may indicate bulk annotation
efforts (e.g. automated tools, dedicated refactoring sessions).

Inputs
------
dataset/final_ds.csv

Outputs
-------
tables/refactoring_type_distribution.tex  – per-type transformation counts
tables/top_commits.tex                    – top-20 commits by transformation count
"""

from pathlib import Path

import numpy as np
import pandas as pd

from stats_utils import mann_whitney

# ── paths ─────────────────────────────────────────────────────────────────────
BASE   = Path(__file__).parent.parent
DATA   = BASE / "dataset" / "final_ds.csv"
TABS   = BASE / "tables"
TABS.mkdir(exist_ok=True)

OUT_TABLE         = TABS / "refactoring_type_distribution.tex"
OUT_TABLE_COMMITS = TABS / "top_commits.tex"
TOP_K             = 20


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("RQ2 — Commit-level analysis of type-annotation transformations")
    print("=" * 65)

    print("\n[1/3] Loading dataset …")
    df = pd.read_csv(DATA, dtype=str)
    print(f"      {len(df):,} rows, {df['project_name'].nunique()} projects")

    # ── Refactoring-type distribution ─────────────────────────────────────────
    print("\n[2/3] Refactoring-type distribution …")
    print("      Each row counts how many transformation instances belong to that type.")
    summary = (
        df["refactoring_type"]
        .value_counts(dropna=False)
        .rename_axis("Refactoring Type")
        .reset_index(name="Count")
    )
    total_transformations = summary["Count"].sum()
    summary["Percentage (%)"] = 100.0 * summary["Count"] / total_transformations

    print(f"\n      Total transformations: {total_transformations:,}")
    print(summary.to_string(index=False))

    latex_table = summary.rename(columns={"Count": "Total"}).assign(
        Total=lambda d: d["Total"].map(lambda x: f"\\num{{{x}}}"),
        **{"Percentage (%)": lambda d: d["Percentage (%)"].map(lambda x: f"{x:.2f}\\%")},
    ).to_latex(
        index=False,
        escape=False,
        caption="Distribution of transformations by refactoring type.",
        label="tab:refactoring-type-distribution",
        column_format="lrr",
    )
    OUT_TABLE.write_text(latex_table, encoding="utf-8")
    print(f"\n  Wrote {OUT_TABLE}")

    # ── Commit-level analysis ─────────────────────────────────────────────────
    print("\n[3/3] Commit-level analysis …")
    print("      Each row is one commit; 'Total' is the number of transformations it contains.")
    commit_summary = (
        df.groupby("commit_id")
        .size()
        .reset_index(name="Total")
        .sort_values("Total", ascending=False)
    )
    total = len(df)
    commit_summary["Percentage (%)"] = 100.0 * commit_summary["Total"] / total

    n_commits = len(commit_summary)
    s = commit_summary["Total"]
    q1, q3 = s.quantile([0.25, 0.75])

    print(f"\n  Transformations per commit ({n_commits:,} commits in total):")
    print(f"    median = {s.median():.0f}  |  mean = {s.mean():.2f}  |  std = {s.std():.2f}")
    print(f"    Q1 = {q1:.0f}  |  Q3 = {q3:.0f}  |  max = {s.max()}")
    print(f"    Distribution is right-skewed: most commits are small; a few are very large.")

    top_commits = commit_summary.head(TOP_K).merge(
        df[["commit_id", "repository", "commit_url"]].drop_duplicates(),
        on="commit_id",
        how="left",
    )
    print(f"\n  Top-{TOP_K} commits by transformation count:")
    print(top_commits[["repository", "commit_id", "Total", "Percentage (%)"]].to_string(index=False))

    top_10_share = commit_summary.head(10)["Total"].sum() / total * 100
    top_20_share = commit_summary.head(20)["Total"].sum() / total * 100

    print(f"\n  Share of all transformations concentrated in top commits:")
    print(f"    Top-10 commits : {top_10_share:.2f}%")
    print(f"    Top-20 commits : {top_20_share:.2f}%")

    latex_commits = (
        top_commits
        .assign(
            Total=lambda d: d["Total"].map(lambda x: f"\\num{{{x}}}"),
            **{"Percentage (%)": lambda d: d["Percentage (%)"].map(lambda x: f"{x:.2f}\\%")},
        )
        [["repository", "commit_id", "Total", "Percentage (%)"]]
        .to_latex(
            index=False,
            escape=False,
            caption=f"Top {TOP_K} commits by number of transformations.",
            label="tab:top-commits",
            column_format="llrr",
        )
    )
    OUT_TABLE_COMMITS.write_text(latex_commits, encoding="utf-8")
    print(f"\n  Wrote {OUT_TABLE_COMMITS}")

    # ── Hypothesis testing: bulk vs. regular commits ──────────────────────────
    print("\n[4/3] Hypothesis testing: are bulk commits a distinct population?")
    print("      H₀: no difference in transformation counts between bulk and regular commits")
    print("      Bulk = top-10% by transformation count; regular = bottom-90%")

    cutoff = commit_summary["Total"].quantile(0.90)
    bulk    = commit_summary.loc[commit_summary["Total"] >= cutoff, "Total"].values
    regular = commit_summary.loc[commit_summary["Total"] <  cutoff, "Total"].values
    print(f"      Cutoff (90th percentile): {cutoff:.0f} transformations/commit")

    mann_whitney(
        bulk, regular,
        label_a=f"bulk commits (≥{cutoff:.0f} transformations, n={len(bulk):,})",
        label_b=f"regular commits (<{cutoff:.0f} transformations, n={len(regular):,})",
    )

    # Within bulk commits: do production commits differ from test commits?
    print("\n      Within-bulk: production vs. test transformation share")
    print("      H₀: no difference between bulk commits touching production vs. test code")
    bulk_ids = commit_summary.loc[commit_summary["Total"] >= cutoff, "commit_id"]
    df_bulk  = df[df["commit_id"].isin(bulk_ids)]
    prod_bulk = df_bulk[df_bulk["is_test_code"] == "production"].groupby("commit_id").size().values
    test_bulk = df_bulk[df_bulk["is_test_code"] == "test"].groupby("commit_id").size().values
    if len(prod_bulk) > 0 and len(test_bulk) > 0:
        mann_whitney(
            prod_bulk, test_bulk,
            label_a="bulk commits — production transformations",
            label_b="bulk commits — test transformations",
        )
    else:
        print("      Insufficient data for production/test split within bulk commits.")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
