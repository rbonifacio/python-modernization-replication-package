"""
stats_utils.py
--------------
Shared helpers for non-parametric hypothesis testing across the RQ scripts.

Functions
---------
modified_mann_kendall(series, alpha)
    Hamed-Rao modified Mann-Kendall trend test with formatted console output.

mann_whitney(a, b, label_a, label_b, alpha)
    Two-sided Mann-Whitney U test with rank-biserial effect size.

kruskal_wallis(groups, labels, alpha)
    Kruskal-Wallis H test for k independent groups (k >= 2).

spearman(x, y, label_x, label_y, alpha)
    Spearman rank correlation with console output.

bootstrap_median_ci(values, n_boot, alpha, rng_seed)
    Bootstrap confidence interval for the median of a 1-D array.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as _stats

try:
    import pymannkendall as _mk
    _MK_AVAILABLE = True
except ImportError:
    _MK_AVAILABLE = False

# ── effect-size helpers ───────────────────────────────────────────────────────

def _rank_biserial(u: float, n1: int, n2: int) -> float:
    """Rank-biserial correlation from Mann-Whitney U (common language effect size)."""
    return 1.0 - (2.0 * u) / (n1 * n2)


def _effect_label(r: float) -> str:
    """Rough magnitude label for |rank-biserial r| following Cohen's conventions."""
    r = abs(r)
    if r < 0.1:
        return "negligible"
    if r < 0.3:
        return "small"
    if r < 0.5:
        return "medium"
    return "large"


def _tau_label(tau: float) -> str:
    """Magnitude label for Kendall's τ."""
    t = abs(tau)
    if t < 0.1:
        return "negligible"
    if t < 0.3:
        return "small"
    if t < 0.5:
        return "medium"
    return "large"


def _rho_label(rho: float) -> str:
    """Magnitude label for Spearman's ρ."""
    r = abs(rho)
    if r < 0.1:
        return "negligible"
    if r < 0.3:
        return "small"
    if r < 0.5:
        return "medium"
    return "large"


def _p_str(p: float) -> str:
    if np.isnan(p):
        return "NaN"
    if p < 0.001:
        return "< 0.001"
    return f"{p:.3f}"


# ── public API ────────────────────────────────────────────────────────────────

def modified_mann_kendall(
    series: "np.ndarray | list",
    label: str = "series",
    alpha: float = 0.05,
) -> dict:
    """
    Hamed-Rao modified Mann-Kendall test, which corrects for autocorrelation.
    Falls back to standard Mann-Kendall when pymannkendall is not available.

    Parameters
    ----------
    series : array-like, ordered by time
    label  : human-readable name printed in the summary
    alpha  : significance level

    Returns
    -------
    dict with keys: trend, p, tau, slope, significant
    """
    x = np.asarray(series, dtype=float)

    if not _MK_AVAILABLE:
        print(f"  [WARNING] pymannkendall not installed — using scipy standard MK for '{label}'")
        tau, p = _stats.kendalltau(np.arange(len(x)), x)
        res_dict = dict(trend="increasing" if tau > 0 else "decreasing", p=p, tau=tau, slope=np.nan)
    else:
        res = _mk.hamed_rao_modification_test(x)
        res_dict = dict(trend=res.trend, p=float(res.p), tau=float(res.Tau), slope=float(res.slope))

    res_dict["significant"] = res_dict["p"] < alpha if not np.isnan(res_dict["p"]) else False

    sig = "YES" if res_dict["significant"] else "NO"
    print(f"\n  Mann-Kendall (Hamed-Rao) — {label}")
    print(f"    Trend       : {res_dict['trend']}")
    print(f"    Kendall τ   : {res_dict['tau']:.4f}  ({_tau_label(res_dict['tau'])})")
    print(f"    p-value     : {_p_str(res_dict['p'])}  →  significant at α={alpha}: {sig}")
    print(f"    Sen's slope : {res_dict['slope']:.4f}  transformations/month")

    return res_dict


def mann_whitney(
    a: "np.ndarray | list",
    b: "np.ndarray | list",
    label_a: str = "group A",
    label_b: str = "group B",
    alpha: float = 0.05,
) -> dict:
    """
    Two-sided Mann-Whitney U test (Wilcoxon rank-sum).

    Returns
    -------
    dict with keys: u, p, r (rank-biserial), significant, median_a, median_b
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    u, p = _stats.mannwhitneyu(a, b, alternative="two-sided")
    r = _rank_biserial(u, len(a), len(b))

    sig = "YES" if p < alpha else "NO"
    result = dict(u=u, p=p, r=r, significant=p < alpha,
                  median_a=np.median(a), median_b=np.median(b))

    print(f"\n  Mann-Whitney U — {label_a}  vs.  {label_b}")
    print(f"    n: {len(a):,} vs {len(b):,}   |   medians: {np.median(a):.1f} vs {np.median(b):.1f}")
    print(f"    U statistic : {u:.1f}")
    print(f"    p-value     : {_p_str(p)}  →  significant at α={alpha}: {sig}")
    print(f"    Rank-biserial r = {r:.4f}  ({_effect_label(r)} effect)")

    return result


def kruskal_wallis(
    groups: "list[np.ndarray | list]",
    labels: "list[str]",
    alpha: float = 0.05,
) -> dict:
    """
    Kruskal-Wallis H test for k independent groups.

    Returns
    -------
    dict with keys: h, p, significant
    """
    arrays = [np.asarray(g, dtype=float) for g in groups]
    h, p = _stats.kruskal(*arrays)
    sig = "YES" if p < alpha else "NO"
    result = dict(h=h, p=p, significant=p < alpha)

    print(f"\n  Kruskal-Wallis H test — {len(groups)} groups")
    for lbl, arr in zip(labels, arrays):
        print(f"    {lbl:<45s}: n={len(arr):>6,}  median={np.median(arr):.1f}")
    print(f"    H statistic : {h:.3f}")
    print(f"    p-value     : {_p_str(p)}  →  significant at α={alpha}: {sig}")

    return result


def spearman(
    x: "np.ndarray | list",
    y: "np.ndarray | list",
    label_x: str = "x",
    label_y: str = "y",
    alpha: float = 0.05,
) -> dict:
    """
    Spearman rank correlation.

    Returns
    -------
    dict with keys: rho, p, significant
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    rho, p = _stats.spearmanr(x, y)
    sig = "YES" if p < alpha else "NO"
    result = dict(rho=rho, p=p, significant=p < alpha)

    print(f"\n  Spearman correlation — {label_x}  ~  {label_y}")
    print(f"    n           : {len(x):,}")
    print(f"    ρ           : {rho:.4f}  ({_rho_label(rho)} {'positive' if rho >= 0 else 'negative'})")
    print(f"    p-value     : {_p_str(p)}  →  significant at α={alpha}: {sig}")

    return result


def bootstrap_median_ci(
    values: "np.ndarray | list",
    n_boot: int = 2000,
    alpha: float = 0.05,
    rng_seed: int = 42,
) -> tuple[float, float]:
    """
    Percentile bootstrap CI for the median of *values*.

    Returns
    -------
    (lower, upper) at (alpha/2, 1-alpha/2) confidence level
    """
    rng = np.random.default_rng(rng_seed)
    v = np.asarray(values, dtype=float)
    boot_medians = np.array(
        [np.median(rng.choice(v, size=len(v), replace=True)) for _ in range(n_boot)]
    )
    lo = np.percentile(boot_medians, 100 * alpha / 2)
    hi = np.percentile(boot_medians, 100 * (1 - alpha / 2))
    return float(lo), float(hi)
