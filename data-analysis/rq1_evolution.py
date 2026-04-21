"""
rq1_evolution.py
----------------
Answers RQ1 (part 2): Evolution of type-annotation transformations over time,
split by production vs. test code.

Inputs
------
dataset/final_ds.csv

Outputs
-------
figures/transformations_over_time_prod_vs_test.png  – monthly trend (raw + 3-month rolling average)
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from stats_utils import modified_mann_kendall

# ── paths ─────────────────────────────────────────────────────────────────────
BASE    = Path(__file__).parent.parent
DATA    = BASE / "dataset" / "final_ds.csv"
FIGS    = BASE / "figures"
FIGS.mkdir(exist_ok=True)

OUT_FIG  = FIGS / "transformations_over_time_prod_vs_test.png"
CUTOFF   = pd.Timestamp("2026-03-01", tz="UTC")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("RQ1 — Temporal evolution of type-annotation transformations")
    print("=" * 65)

    print("\n[1/3] Loading dataset …")
    df = pd.read_csv(DATA, dtype=str)
    print(f"      {len(df):,} rows loaded")

    print("\n[2/3] Parsing and filtering dates …")
    df["commit_time"] = pd.to_datetime(df["commit_time"], errors="coerce", utc=True)
    before_cutoff = len(df)
    df = df[df["commit_time"] < CUTOFF]
    print(f"      Rows after cutoff ({CUTOFF.date()}): {len(df):,}  "
          f"(removed {before_cutoff - len(df):,})")

    invalid_dates = df["commit_time"].isna().sum()
    if invalid_dates:
        print(f"      Dropping {invalid_dates:,} rows with invalid commit_time")
        df = df.dropna(subset=["commit_time"])

    df["is_test_code"] = df["is_test_code"].fillna("unknown").str.strip().str.lower()
    valid_categories   = {"production", "test"}
    unexpected = sorted(set(df["is_test_code"]) - valid_categories)
    if unexpected:
        print(f"      Warning: unexpected is_test_code values: {unexpected}")
        df = df[df["is_test_code"].isin(valid_categories)]

    df["month_year"] = df["commit_time"].dt.to_period("M")

    print("\n[3/3] Aggregating monthly counts and plotting …")
    monthly = (
        df.groupby(["month_year", "is_test_code"])
        .size()
        .reset_index(name="Total")
    )
    monthly_wide = (
        monthly
        .pivot(index="month_year", columns="is_test_code", values="Total")
        .fillna(0)
        .sort_index()
    )
    for col in ["production", "test"]:
        if col not in monthly_wide.columns:
            monthly_wide[col] = 0
    monthly_wide = monthly_wide[["production", "test"]]
    monthly_wide.index = monthly_wide.index.to_timestamp()

    monthly_wide["production_smooth"] = monthly_wide["production"].rolling(window=3, min_periods=1).mean()
    monthly_wide["test_smooth"]       = monthly_wide["test"].rolling(window=3, min_periods=1).mean()

    date_range_start = monthly_wide.index.min().strftime("%Y-%m")
    date_range_end   = monthly_wide.index.max().strftime("%Y-%m")
    peak_prod_month  = monthly_wide["production"].idxmax().strftime("%Y-%m")
    peak_test_month  = monthly_wide["test"].idxmax().strftime("%Y-%m")

    print(f"\n  Figure data summary:")
    print(f"    Date range        : {date_range_start} to {date_range_end} ({len(monthly_wide)} months)")
    print(f"    Total production  : {int(monthly_wide['production'].sum()):,} transformations")
    print(f"    Total test        : {int(monthly_wide['test'].sum()):,} transformations")
    print(f"    Prod/test ratio   : {monthly_wide['production'].sum() / monthly_wide['test'].sum():.1f}x")
    print(f"    Peak prod month   : {peak_prod_month} ({int(monthly_wide['production'].max()):,} transformations)")
    print(f"    Peak test month   : {peak_test_month} ({int(monthly_wide['test'].max()):,} transformations)")
    print(f"    Mean prod/month   : {monthly_wide['production'].mean():.1f}")
    print(f"    Mean test/month   : {monthly_wide['test'].mean():.1f}")
    print(f"    Activity 2015–2018: "
          f"{int(monthly_wide.loc[monthly_wide.index < '2019-01-01', 'production'].sum()):,} prod, "
          f"{int(monthly_wide.loc[monthly_wide.index < '2019-01-01', 'test'].sum()):,} test")
    print(f"    Activity 2022+    : "
          f"{int(monthly_wide.loc[monthly_wide.index >= '2022-01-01', 'production'].sum()):,} prod, "
          f"{int(monthly_wide.loc[monthly_wide.index >= '2022-01-01', 'test'].sum()):,} test")
    print(f"    Lines: raw monthly counts (alpha=0.35) + 3-month rolling average (solid)")

    plt.figure(figsize=(10, 5))
    plt.plot(monthly_wide.index, monthly_wide["production"],        alpha=0.35, label="Production (monthly)")
    plt.plot(monthly_wide.index, monthly_wide["test"],              alpha=0.35, label="Test (monthly)")
    plt.plot(monthly_wide.index, monthly_wide["production_smooth"], linewidth=2, label="Production (3-month rolling avg)")
    plt.plot(monthly_wide.index, monthly_wide["test_smooth"],       linewidth=2, label="Test (3-month rolling avg)")
    plt.xlabel("Month")
    plt.ylabel("Number of transformations")
    plt.title("Evolution of transformations over time")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG, dpi=300)
    plt.close()
    print(f"\n  Wrote {OUT_FIG}")

    monthly_wide.tail(124).to_csv(BASE / "monthly_tail.csv")

    # ── Hypothesis testing: Mann-Kendall trend test ───────────────────────────
    print("\n[4/3] Hypothesis testing: monotonic trend in monthly transformation counts")
    print("      H₀: no monotonic trend over time")
    print("      Test: Hamed-Rao modified Mann-Kendall (corrects for autocorrelation)")

    modified_mann_kendall(
        monthly_wide["production"].values,
        label="production code (monthly)",
    )
    modified_mann_kendall(
        monthly_wide["test"].values,
        label="test code (monthly)",
    )

    print("\nDone.\n")


if __name__ == "__main__":
    main()
