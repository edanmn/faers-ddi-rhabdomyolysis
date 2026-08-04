"""Interval estimation and dependence-aware significance testing.

Two problems with the first version of this analysis, both raised in review:

**No confidence intervals.** Every figure was a point estimate. A sensitivity of
12/14 is 86% with a 95% interval of 62-97%; quoting 86% alone overstates what
fourteen controls can establish.

**Binomial tests assumed independence that does not hold.** With 200 drugs, each
drug sits in 199 pairs, so pair-level outcomes are strongly dependent -- the
statin-confounding result is a direct demonstration of that dependence, where
one drug drives the signal of every pair it belongs to. A binomial test treats
17,375 pairs as 17,375 independent trials and returns p-values that are far too
small.

The permutation test here preserves the pair graph and the observed signal
pattern, and randomises only the drug-level annotation. Under its null, the same
number of drugs is "implicated" but which drugs is random, so any enrichment
attributable to a handful of high-degree drugs is reproduced in the null rather
than counted as evidence.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def proportion_ci(successes: int, trials: int, level: float = 0.95) -> tuple[float, float]:
    """Jeffreys interval. Behaves sensibly at 0 and at n, unlike Wald."""
    if trials == 0:
        return (float("nan"), float("nan"))
    alpha = 1 - level
    lower = stats.beta.ppf(alpha / 2, successes + 0.5, trials - successes + 0.5)
    upper = stats.beta.ppf(1 - alpha / 2, successes + 0.5, trials - successes + 0.5)
    return (0.0 if successes == 0 else float(lower),
            1.0 if successes == trials else float(upper))


def rule_of_three_upper(trials: int, level: float = 0.95) -> float:
    """Upper bound on a rate after observing zero events in `trials`.

    Needed because the era-stability filter admits no negative controls at all.
    A zero numerator carries no information about how much below the bound the
    true rate lies, so the bound is what must be reported.
    """
    return -np.log(1 - level) / trials if trials else float("nan")


def ratio_ci(
    successes_a: int, trials_a: int, successes_b: int, trials_b: int,
    level: float = 0.95,
) -> tuple[float, float]:
    """Interval for a ratio of two proportions, on the log scale.

    Used for enrichment, which is a ratio of two rates each carrying its own
    uncertainty. Reporting enrichment as a bare point estimate hides that the
    denominator is estimated too.
    """
    if not (successes_a and successes_b and trials_a and trials_b):
        return (float("nan"), float("nan"))
    rate_a, rate_b = successes_a / trials_a, successes_b / trials_b
    log_ratio = np.log(rate_a / rate_b)
    se = np.sqrt(1 / successes_a - 1 / trials_a + 1 / successes_b - 1 / trials_b)
    z = stats.norm.ppf(1 - (1 - level) / 2)
    return float(np.exp(log_ratio - z * se)), float(np.exp(log_ratio + z * se))


def correlation_with_ci(
    x: np.ndarray, y: np.ndarray, level: float = 0.95
) -> dict:
    """Pearson r with a Fisher-z interval and a p-value.

    The manuscript originally reported r = -0.42 across the positive controls
    with no n, interval or p. On n = 16 that correlation is not significant
    (p = 0.105) and its interval includes zero, so it cannot carry the claim it
    was asked to carry.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = len(x)
    r, p = stats.pearsonr(x, y)
    z = np.arctanh(r)
    se = 1 / np.sqrt(n - 3)
    critical = stats.norm.ppf(1 - (1 - level) / 2)
    lower, upper = np.tanh([z - critical * se, z + critical * se])
    return {"r": float(r), "n": int(n), "p_value": float(p),
            "ci_low": float(lower), "ci_high": float(upper),
            "significant": bool(p < 0.05)}


