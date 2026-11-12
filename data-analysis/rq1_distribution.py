"""
rq1_distribution.py
-------------------
Answers RQ1 (part 1): Distribution of transformations across repositories —
per-project statistics, commit sizes, and
production vs. test code breakdown.

Inputs
------
dataset/final_ds.csv

Outputs
-------
figures/boxplot_transformations.png  – box plot of per-repo transformation counts
figures/transformations_over_time.png – monthly evolution of all transformations
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from stats_utils import mann_whitney, kruskal_wallis

# ── paths ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
DATA = BASE / "dataset" / "final_ds.csv"
FIGS = BASE / "figures"
FIGS.mkdir(exist_ok=True)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("RQ1 — Distribution of type-annotation transformations")
    print("=" * 65)

    print("\n[1/6] Loading dataset …")
    df = pd.read_csv(DATA, dtype=str)
    print(f"      Columns : {df.columns.tolist()}")
    print(f"      Total rows (transformations): {len(df):,}")
    print(f"      Unique commits              : {df['commit_id'].nunique():,}")
    print(f"      Unique repositories         : {df['repository'].nunique():,}")

    # ── Transformation type breakdown ────────────────────────────────────────
    print("\n[2/6] Refactoring-type breakdown …")
    print("      Each row is one detected transformation instance.")
    type_counts = (
        df["refactoring_type"]
        .value_counts(dropna=False)
        .rename_axis("Refactoring Type")
        .reset_index(name="Count")
    )
    total_transformations = type_counts["Count"].sum()
    type_counts["Percentage (%)"] = 100.0 * type_counts["Count"] / total_transformations
    print(type_counts.to_string(index=False))

    # ── Production vs. test split ─────────────────────────────────────────────
    print("\n[3/6] Production vs. test code split (whole dataset) …")
    print("      'is_test_code' distinguishes transformations in test files.")
    split = df.groupby("is_test_code").size().rename("Count").reset_index()
    split["Percentage (%)"] = 100.0 * split["Count"] / len(df)
    print(split.to_string(index=False))

    print("\n      Production vs. test split for mypy only:")
    mypy = df[df["repository"].str.contains("mypy", na=False)]
    mypy_split = mypy.groupby("is_test_code").size().rename("Count").reset_index()
    print(mypy_split.to_string(index=False))

    # ── Per-repository share ──────────────────────────────────────────────────
    print("\n[4/6] Per-repository share of all transformations (top 10) …")
    repo_pct = (
        df.groupby("repository")
        .size()
        .rename("Count")
        .reset_index()
        .assign(**{"Share (%)": lambda d: 100.0 * d["Count"] / len(df)})
        .sort_values("Share (%)", ascending=False)
    )
    print(repo_pct.head(10).to_string(index=False))

    # ── §4.1 Table 2 — per-project statistics (with outliers) ────────────────
    print("\n[5/6] Per-project transformation counts …")
    print("      Each repository is one data point; values are transformation totals.")
    per_repo = df.groupby("repository").size().rename("Total")

    summary = {
        "n_projects": len(per_repo),
        "mean":       per_repo.mean(),
        "median":     per_repo.median(),
        "std":        per_repo.std(),
        "min":        per_repo.min(),
        "q1":         per_repo.quantile(0.25),
        "q3":         per_repo.quantile(0.75),
        "max":        per_repo.max(),
    }

    print("\n  All projects:")
    for k, v in summary.items():
        print(f"    {k:12s} = {v:>12.2f}" if isinstance(v, float) else f"    {k:12s} = {v:>12}")

    # the two repositories with the most transformations
    outliers = per_repo.nlargest(2).index.tolist()
    outlier_names = [o.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1] for o in outliers]
    outlier_share = 100 * per_repo[outliers].sum() / per_repo.sum()
    df_filtered = df[~df["repository"].isin(outliers)]
    per_repo_f  = df_filtered.groupby("repository").size().rename("Total")

    summary_f = {
        "n_projects": len(per_repo_f),
        "mean":       per_repo_f.mean(),
        "median":     per_repo_f.median(),
        "std":        per_repo_f.std(),
        "min":        per_repo_f.min(),
        "q1":         per_repo_f.quantile(0.25),
        "q3":         per_repo_f.quantile(0.75),
        "max":        per_repo_f.max(),
    }

    print(f"\n  Excluding {outlier_names[0]} and {outlier_names[1]} (the two largest repositories,")
    print(f"  which together account for {outlier_share:.1f}% of all transformations):")
    for k, v in summary_f.items():
        print(f"    {k:12s} = {v:>12.2f}" if isinstance(v, float) else f"    {k:12s} = {v:>12}")

    # ── Figures ────────────────────────────────────────────────────────────────
    print("\n[6/6] Generating figures …")

    print("\n  Box plot — transformations per repository (outliers hidden in plot):")
    print(f"    Data    : {len(per_repo)} repositories")
    print(f"    Median  : {per_repo.median():.0f}  |  Mean : {per_repo.mean():.2f}")
    print(f"    Q1–Q3   : {per_repo.quantile(0.25):.2f} – {per_repo.quantile(0.75):.2f}")
    print(f"    Min–Max : {per_repo.min()} – {per_repo.max()}")

    per_repo.plot(kind="box", showfliers=False)
    plt.ylabel("Number of transformations per repository")
    plt.tight_layout()
    out = FIGS / "boxplot_transformations.png"
    plt.savefig(out, dpi=300)
    plt.close()
    print(f"  Wrote {out}")

    df["commit_time"] = pd.to_datetime(df["commit_time"], errors="coerce", utc=True)
    df["month_year"]  = df["commit_time"].dt.to_period("M")
    monthly = (
        df.groupby("month_year")
        .size()
        .reset_index(name="Total")
    )
    monthly["month_year"] = monthly["month_year"].dt.to_timestamp()

    print(f"\n  Monthly evolution plot — transformations over time:")
    print(f"    Date range : {monthly['month_year'].min().strftime('%Y-%m')} to "
          f"{monthly['month_year'].max().strftime('%Y-%m')}")
    print(f"    Months     : {len(monthly)}")
    print(f"    Peak month : {monthly.loc[monthly['Total'].idxmax(), 'month_year'].strftime('%Y-%m')} "
          f"({monthly['Total'].max():,} transformations)")
    print(f"    Mean/month : {monthly['Total'].mean():.1f}")

    plt.figure(figsize=(8, 4))
    plt.plot(monthly["month_year"], monthly["Total"])
    plt.xlabel("Month-Year")
    plt.ylabel("Number of Transformations")
    plt.title("Evolution of Transformations Over Time")
    plt.xticks(rotation=45)
    plt.tight_layout()
    out2 = FIGS / "transformations_over_time.png"
    plt.savefig(out2, dpi=300)
    plt.close()
    print(f"  Wrote {out2}")

    # ── Hypothesis testing ────────────────────────────────────────────────────
    print("\n[7/6] Hypothesis testing")

    # Mann-Whitney U: outlier repos vs. the rest
    # H₀: the two dominant repos are drawn from the same
    #     per-repo transformation-count distribution as the remaining projects.
    print("\n  7a. Do the two largest repos differ from the rest?")
    print("      H₀: no difference in per-repo transformation counts")
    outlier_counts  = per_repo[per_repo.index.isin(outliers)].values
    rest_counts     = per_repo[~per_repo.index.isin(outliers)].values
    mann_whitney(
        outlier_counts, rest_counts,
        label_a=f"outliers ({outlier_names[0]} + {outlier_names[1]})",
        label_b="remaining repos",
    )

    # Kruskal-Wallis across the five most common transformation types
    # H₀: per-repo transformation counts are equal across annotation categories.
    print("\n  7b. Do transformation counts differ across annotation types?")
    print("      H₀: per-commit counts are equal across the top-5 refactoring types")
    top5_types  = df["refactoring_type"].value_counts().head(5).index.tolist()
    kw_groups   = [df[df["refactoring_type"] == t].groupby("commit_id").size().values
                   for t in top5_types]
    kruskal_wallis(kw_groups, [t[:45] for t in top5_types])

    print("\nDone.\n")


if __name__ == "__main__":
    main()
