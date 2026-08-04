"""Invariant tests for the Omega DDI measure.

Three tests carry most of the weight:

  test_no_synergy_gives_omega_exactly_zero -- a table generated from a
    log-linear model with strong pairwise associations but no three-way term
    must give Omega = 0. This is the entire claim of the method.

  test_naive_measure_fires_where_omega_does_not -- the same table, scored the
    way a naive independence comparison would score it, produces a large false
    signal. This is why the method is needed.

  test_closed_form_error_grows_with_association -- characterises how far the
    published closed-form approximation drifts from the exact fit. It documents
    the error rather than tolerating it, and is the basis for the methods-section
    note explaining why this implementation uses IPF instead.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from faers_ddi import omega as om


# --- helpers ---------------------------------------------------------------


def loglinear_table(
    lam_a=0.0, lam_b=0.0, lam_z=0.0, lam_ab=0.0, lam_az=0.0, lam_bz=0.0, lam_abz=0.0,
    n_total=10_000_000,
) -> np.ndarray:
    """A 2x2x2 count table drawn from an explicit log-linear model.

    Indices are [a, b, z] with 0 = absent, 1 = present. Setting lam_abz = 0
    produces a table with NO three-way interaction, whatever the pairwise terms.
    """
    logits = np.zeros((2, 2, 2))
    for a, b, z in itertools.product((0, 1), repeat=3):
        logits[a, b, z] = (
            lam_a * a + lam_b * b + lam_z * z
            + lam_ab * a * b + lam_az * a * z + lam_bz * b * z
            + lam_abz * a * b * z
        )
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum()
    return probabilities * n_total


def triple_from_table(table: np.ndarray) -> om.Triple:
    return om.Triple(
        n_1_1_1=table[1, 1, 1],
        n_1_1_dot=table[1, 1, :].sum(),
        n_1_dot_1=table[1, :, 1].sum(),
        n_dot_1_1=table[:, 1, 1].sum(),
        n_1_dot_dot=table[1, :, :].sum(),
        n_dot_1_dot=table[:, 1, :].sum(),
        n_dot_dot_1=table[:, :, 1].sum(),
        n_total=table.sum(),
    )


def naive_independent_expected(t: om.Triple) -> float:
    """The comparison the guide's plain-language description implies.

    Assumes A, B and the event are mutually independent, so it cannot tell
    co-prescription apart from synergy.
    """
    return (
        t.n_1_dot_dot * t.n_dot_1_dot * t.n_dot_dot_1 / (t.n_total * t.n_total)
    )


NO_SYNERGY_CASES = [
    (2.0, 1.5, 1.5),   # heavily co-prescribed, both drugs linked to the event
    (3.0, 2.0, 1.0),   # near-always co-prescribed
    (1.0, 2.5, 2.5),   # both strongly linked to the event
    (0.0, 2.0, 2.0),   # not co-prescribed, both linked to the event
    (0.5, 0.5, 0.5),   # weak associations throughout
]


# --- table reconstruction --------------------------------------------------


@pytest.mark.parametrize("lam_ab,lam_az,lam_bz", NO_SYNERGY_CASES)
def test_full_table_round_trips_through_the_marginals(lam_ab, lam_az, lam_bz):
    """The eight cells must be recoverable from the triple count and margins."""
    table = loglinear_table(
        lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
        lam_ab=lam_ab, lam_az=lam_az, lam_bz=lam_bz,
    )
    np.testing.assert_allclose(om.full_table(triple_from_table(table)), table, rtol=1e-9)


# --- the core claim --------------------------------------------------------


@pytest.mark.parametrize("lam_ab,lam_az,lam_bz", NO_SYNERGY_CASES)
def test_no_synergy_gives_omega_exactly_zero(lam_ab, lam_az, lam_bz):
    table = loglinear_table(
        lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
        lam_ab=lam_ab, lam_az=lam_az, lam_bz=lam_bz, lam_abz=0.0,
    )
    t = triple_from_table(table)
    t.validate()
    # The no-three-way model fits such a table perfectly, so the fitted count
    # must equal the observed count and Omega must vanish.
    assert om.expected_count(t) == pytest.approx(t.n_1_1_1, rel=1e-6)
    assert om.omega(t) == pytest.approx(0.0, abs=1e-6)


def test_naive_measure_fires_where_omega_does_not():
    """Same no-synergy table: the naive comparison produces a large false signal."""
    table = loglinear_table(
        lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
        lam_ab=3.0, lam_az=2.0, lam_bz=1.0, lam_abz=0.0,
    )
    t = triple_from_table(table)
    naive = np.log2(t.n_1_1_1 / naive_independent_expected(t))
    assert naive > 2.0, "expected the naive measure to be badly misled here"
    assert om.omega(t) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("lam_abz", [0.5, 1.0, 2.0])
def test_true_synergy_is_detected(lam_abz):
    table = loglinear_table(
        lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
        lam_ab=1.0, lam_az=1.0, lam_bz=1.0, lam_abz=lam_abz,
    )
    t = triple_from_table(table)
    assert om.omega(t) > 0.2
    assert om.omega_quantile(t) > 0.0


def test_omega_is_positive_for_any_synergy_and_zero_without_it():
    values = {}
    for lam_abz in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0):
        table = loglinear_table(
            lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
            lam_ab=1.0, lam_az=1.0, lam_bz=1.0, lam_abz=lam_abz,
        )
        values[lam_abz] = om.omega(triple_from_table(table))
    assert values[0.0] == pytest.approx(0.0, abs=1e-6)
    assert all(v > 0.0 for lam, v in values.items() if lam > 0.0)


def test_omega_is_not_monotonic_in_the_loglinear_interaction_parameter():
    """A documented caveat, not a defect -- Omega ranks signals, it is not an
    effect size on the log-odds scale.

    Raising lambda_abz also moves the marginals, and the fitted no-three-way
    model absorbs part of that shift, so Omega rises then falls. Consequence for
    the paper: Omega values order pairs by evidence of synergy, but the
    magnitude must not be read as an interaction strength. Monotonicity does
    hold in the observed count with the margins held fixed -- see
    test_omega_monotonic_in_observed_count.
    """
    values = []
    for lam_abz in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        table = loglinear_table(
            lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
            lam_ab=1.0, lam_az=1.0, lam_bz=1.0, lam_abz=lam_abz,
        )
        values.append(om.omega(triple_from_table(table)))
    assert values != sorted(values), "expected the peak-then-decline shape"
    assert max(values) > values[-1]


def test_protective_interaction_gives_negative_omega():
    table = loglinear_table(
        lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
        lam_ab=1.0, lam_az=1.0, lam_bz=1.0, lam_abz=-1.0,
    )
    assert om.omega(triple_from_table(table)) < -0.2


# --- the published approximation, characterised ----------------------------


def test_closed_form_error_grows_with_association():
    """Document why this implementation does not use the published closed form.

    The approximation is exact under independence and stays usable while the
    pairwise log-odds are small, but real drug/event tables are not in that
    regime, and the error there is large enough to invert the sign of Omega.
    """
    errors = {}
    for lam in (0.0, 0.5, 1.0, 2.0, 3.0, 4.0):
        table = loglinear_table(
            lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
            lam_ab=lam, lam_az=lam, lam_bz=lam, lam_abz=0.0,
        )
        t = triple_from_table(table)
        exact = om.expected_count(t)
        errors[lam] = abs(om.expected_count_closed_form(t) - exact) / exact

    assert errors[0.0] < 1e-9, "must be exact under independence"
    assert errors[0.5] < 0.05, "usable while associations are weak"
    assert errors[1.0] > 0.20
    assert errors[2.0] > 1.00, "worst in the regime real data occupies"
    # The error is not monotonic: it peaks in the mid range and falls away again
    # once the table is so extreme that it is nearly degenerate. So there is no
    # association strength above which the approximation is safe to assume.
    assert errors[4.0] < errors[2.0]

    # And the practical consequence: on a no-synergy table the approximation
    # reports a signal in the wrong direction, while the exact fit gives zero.
    table = loglinear_table(
        lam_a=-3.0, lam_b=-3.0, lam_z=-4.0,
        lam_ab=3.0, lam_az=2.0, lam_bz=1.0, lam_abz=0.0,
    )
    t = triple_from_table(table)
    approximate_omega = np.log2(
        (t.n_1_1_1 + om.ALPHA) / (om.expected_count_closed_form(t) + om.ALPHA)
    )
    assert approximate_omega < -1.0
    assert om.omega(t) == pytest.approx(0.0, abs=1e-6)


def test_independence_recovers_the_product_of_marginals():
    table = loglinear_table(lam_a=-2.0, lam_b=-3.0, lam_z=-4.0)
    t = triple_from_table(table)
    assert om.expected_count(t) == pytest.approx(naive_independent_expected(t), rel=1e-6)
    assert om.expected_count_closed_form(t) == pytest.approx(
        naive_independent_expected(t), rel=1e-6
    )
    assert om.omega(t) == pytest.approx(0.0, abs=1e-6)


# --- shrinkage behaviour ---------------------------------------------------
# Tested on (observed, expected) pairs directly, so the shrinkage is isolated
# from the model fit.


def test_shrinkage_suppresses_a_signal_at_low_counts():
    """Threefold excess over expectation: real at scale, not real at n=3."""
    small = om.omega_quantile_vec(3, 1.0)
    large = om.omega_quantile_vec(300, 100.0)
    assert om.omega_vec(3, 1.0) > 0.5, "point estimate is positive in both cases"
    assert om.omega_vec(300, 100.0) > 0.5
    assert small < 0.0, "but n=3 must not clear the threshold"
    assert large > 0.0


@pytest.mark.parametrize("ratio", [2.0, 3.0, 5.0])
def test_lower_bound_rises_with_sample_size_at_fixed_ratio(ratio):
    bounds = [
        float(om.omega_quantile_vec(n, n / ratio))
        for n in (2, 5, 20, 100, 1000)
    ]
    assert bounds == sorted(bounds)
    assert bounds[0] < 0.0 < bounds[-1]


def test_zero_observed_never_signals():
    for expected in (0.01, 1.0, 100.0):
        assert om.omega_quantile_vec(0, expected) < 0.0


def test_lower_bound_is_below_point_estimate_is_below_upper():
    t = om.Triple(
        n_1_1_1=40, n_1_1_dot=200, n_1_dot_1=400, n_dot_1_1=400,
        n_1_dot_dot=20_000, n_dot_1_dot=20_000, n_dot_dot_1=50_000,
        n_total=2_000_000,
    )
    t.validate()
    low, high = om.omega_interval(t)
    assert low < om.omega(t) < high


def test_omega_monotonic_in_observed_count():
    base = dict(
        n_1_1_dot=1_000, n_1_dot_1=2_000, n_dot_1_1=2_000,
        n_1_dot_dot=50_000, n_dot_1_dot=50_000, n_dot_dot_1=100_000,
        n_total=5_000_000,
    )
    values = [om.omega_quantile(om.Triple(n_1_1_1=n, **base)) for n in (0, 5, 20, 100, 500)]
    assert values == sorted(values)


# --- input validation ------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(n_1_1_1=200),                    # triple exceeds a pairwise margin
        dict(n_1_1_dot=20_000),               # pairwise exceeds a single margin
        dict(n_dot_dot_1=10**9),              # margin exceeds the total
        dict(n_1_1_1=-1),                     # negative count
        dict(n_1_dot_dot=150),                # marginals imply a negative cell
    ],
)
def test_validate_rejects_impossible_tables(kwargs):
    base = dict(
        n_1_1_1=1, n_1_1_dot=100, n_1_dot_1=200, n_dot_1_1=200,
        n_1_dot_dot=10_000, n_dot_1_dot=10_000, n_dot_dot_1=20_000,
        n_total=1_000_000,
    )
    with pytest.raises(ValueError):
        om.Triple(**{**base, **kwargs}).validate()


def test_validate_accepts_a_consistent_table():
    om.Triple(
        n_1_1_1=1, n_1_1_dot=100, n_1_dot_1=200, n_dot_1_1=200,
        n_1_dot_dot=10_000, n_dot_1_dot=10_000, n_dot_dot_1=20_000,
        n_total=1_000_000,
    ).validate()


def test_zero_margin_returns_nan_not_a_signal():
    t = om.Triple(
        n_1_1_1=0, n_1_1_dot=0, n_1_dot_1=0, n_dot_1_1=0,
        n_1_dot_dot=0, n_dot_1_dot=100, n_dot_dot_1=100,
        n_total=1_000,
    )
    assert np.isnan(om.expected_count(t))
    assert np.isnan(om.omega(t))
    assert np.isnan(om.omega_quantile(t))


# --- vectorised forms must match the scalar forms --------------------------


def _random_consistent_triples(n_triples: int, seed: int) -> list[om.Triple]:
    """Draw triples by sampling a full table, so consistency is guaranteed."""
    rng = np.random.default_rng(seed)
    triples = []
    while len(triples) < n_triples:
        probabilities = rng.dirichlet(np.full(8, 0.4)).reshape(2, 2, 2)
        table = np.round(probabilities * 1_000_000)
        t = triple_from_table(table)
        if min(t.n_1_dot_dot, t.n_dot_1_dot, t.n_dot_dot_1) == 0:
            continue
        t.validate()
        triples.append(t)
    return triples


def test_vectorised_matches_scalar():
    triples = _random_consistent_triples(150, seed=20260802)
    tables = om.triples_to_tables(
        [t.n_1_1_1 for t in triples],
        [t.n_1_1_dot for t in triples],
        [t.n_1_dot_1 for t in triples],
        [t.n_dot_1_1 for t in triples],
        [t.n_1_dot_dot for t in triples],
        [t.n_dot_1_dot for t in triples],
        [t.n_dot_dot_1 for t in triples],
        [t.n_total for t in triples],
    )
    np.testing.assert_allclose(
        tables, [om.full_table(t) for t in triples], rtol=1e-9
    )

    expected = om.expected_count_vec(tables)
    observed = np.array([t.n_1_1_1 for t in triples])
    np.testing.assert_allclose(
        expected, [om.expected_count(t) for t in triples], rtol=1e-6
    )
    np.testing.assert_allclose(
        om.omega_vec(observed, expected), [om.omega(t) for t in triples], rtol=1e-6
    )
    np.testing.assert_allclose(
        om.omega_quantile_vec(observed, expected),
        [om.omega_quantile(t) for t in triples],
        rtol=1e-5,
    )


def test_screen_scale_batch_is_fast_and_finite():
    """A screen-sized batch must fit in one vectorised call."""
    triples = _random_consistent_triples(200, seed=7)
    reps = 100  # 20,000 pairs, the Phase 9 screen size
    stack = lambda f: np.tile(np.array([f(t) for t in triples], dtype=float), reps)
    tables = om.triples_to_tables(
        stack(lambda t: t.n_1_1_1), stack(lambda t: t.n_1_1_dot),
        stack(lambda t: t.n_1_dot_1), stack(lambda t: t.n_dot_1_1),
        stack(lambda t: t.n_1_dot_dot), stack(lambda t: t.n_dot_1_dot),
        stack(lambda t: t.n_dot_dot_1), stack(lambda t: t.n_total),
    )
    expected = om.expected_count_vec(tables)
    assert expected.shape == (len(triples) * reps,)
    assert np.isfinite(expected).all()


# --- the additive null -----------------------------------------------------
#
# Omega's multiplicative null predicts joint event rates above unity once the
# marginal associations are strong, which is the regime this study occupies. The
# additive null cannot, and these tests pin that difference down.


def _triple_with_risks(risk_a, risk_b, baseline, observed_rate,
                       n_a=50_000, n_b=50_000, n_ab=1_000, n_total=20_000_000):
    """Build a consistent triple from conditional event rates."""
    n_event = int(baseline * n_total)
    return om.Triple(
        n_1_1_1=int(observed_rate * n_ab),
        n_1_1_dot=n_ab,
        n_1_dot_1=int(risk_a * n_a),
        n_dot_1_1=int(risk_b * n_b),
        n_1_dot_dot=n_a,
        n_dot_1_dot=n_b,
        n_dot_dot_1=n_event,
        n_total=n_total,
    )


def test_multiplicative_expected_is_bounded_by_the_co_report_count():
    """IPF reproduces the A-B margin exactly, so it cannot predict above 100%.

    Worth pinning down because it is easy to reason about the multiplicative
    null via an unconstrained RR product, which CAN exceed unity and does so for
    4 of the 16 positive controls. That product is not what the model fits.
    """
    for risk_a, risk_b in [(0.098, 0.0125), (0.30, 0.20), (0.40, 0.35)]:
        t = _triple_with_risks(risk_a, risk_b, baseline=0.00207, observed_rate=0.15)
        t.validate()
        assert 0 <= om.expected_count(t) <= t.n_1_1_dot + 1e-6


def test_impossible_marginals_are_rejected_before_they_reach_ipf():
    """A + B events cannot exceed all events, minus their overlap.

    With 50,000-report marginals at 50% and 40% event rates, A-and-event plus
    B-and-event is 45,000 against 41,399 events in total -- impossible, since
    they can only overlap within the 1,000 co-reports. IPF on such a table
    happily returns an expected count larger than the co-report total, so the
    inconsistency has to be caught before the fit rather than after.
    """
    t = _triple_with_risks(risk_a=0.5, risk_b=0.4, baseline=0.00207, observed_rate=0.15)
    with pytest.raises(ValueError, match="negative cell"):
        t.validate()
    assert om.expected_count(t) > t.n_1_1_dot, "unvalidated input yields nonsense"


def test_multiplicative_null_sets_a_much_higher_bar_than_additive():
    """The concrete failure: gemfibrozil + simvastatin, suspect-only, core tier.

    Observed 55.1% of co-reports carry the event -- an enormous rate. The
    multiplicative null still expects 72.9%, because both drugs are individually
    strong, so the pair scores as protective. The additive null expects 27.9%
    and scores it as a signal. Two agents that both strongly cause the same
    outcome behave sub-multiplicatively as a rule.
    """
    t = _triple_with_risks(risk_a=0.183, risk_b=0.098, baseline=0.00207,
                           observed_rate=0.551)
    assert om.expected_count(t) > om.additive_expected(t)
    assert om.omega(t) < 0 < om.omega_additive(t)


def test_additive_null_stays_within_the_possible():
    t = _triple_with_risks(risk_a=0.098, risk_b=0.0125, baseline=0.00207,
                           observed_rate=0.15)
    expected = om.additive_expected(t)
    assert 0 <= expected <= t.n_1_1_dot
    assert om.omega_additive(t) > 0, "the same pair scores as a signal"


def test_additive_expected_is_the_sum_of_excess_risks():
    t = _triple_with_risks(risk_a=0.05, risk_b=0.03, baseline=0.01,
                           observed_rate=0.10)
    # 0.05 + 0.03 - 0.01 = 0.07 of 1,000 co-reports
    assert om.additive_expected(t) == pytest.approx(70.0, rel=1e-3)


def test_additive_null_is_zero_when_excesses_merely_add():
    """No interaction under additivity must give exactly Omega_add = 0."""
    risk_a, risk_b, baseline = 0.05, 0.03, 0.01
    t = _triple_with_risks(risk_a, risk_b, baseline,
                           observed_rate=risk_a + risk_b - baseline)
    assert om.omega_additive(t) == pytest.approx(0.0, abs=0.02)


def test_additive_null_detects_synergy_beyond_additivity():
    risk_a, risk_b, baseline = 0.05, 0.03, 0.01
    additive_rate = risk_a + risk_b - baseline
    t = _triple_with_risks(risk_a, risk_b, baseline, observed_rate=3 * additive_rate)
    assert om.omega_additive(t) > 1.0
    assert om.omega_additive_quantile(t) > 0.0


def test_additive_expected_never_exceeds_the_co_report_count():
    """Clipping at unity keeps the expectation attainable however extreme."""
    t = _triple_with_risks(risk_a=0.9, risk_b=0.8, baseline=0.001,
                           observed_rate=0.95)
    assert 0 <= om.additive_expected(t) <= t.n_1_1_dot


def test_additive_shrinkage_still_withholds_at_low_counts():
    t = _triple_with_risks(risk_a=0.05, risk_b=0.03, baseline=0.01,
                           observed_rate=0.30, n_ab=10)
    assert om.omega_additive(t) > 1.0, "point estimate is large"
    assert om.omega_additive_quantile(t) < 0.0, "but the bound withholds"


def test_additive_vectorised_matches_scalar():
    triples = _random_consistent_triples(100, seed=606)
    expected = om.additive_expected_vec(
        [t.n_1_dot_1 for t in triples], [t.n_dot_1_1 for t in triples],
        [t.n_1_dot_dot for t in triples], [t.n_dot_1_dot for t in triples],
        triples[0].n_dot_dot_1, triples[0].n_total,
        [t.n_1_1_dot for t in triples],
    )
    scalar = [
        om.additive_expected(om.Triple(
            t.n_1_1_1, t.n_1_1_dot, t.n_1_dot_1, t.n_dot_1_1,
            t.n_1_dot_dot, t.n_dot_1_dot,
            triples[0].n_dot_dot_1, triples[0].n_total))
        for t in triples
    ]
    np.testing.assert_allclose(expected, scalar, rtol=1e-9)


def test_the_two_nulls_diverge_exactly_where_marginals_are_strong():
    """Weak marginals: the nulls agree. Strong marginals: they do not."""
    weak = _triple_with_risks(risk_a=0.004, risk_b=0.003, baseline=0.002,
                              observed_rate=0.005)
    strong = _triple_with_risks(risk_a=0.098, risk_b=0.0125, baseline=0.00207,
                                observed_rate=0.15)
    weak_gap = abs(om.omega(weak) - om.omega_additive(weak))
    strong_gap = abs(om.omega(strong) - om.omega_additive(strong))
    assert weak_gap < 0.5
    # Measured at 1.39 on these inputs; the two nulls disagree by more than a
    # doubling of the observed-to-expected ratio.
    assert strong_gap > 1.0


def test_additive_expected_is_floored_at_the_larger_individual_risk():
    """Drugs reported with the event LESS often than background.

    Their excess risks are negative, so P(Z|A) + P(Z|B) - P(Z) goes below zero.
    Clipping to zero gives a zero expectation and an unbounded Omega_add: the
    first screen run ranked DEXAMETHASONE+LENALIDOMIDE first out of 17,375 pairs
    on a 0.138% event rate against a 0.207% background -- a negative association
    scored as the strongest signal in the database.
    """
    t = _triple_with_risks(risk_a=0.001, risk_b=0.0005, baseline=0.00207,
                           observed_rate=0.0014, n_ab=38_469)
    expected = om.additive_expected(t)
    assert expected > 0, "must not collapse to zero"
    assert expected == pytest.approx(0.001 * t.n_1_1_dot, rel=1e-6), "floored at max risk"
    assert om.omega_additive(t) < 1.0, "a below-background pair is not a top signal"


def test_additive_floor_does_not_bind_in_the_normal_case():
    """Both risks above baseline: the formula must be untouched."""
    t = _triple_with_risks(risk_a=0.05, risk_b=0.03, baseline=0.01, observed_rate=0.10)
    assert om.additive_expected(t) == pytest.approx(0.07 * t.n_1_1_dot, rel=1e-6)


def test_additive_expected_never_falls_below_either_marginal_risk():
    """Adding a drug cannot make the event less likely than the worse drug alone."""
    for risk_a, risk_b, baseline in [
        (0.001, 0.0005, 0.00207), (0.30, 0.001, 0.00207), (0.0001, 0.0001, 0.01),
    ]:
        t = _triple_with_risks(risk_a, risk_b, baseline, observed_rate=0.02)
        rate = om.additive_expected(t) / t.n_1_1_dot
        assert rate >= max(risk_a, risk_b) - 1e-9


def test_additive_floor_applies_in_the_vectorised_path_too():
    t = _triple_with_risks(risk_a=0.001, risk_b=0.0005, baseline=0.00207,
                           observed_rate=0.0014, n_ab=38_469)
    vec = om.additive_expected_vec(
        [t.n_1_dot_1], [t.n_dot_1_1], [t.n_1_dot_dot], [t.n_dot_1_dot],
        t.n_dot_dot_1, t.n_total, [t.n_1_1_dot])
    np.testing.assert_allclose(vec, [om.additive_expected(t)], rtol=1e-9)