def drug_level_permutation_test(
    pairs: list[tuple[str, str]],
    signalled: list[bool],
    implicated: set[str],
    n_permutations: int = 10_000,
    seed: int = 0,
) -> dict:
    """Is the signal rate among implicated-implicated pairs above chance?

    Null: the same NUMBER of drugs is implicated, but which ones is random. The
    pair graph and the observed signal pattern are held fixed, so enrichment
    produced by a few high-degree or high-signal drugs appears in the null too.

    This is the dependence-aware replacement for the binomial test. A binomial
    test on the same data treats every pair as an independent trial and is
    anticonservative by orders of magnitude.
    """
    rng = np.random.default_rng(seed)
    drugs = sorted({d for pair in pairs for d in pair})
    index = {d: i for i, d in enumerate(drugs)}
    left = np.array([index[a] for a, _ in pairs])
    right = np.array([index[b] for _, b in pairs])
    signal = np.asarray(signalled, dtype=bool)

    def enrichment(flags: np.ndarray) -> float:
        both = flags[left] & flags[right]
        neither = ~flags[left] & ~flags[right]
        if both.sum() == 0 or neither.sum() == 0:
            return np.nan
        rate_both = signal[both].mean()
        rate_neither = signal[neither].mean()
        return rate_both / rate_neither if rate_neither > 0 else np.nan

    observed_flags = np.array([d in implicated for d in drugs])
    observed = enrichment(observed_flags)

    k = int(observed_flags.sum())
    null = np.empty(n_permutations)
    for i in range(n_permutations):
        flags = np.zeros(len(drugs), dtype=bool)
        flags[rng.choice(len(drugs), size=k, replace=False)] = True
        null[i] = enrichment(flags)

    finite = null[np.isfinite(null)]
    # +1 in numerator and denominator: the observed value is one of the possible
    # arrangements, so a permutation p-value can never legitimately be zero.
    p_value = (1 + int((finite >= observed).sum())) / (1 + len(finite))
    return {
        "observed_enrichment": float(observed),
        "null_median": float(np.median(finite)),
        "null_p95": float(np.percentile(finite, 95)),
        "p_value": float(p_value),
        "n_permutations": int(len(finite)),
        "n_implicated_drugs": k,
        "n_drugs": len(drugs),
    }


def leave_one_out_selection(
    additive_recovered: list[bool], multiplicative_recovered: list[bool]
) -> dict:
    """Honest recovery estimate when the estimand was chosen on these controls.

    The additive null was adopted because it recovered more positive controls
    than the multiplicative one, and recovery on those same controls was then
    reported as validation. That is selection on the evaluation set.

    The selection decision is binary, so it can be cross-validated: for each
    control, choose the null using only the other fifteen, then score the
    held-out control under that choice. If the same null wins in every fold, the
    decision is stable and the leave-one-out recovery is an honest out-of-sample
    estimate rather than an in-sample fit.
    """
    additive = np.asarray(additive_recovered, dtype=bool)
    multiplicative = np.asarray(multiplicative_recovered, dtype=bool)
    n = len(additive)

    held_out_correct, chose_additive = [], []
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        pick_additive = additive[mask].sum() >= multiplicative[mask].sum()
        chose_additive.append(bool(pick_additive))
        held_out_correct.append(bool(additive[i] if pick_additive else multiplicative[i]))

    return {
        "n_folds": n,
        "folds_selecting_additive": int(sum(chose_additive)),
        "selection_is_stable": bool(all(chose_additive) or not any(chose_additive)),
        "loo_recovered": int(sum(held_out_correct)),
        "loo_recovery_rate": float(np.mean(held_out_correct)),
        "in_sample_recovered": int(additive.sum()),
        "optimism": float(additive.mean() - np.mean(held_out_correct)),
    }


def mantel_haenszel_ratio(
    signalled: list[bool], documented: list[bool], counts: list[float],
    n_strata: int = 10,
) -> dict:
    """Risk ratio stratified by co-report count.

    Label-documented pairs are co-reported far more often than undocumented
    ones (median 202 vs 69, Mann-Whitney p = 2e-75). Co-report count drives
    statistical power directly, so a crude comparison of signal rates confounds
    "documented" with "well powered". Stratifying on it removes that.
    """
    signalled = np.asarray(signalled, dtype=bool)
    documented = np.asarray(documented, dtype=bool)
    counts = np.asarray(counts, dtype=float)
    edges = np.quantile(counts, np.linspace(0, 1, n_strata + 1))

    numerator = denominator = 0.0
    used = 0
    for i in range(n_strata):
        lo, hi = edges[i], edges[i + 1]
        inside = (counts >= lo) & ((counts < hi) if i < n_strata - 1 else (counts <= hi))
        if inside.sum() < 20:
            continue
        exposed = inside & documented
        unexposed = inside & ~documented
        if not exposed.sum() or not unexposed.sum():
            continue
        total = inside.sum()
        numerator += signalled[exposed].sum() * unexposed.sum() / total
        denominator += signalled[unexposed].sum() * exposed.sum() / total
        used += 1
    return {
        "ratio": round(float(numerator / denominator), 3) if denominator else None,
        "n_strata_used": used,
    }


