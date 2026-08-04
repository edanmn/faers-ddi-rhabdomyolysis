"""The Omega disproportionality measure for drug-drug interaction surveillance.

Reference
---------
Noren GN, Sundberg R, Bate A, Edwards IR. "A statistical methodology for
drug-drug interaction surveillance." Statistics in Medicine 2008;27:3057-3070.

What this measures, and why the naive version is wrong
------------------------------------------------------
For a triple (drug A, drug B, event Z) we have a 2x2x2 table over all reports.
The naive question -- "do A and B co-occur with Z more than chance?" -- compares
the observed triple count against a fully independent model. That flags every
commonly co-prescribed pair, because co-prescription *is* an association, and it
flags any pair where both drugs independently cause the event.

Omega instead compares the observed triple count against the expected count
under the log-linear model containing all three PAIRWISE associations (A-B, A-Z,
B-Z) but NO three-way interaction term, written [AB][AZ][BZ]. That model already
knows A and B are co-prescribed and that each drug is separately associated with
the event. Only genuine synergy beyond those pairwise effects moves Omega.

Omega is a shrunk log2 observed-to-expected ratio,

    Omega = log2((n_111 + alpha) / (E_111 + alpha)),   alpha = 0.5

and the reported statistic is Omega_025, the 2.5th percentile of its posterior.
Treating n_111 as Poisson with a conjugate gamma prior gives a
Gamma(n_111 + alpha, rate = E_111 + alpha) posterior for the ratio, so

    Omega_025 = log2(GammaQuantile(0.025; n_111 + alpha, 1 / (E_111 + alpha)))

The shrinkage is the point: at low counts the posterior is wide and Omega_025 is
pulled below zero, so a handful of co-reports cannot manufacture a signal.
Signal threshold is Omega_025 > 0.

HOW THIS IMPLEMENTATION DEVIATES FROM THE PUBLISHED FORMULA
-----------------------------------------------------------
The [AB][AZ][BZ] model has no closed-form MLE, so the literature uses the
approximation

    E_111 ~= (n_11. * n_1.1 * n_.11) / (n_1.. * n_.1. * n_..1) * n_...

which is exact under full independence and degrades as the pairwise
associations strengthen. `expected_count_closed_form` implements it. On
synthetic tables built from an explicit log-linear model it is accurate to ~4%
when all pairwise log-odds are 0.5, but drifts to >200% error once they reach
2-3 -- the regime real drug/event tables occupy. At that error it produces
negative Omega for tables with no synergy at all and is non-monotonic in true
synergy strength. See tests/test_omega.py::test_closed_form_error_grows_with_association,
which characterises the error rather than tolerating it.

So `expected_count` fits the model exactly by iterative proportional fitting
instead. IPF on a 2x2x2 table converges in microseconds and is vectorised
across pairs here, so the exact fit costs nothing at screen scale. The
approximation is retained only for the methods-section comparison.

Note the full 2x2x2 table is recoverable from the triple count plus the
marginals, so nothing extra needs to be carried through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

ALPHA = 0.5
QUANTILE = 0.025
IPF_ITERATIONS = 500
IPF_TOL = 1e-12


@dataclass(frozen=True)
class Triple:
    """The counts needed for one (drug A, drug B, event) triple.

    Attributes use Noren's dot notation: a `1` is presence on the report, a `.`
    is marginalised over. So n_1_1_1 is reports containing A and B and the
    event; n_1_1_dot is reports containing A and B regardless of event.
    """

    n_1_1_1: float      # A and B and event
    n_1_1_dot: float    # A and B
    n_1_dot_1: float    # A and event
    n_dot_1_1: float    # B and event
    n_1_dot_dot: float  # A
    n_dot_1_dot: float  # B
    n_dot_dot_1: float  # event
    n_total: float      # all reports

    def validate(self) -> None:
        """Reject tables that cannot arise from real data.

        Worth doing eagerly: an off-by-one join that double counts a marginal
        yields a plausible-looking Omega rather than an error. The strongest
        check is that every one of the eight reconstructed cells is
        non-negative -- that catches inconsistencies the pairwise checks miss.
        """
        counts = (
            self.n_1_1_1, self.n_1_1_dot, self.n_1_dot_1, self.n_dot_1_1,
            self.n_1_dot_dot, self.n_dot_1_dot, self.n_dot_dot_1, self.n_total,
        )
        if any(v < 0 for v in counts):
            raise ValueError(f"negative count in {self}")
        cells = full_table(self)
        if np.any(cells < -1e-9):
            raise ValueError(
                f"marginals imply a negative cell count; table is inconsistent: {self}"
            )


def full_table(t: Triple) -> np.ndarray:
    """Reconstruct the 2x2x2 table, indexed [a, b, z] with 1 = present.

    The triple count and the six marginals plus the total determine all eight
    cells exactly, so the pipeline never needs to carry the full table around.
    """
    cells = np.zeros((2, 2, 2), dtype=float)
    cells[1, 1, 1] = t.n_1_1_1
    cells[1, 1, 0] = t.n_1_1_dot - t.n_1_1_1
    cells[1, 0, 1] = t.n_1_dot_1 - t.n_1_1_1
    cells[0, 1, 1] = t.n_dot_1_1 - t.n_1_1_1
    cells[1, 0, 0] = t.n_1_dot_dot - cells[1, 1, 0] - cells[1, 0, 1] - cells[1, 1, 1]
    cells[0, 1, 0] = t.n_dot_1_dot - cells[1, 1, 0] - cells[0, 1, 1] - cells[1, 1, 1]
    cells[0, 0, 1] = t.n_dot_dot_1 - cells[1, 0, 1] - cells[0, 1, 1] - cells[1, 1, 1]
    cells[0, 0, 0] = t.n_total - cells.sum()  # cells[0,0,0] is still zero here
    return cells


def fit_no_three_way(
    tables: np.ndarray, iterations: int = IPF_ITERATIONS, tol: float = IPF_TOL
) -> np.ndarray:
    """Fit [AB][AZ][BZ] by IPF. `tables` is (..., 2, 2, 2); returns fitted tables.

    IPF repeatedly rescales the working table to match each two-way margin in
    turn. Because those three margins are the sufficient statistics of the
    no-three-way model, the fixed point is its MLE. Vectorised over the leading
    axes so a whole screen fits at once.
    """
    tables = np.asarray(tables, dtype=float)
    targets = [(-1, tables.sum(axis=-1)),  # [AB], summing over z
               (-2, tables.sum(axis=-2)),  # [AZ], summing over b
               (-3, tables.sum(axis=-3))]  # [BZ], summing over a
    fitted = np.ones_like(tables)
    previous = fitted[..., 1, 1, 1].copy()
    for iteration in range(iterations):
        for axis, target in targets:
            margin = fitted.sum(axis=axis)
            ratio = np.divide(
                target, margin, out=np.zeros_like(target), where=margin > 0
            )
            fitted = fitted * np.expand_dims(ratio, axis=axis)
        current = fitted[..., 1, 1, 1]
        if iteration and np.all(np.abs(current - previous) <= tol * (1.0 + np.abs(current))):
            break
        previous = current.copy()
    return fitted


def expected_count(t: Triple) -> float:
    """E_111: the exact MLE under [AB][AZ][BZ], via IPF."""
    if t.n_1_dot_dot == 0 or t.n_dot_1_dot == 0 or t.n_dot_dot_1 == 0:
        return float("nan")
    fitted = fit_no_three_way(full_table(t)[None, ...])
    return float(fitted[0, 1, 1, 1])


def expected_count_closed_form(t: Triple) -> float:
    """The published approximation. Retained only for methods-section comparison.

    Do not use for inference -- see the module docstring for measured error.
    """
    denominator = t.n_1_dot_dot * t.n_dot_1_dot * t.n_dot_dot_1
    if denominator == 0:
        return float("nan")
    return (t.n_1_1_dot * t.n_1_dot_1 * t.n_dot_1_1) / denominator * t.n_total


def omega(t: Triple, alpha: float = ALPHA) -> float:
    """Shrunk log2 observed-to-expected ratio (the point estimate)."""
    expected = expected_count(t)
    if not np.isfinite(expected):
        return float("nan")
    return float(np.log2((t.n_1_1_1 + alpha) / (expected + alpha)))


def omega_quantile(t: Triple, q: float = QUANTILE, alpha: float = ALPHA) -> float:
    """Lower credibility bound of Omega. `q=0.025` gives the reported Omega_025."""
    expected = expected_count(t)
    if not np.isfinite(expected):
        return float("nan")
    return float(_omega_quantile_from_counts(t.n_1_1_1, expected, q, alpha))


def omega_interval(
    t: Triple, lower: float = 0.025, upper: float = 0.975, alpha: float = ALPHA
) -> tuple[float, float]:
    return omega_quantile(t, lower, alpha), omega_quantile(t, upper, alpha)


def _omega_quantile_from_counts(observed, expected, q=QUANTILE, alpha=ALPHA):
    shape = np.asarray(observed, dtype=float) + alpha
    rate = np.asarray(expected, dtype=float) + alpha
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log2(stats.gamma.ppf(q, a=shape, scale=1.0 / rate))


# --- vectorised forms, for the Phase 9 screen over ~20k pairs ---------------


def triples_to_tables(
    n_1_1_1, n_1_1_dot, n_1_dot_1, n_dot_1_1,
    n_1_dot_dot, n_dot_1_dot, n_dot_dot_1, n_total,
) -> np.ndarray:
    """Vectorised `full_table`. Returns an (n, 2, 2, 2) array."""
    arrays = [np.asarray(x, dtype=float) for x in (
        n_1_1_1, n_1_1_dot, n_1_dot_1, n_dot_1_1,
        n_1_dot_dot, n_dot_1_dot, n_dot_dot_1,
    )]
    abz, ab, az, bz, a, b, z = arrays
    total = np.broadcast_to(np.asarray(n_total, dtype=float), abz.shape)

    cells = np.zeros(abz.shape + (2, 2, 2), dtype=float)
    cells[..., 1, 1, 1] = abz
    cells[..., 1, 1, 0] = ab - abz
    cells[..., 1, 0, 1] = az - abz
    cells[..., 0, 1, 1] = bz - abz
    cells[..., 1, 0, 0] = a - (ab - abz) - (az - abz) - abz
    cells[..., 0, 1, 0] = b - (ab - abz) - (bz - abz) - abz
    cells[..., 0, 0, 1] = z - (az - abz) - (bz - abz) - abz
    cells[..., 0, 0, 0] = total - cells.sum(axis=(-3, -2, -1))
    return cells


def expected_count_vec(tables: np.ndarray) -> np.ndarray:
    """E_111 for a batch of tables from `triples_to_tables`."""
    tables = np.asarray(tables, dtype=float)
    degenerate = (
        (tables.sum(axis=(-2, -1))[..., 1] == 0)   # no reports with A
        | (tables.sum(axis=(-3, -1))[..., 1] == 0)  # no reports with B
        | (tables.sum(axis=(-3, -2))[..., 1] == 0)  # no reports with the event
    )
    fitted = fit_no_three_way(tables)[..., 1, 1, 1]
    return np.where(degenerate, np.nan, fitted)


def omega_vec(n_1_1_1, expected, alpha: float = ALPHA) -> np.ndarray:
    observed = np.asarray(n_1_1_1, dtype=float)
    expected = np.asarray(expected, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log2((observed + alpha) / (expected + alpha))


def omega_quantile_vec(
    n_1_1_1, expected, q: float = QUANTILE, alpha: float = ALPHA
) -> np.ndarray:
    return _omega_quantile_from_counts(n_1_1_1, expected, q, alpha)


# --- the additive null -----------------------------------------------------
#
# Omega's null is multiplicative on the odds scale: under no interaction the
# association between B and the event is the same within A-exposed and
# A-unexposed reports. That is a reasonable null while the marginal
# associations are weak, and a very demanding one once they are not.
#
# For rhabdomyolysis the drugs of interest ARE the dominant reported causes, so
# marginal RRs run 3-19 and the fitted multiplicative null predicts joint event
# rates of 13-85% among co-reports. (The fit is margin-constrained -- IPF
# reproduces the A-B margin exactly, so the expected count can never exceed the
# number of co-reports. An unconstrained RR product would predict above 100% for
# 4 of the 16 controls, which is itself a sign the scale is wrong, but it is not
# what the model fits.)
#
# Observed rates are high in absolute terms and still fall short of that bar:
# gemfibrozil + simvastatin is 55.1% observed against 72.9% expected. Two agents
# that both strongly cause the same outcome behave sub-multiplicatively as a
# rule, so requiring super-multiplicativity rejects most real interactions.
# Measured across the 16 positive controls, Omega correlates at r = -0.42 with
# log2(RR_A x RR_B): the better established the pair, the more negative it looks.
#
# The additive null asks the public-health question instead -- does the
# combination produce more cases than the sum of the individual excesses?
#
#     P(Z | A and B)  =  P(Z)  +  [P(Z|A) - P(Z)]  +  [P(Z|B) - P(Z)]
#                     =  P(Z|A) + P(Z|B) - P(Z)
#
# which predicts 5.5-27.9% here. Departure from additivity is the standard
# criterion for interaction that matters clinically; departure from
# multiplicativity is a different and much stricter question. The same shrinkage
# is applied to its lower bound, so the two measures differ only in the null.


def additive_expected(t: Triple) -> float:
    """Expected triple count under additivity of excess risk.

    Floored at the larger of the two individual risks, not at zero. When a drug
    is reported with the event LESS often than the database background, its
    excess risk is negative, and two such drugs give
    P(Z|A) + P(Z|B) - P(Z) < 0. Clipping that to zero makes the expected count
    zero, so Omega_add becomes log2(2n + 1) -- unbounded in the observed count.

    The first screen run put DEXAMETHASONE+LENALIDOMIDE at the top of 17,375
    pairs on exactly this: 38,469 co-reports, 53 with the event, an event rate
    of 0.138% against a 0.207% background. A NEGATIVE association scored as the
    strongest signal in the database.

    Flooring at max(risk_a, risk_b) encodes the monotonicity the null should
    have: adding a second drug cannot make the event less likely than the more
    dangerous drug alone. Where both risks exceed baseline -- the case the
    additive model is for -- the floor never binds and the formula is unchanged.
    """
    if t.n_1_dot_dot == 0 or t.n_dot_1_dot == 0 or t.n_total == 0:
        return float("nan")
    risk_a = t.n_1_dot_1 / t.n_1_dot_dot
    risk_b = t.n_dot_1_1 / t.n_dot_1_dot
    baseline = t.n_dot_dot_1 / t.n_total
    joint = max(risk_a + risk_b - baseline, risk_a, risk_b)
    return min(joint, 1.0) * t.n_1_1_dot


def additive_expected_vec(
    n_1_dot_1, n_dot_1_1, n_1_dot_dot, n_dot_1_dot, n_dot_dot_1, n_total, n_1_1_dot
) -> np.ndarray:
    risk_a = np.divide(np.asarray(n_1_dot_1, dtype=float), np.asarray(n_1_dot_dot, dtype=float),
                       out=np.full(np.shape(n_1_dot_1), np.nan),
                       where=np.asarray(n_1_dot_dot) > 0)
    risk_b = np.divide(np.asarray(n_dot_1_1, dtype=float), np.asarray(n_dot_1_dot, dtype=float),
                       out=np.full(np.shape(n_dot_1_1), np.nan),
                       where=np.asarray(n_dot_1_dot) > 0)
    baseline = float(n_dot_dot_1) / float(n_total)
    # Floored at the larger individual risk -- see additive_expected.
    joint = np.minimum(
        np.maximum(np.maximum(risk_a + risk_b - baseline, risk_a), risk_b), 1.0)
    return joint * np.asarray(n_1_1_dot, dtype=float)


def omega_additive(t: Triple, alpha: float = ALPHA) -> float:
    expected = additive_expected(t)
    if not np.isfinite(expected):
        return float("nan")
    return float(np.log2((t.n_1_1_1 + alpha) / (expected + alpha)))


def omega_additive_quantile(
    t: Triple, q: float = QUANTILE, alpha: float = ALPHA
) -> float:
    expected = additive_expected(t)
    if not np.isfinite(expected):
        return float("nan")
    return float(_omega_quantile_from_counts(t.n_1_1_1, expected, q, alpha))
