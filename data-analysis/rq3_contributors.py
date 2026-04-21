"""
rq3_contributors.py
-------------------
Analyses the concentration of contributors responsible for Python modernization
transformations across the projects in final_ds.csv.

Research question: Is a small fraction of contributors responsible for the
majority of transformations? (Pareto / Gini analysis)

Outputs
-------
tables/contributor_concentration.tex  – per-project Pareto summary table
tables/contributor_stats.csv          – full per-project statistics
figures/contributor_lorenz.pdf        – Lorenz curves (one per project, sampled)
figures/contributor_pareto_global.pdf – global Pareto chart
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stats_utils import spearman, bootstrap_median_ci

# ── paths ─────────────────────────────────────────────────────────────────────
BASE  = Path(__file__).parent.parent
DATA  = BASE / "dataset" / "final_ds.csv"
FIGS  = BASE / "figures"
TABS  = BASE / "tables"
FIGS.mkdir(exist_ok=True)
TABS.mkdir(exist_ok=True)


# ── helper: Gini coefficient ──────────────────────────────────────────────────
def gini(values: np.ndarray) -> float:
    v = np.sort(values)
    n = len(v)
    if n == 0 or v.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * (idx * v).sum() / (n * v.sum())) - (n + 1) / n)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("RQ3 — Contributor concentration analysis")
    print("=" * 65)

    print("\n[1/4] Loading dataset …")
    df = pd.read_csv(DATA, dtype=str)
    print(f"      {len(df):,} rows, {df['project_name'].nunique()} projects")

    # Author identity: email address, with display name as fallback.
    email = df["author_email"].fillna("").str.strip()
    name  = df["author_name"].fillna("").str.strip()
    df["author"] = email.where(email != "", name)

    print(f"      Unique authors (global)  : {df['author'].nunique():,}")
    print(f"      Author–project pairs     : {df.groupby(['project_name', 'author']).ngroups:,}")

    # ── Per-project concentration stats ──────────────────────────────────────
    print("\n[2/4] Computing per-project concentration statistics …")
    print("      For each project we report:")
    print("        transformations  – total transformation count")
    print("        contributors     – distinct author identities")
    print("        n_for_80pct      – minimum #contributors covering 80% of transformations")
    print("        pct_n_for_80pct  – n_for_80pct as % of all contributors")
    print("        top1/3/5_pct     – share of transformations by top 1/3/5 contributors")
    print("        gini             – Gini coefficient (0=equal, 1=maximally concentrated)")

    rows = []
    for project, grp in df.groupby("project_name"):
        counts = grp.groupby("author").size().sort_values(ascending=False)
        total  = counts.sum()
        n_contributors = len(counts)

        cumulative = counts.cumsum()
        n_for_80   = int((cumulative / total < 0.80).sum()) + 1
        pct_for_80 = 100.0 * n_for_80 / n_contributors

        top1_pct = 100.0 * counts.iloc[0] / total
        top3_pct = 100.0 * counts.iloc[:3].sum() / total
        top5_pct = 100.0 * counts.iloc[:5].sum() / total
        g        = gini(counts.values.astype(float))

        rows.append({
            "project":          project,
            "transformations":  total,
            "contributors":     n_contributors,
            "n_for_80pct":      n_for_80,
            "pct_n_for_80pct":  round(pct_for_80, 1),
            "top1_pct":         round(top1_pct, 1),
            "top3_pct":         round(top3_pct, 1),
            "top5_pct":         round(top5_pct, 1),
            "gini":             round(g, 3),
        })

    stats = pd.DataFrame(rows).sort_values("transformations", ascending=False)

    print("\n  Top-10 projects by transformation volume:")
    print(stats.head(10).to_string(index=False))

    # ── Global summary ────────────────────────────────────────────────────────
    print("\n[3/4] Global summary (across all projects) …")
    print("      Statistics are computed across all projects.")

    med_gini    = stats["gini"].median()
    n_gini_80   = (stats["gini"] > 0.8).sum()
    pct_gini_80 = 100 * (stats["gini"] > 0.8).mean()
    med_top1    = stats["top1_pct"].median()
    med_top3    = stats["top3_pct"].median()
    med_top5    = stats["top5_pct"].median()
    n_top1_50   = (stats["top1_pct"] > 50).sum()
    pct_top1_50 = 100 * (stats["top1_pct"] > 50).mean()
    n_top1_75   = (stats["top1_pct"] > 75).sum()
    med_pct80   = stats["pct_n_for_80pct"].median()
    n_pct80_10  = (stats["pct_n_for_80pct"] <= 10).sum()
    pct_pct80_10 = 100 * (stats["pct_n_for_80pct"] <= 10).mean()

    print(f"\n  Median Gini coefficient                     : {med_gini:.3f}")
    print(f"  Projects with Gini > 0.8                    : {n_gini_80} ({pct_gini_80:.0f}%)")
    print(f"  Median top-1 contributor share              : {med_top1:.1f}%")
    print(f"  Median top-3 contributor share              : {med_top3:.1f}%")
    print(f"  Median top-5 contributor share              : {med_top5:.1f}%")
    print(f"  Projects where top-1 contributor > 50%      : {n_top1_50} ({pct_top1_50:.0f}%)")
    print(f"  Projects where top-1 contributor > 75%      : {n_top1_75}")
    print(f"  Median % of contributors needed for 80%     : {med_pct80:.1f}%")
    print(f"  Projects where ≤10% of contributors reach 80%: {n_pct80_10} ({pct_pct80_10:.0f}%)")

    # ── LaTeX table ──────────────────────────────────────────────────────────
    tex = stats.head(20).copy()
    tex["transformations"] = tex["transformations"].map(lambda x: f"\\num{{{x}}}")
    tex_out = tex[["project", "transformations", "contributors",
                   "n_for_80pct", "pct_n_for_80pct", "gini"]].rename(columns={
        "project":         "Project",
        "transformations": "Transformations",
        "contributors":    "Contributors",
        "n_for_80pct":     r"$n_{80\%}$",
        "pct_n_for_80pct": r"$\%_{80\%}$",
        "gini":            "Gini",
    })
    latex = tex_out.to_latex(
        index=False, escape=False,
        caption=(
            "Contributor concentration per project (top-20 by transformations). "
            r"$n_{80\%}$ is the minimum number of contributors covering 80\% of "
            "transformations; "
            r"$\%_{80\%}$ is that count as a percentage of all contributors."
        ),
        label="tab:contributor-concentration",
        column_format="lrrrrr",
    )
    (TABS / "contributor_concentration.tex").write_text(latex)
    print(f"\n  Wrote {TABS / 'contributor_concentration.tex'}")

    stats.to_csv(TABS / "contributor_stats.csv", index=False)
    print(f"  Wrote {TABS / 'contributor_stats.csv'}")

    # ── Global Pareto chart ───────────────────────────────────────────────────
    print("\n[4/4] Generating figures …")

    global_counts = (
        df.groupby(["project_name", "author"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )
    n_pairs = len(global_counts)
    global_counts["cumulative_pct"]  = 100.0 * global_counts["count"].cumsum() / global_counts["count"].sum()
    global_counts["contributor_pct"] = 100.0 * (global_counts.index + 1) / n_pairs
    pareto_cutoff = global_counts.loc[global_counts["cumulative_pct"] >= 80, "contributor_pct"].iloc[0]

    print(f"\n  Global Pareto chart:")
    print(f"    Author–project pairs total       : {n_pairs:,}")
    print(f"    Pairs needed to reach 80% share  : {pareto_cutoff:.1f}%")
    print(f"    X-axis: cumulative % of pairs ranked by transformation count (most → least)")
    print(f"    Y-axis: cumulative % of all transformations covered")
    print(f"    Red dashed lines mark the 80% threshold.")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(global_counts["contributor_pct"], global_counts["cumulative_pct"], lw=1.5)
    ax.axhline(80, color="red", ls="--", lw=0.8, label="80 %")
    ax.axvline(pareto_cutoff, color="red", ls="--", lw=0.8)
    ax.set_xlabel("Cumulative % of contributor–project pairs (ranked by transformations)")
    ax.set_ylabel("Cumulative % of transformations")
    ax.set_title("Global Pareto: contributor vs. transformation share")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGS / "contributor_pareto_global.pdf")
    plt.close()
    print(f"\n  Wrote {FIGS / 'contributor_pareto_global.pdf'}")

    # ── Lorenz curves ────────────────────────────────────────────────────────
    sample_projects = stats.nlargest(9, "transformations")["project"].tolist()
    print(f"\n  Lorenz curves for top-9 projects by transformations:")
    print(f"    Projects : {', '.join(sample_projects)}")
    print(f"    Each sub-plot shows contributor inequality within a project.")
    print(f"    The diagonal dashed line represents perfect equality.")
    print(f"    Gini coefficient shown in each sub-title (higher = more concentrated).")

    fig, axes = plt.subplots(3, 3, figsize=(11, 9))
    for ax, project in zip(axes.flat, sample_projects):
        grp    = df[df["project_name"] == project]
        counts = np.sort(grp.groupby("author").size().values.astype(float))
        n      = len(counts)
        lorenz_x = np.linspace(0, 100, n)
        lorenz_y = 100.0 * counts.cumsum() / counts.sum()
        ax.plot(lorenz_x, lorenz_y, lw=1.5)
        ax.plot([0, 100], [0, 100], "k--", lw=0.7, label="Equality")
        g = gini(counts)
        ax.set_title(f"{project}\n(Gini={g:.2f})", fontsize=8)
        ax.set_xlabel("% contributors", fontsize=7)
        ax.set_ylabel("% transformations", fontsize=7)
    fig.suptitle("Lorenz curves – contributor inequality per project", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGS / "contributor_lorenz.pdf")
    plt.close()
    print(f"  Wrote {FIGS / 'contributor_lorenz.pdf'}")

    # ── Hypothesis testing ────────────────────────────────────────────────────
    print("\n[5/4] Hypothesis testing")

    # Spearman: number of contributors ~ total transformations per project
    print("\n  5a. Does contributor count correlate with transformation volume?")
    print("      H₀: ρ = 0  (no monotonic relationship)")
    spearman(
        stats["contributors"].values,
        stats["transformations"].values,
        label_x="contributors per project",
        label_y="transformations per project",
    )

    # Spearman: top-1 contributor share ~ Gini
    # A sanity check: projects where one person dominates should have high Gini.
    print("\n  5b. Does top-1 contributor share correlate with Gini coefficient?")
    print("      H₀: ρ = 0  (sanity check — expected strong positive correlation)")
    spearman(
        stats["top1_pct"].values,
        stats["gini"].values,
        label_x="top-1 contributor share (%)",
        label_y="Gini coefficient",
    )

    # Bootstrap CI for the median Gini across projects
    print("\n  5c. Bootstrap 95% CI for the median Gini coefficient (2 000 resamples)")
    lo, hi = bootstrap_median_ci(stats["gini"].values, n_boot=2000)
    med    = stats["gini"].median()
    print(f"      Median Gini : {med:.3f}  (95% CI: [{lo:.3f}, {hi:.3f}])")

    # Bootstrap CI for the median % of contributors needed for 80% of transformations
    print("\n  5d. Bootstrap 95% CI for median % of contributors covering 80% of work")
    lo2, hi2 = bootstrap_median_ci(stats["pct_n_for_80pct"].values, n_boot=2000)
    med2     = stats["pct_n_for_80pct"].median()
    print(f"      Median pct_80 : {med2:.1f}%  (95% CI: [{lo2:.1f}%, {hi2:.1f}%])")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