def mantel_haenszel_bootstrap(
    pairs, signalled, documented, counts, n_boot: int = 2000,
    n_strata: int = 10, seed: int = 0,
) -> dict:
    """Cluster-bootstrap interval for the stratified ratio, resampling DRUGS.

    Resampling pairs would treat 130k pairs as independent units when each drug
    appears in hundreds of them, understating uncertainty. Resampling drugs and
    taking the induced pairs respects that dependence, at the cost of a wider
    and more honest interval.
    """
    rng = np.random.default_rng(seed)
    signalled = np.asarray(signalled, dtype=bool)
    documented = np.asarray(documented, dtype=bool)
    counts = np.asarray(counts, dtype=float)

    drugs = sorted({d for pair in pairs for d in pair})
    index = {d: i for i, d in enumerate(drugs)}
    left = np.array([index[a] for a, _ in pairs])
    right = np.array([index[b] for _, b in pairs])

    point = mantel_haenszel_ratio(signalled, documented, counts, n_strata)["ratio"]
    estimates = []
    for _ in range(n_boot):
        keep = np.zeros(len(drugs), dtype=bool)
        keep[rng.choice(len(drugs), size=len(drugs), replace=True)] = True
        mask = keep[left] & keep[right]
        if mask.sum() < 100 or documented[mask].sum() < 5:
            continue
        value = mantel_haenszel_ratio(
            signalled[mask], documented[mask], counts[mask], n_strata)["ratio"]
        if value is not None and np.isfinite(value):
            estimates.append(value)

    if len(estimates) < 100:
        return {"ratio": point, "ci": None, "n_boot_effective": len(estimates)}
    lower, upper = np.percentile(estimates, [2.5, 97.5])
    return {
        "ratio": round(float(point), 3),
        "ci": [round(float(lower), 3), round(float(upper), 3)],
        "n_boot_effective": len(estimates),
        "excludes_unity": bool(lower > 1.0 or upper < 1.0),
    }


def cluster_proportion_ci(successes: list[bool], clusters: list[str],
                          n_boot: int = 20_000, seed: int = 0,
                          level: float = 0.95) -> dict:
    """Bootstrap interval for a proportion whose trials are clustered.

    The 16 positive controls are not 16 independent trials: they are 5 victim
    drugs paired with 8 perpetrators, and simvastatin alone accounts for 7 of
    them. A Jeffreys binomial interval assumes independence and is therefore too
    narrow -- 62-97% against 50-100% when the victim drug is resampled instead.

    This is the same correction already applied to the screen enrichment via
    `mantel_haenszel_bootstrap`, which resamples drugs rather than pairs. Using
    the clustered interval there and the naive one here was two standards for
    one dependence structure.
    """
    successes = np.asarray(successes, dtype=bool)
    clusters = np.asarray(clusters)
    names = sorted(set(clusters.tolist()))
    if not len(successes):
        return {"n": 0, "n_clusters": 0}
    grouped = [successes[clusters == name] for name in names]

    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(grouped), size=len(grouped))
        draws[i] = np.concatenate([grouped[j] for j in pick]).mean()

    tail = (1 - level) / 2
    naive_lo, naive_hi = proportion_ci(int(successes.sum()), len(successes), level)
    return {
        "n": int(len(successes)),
        "n_clusters": len(names),
        "recovered": int(successes.sum()),
        "rate": round(float(successes.mean()), 4),
        "cluster_ci": [round(float(np.percentile(draws, 100 * tail)), 4),
                       round(float(np.percentile(draws, 100 * (1 - tail))), 4)],
        "naive_binomial_ci_ANTICONSERVATIVE": [round(naive_lo, 4), round(naive_hi, 4)],
        "largest_cluster_share": round(
            max(len(g) for g in grouped) / len(successes), 4),
    }
