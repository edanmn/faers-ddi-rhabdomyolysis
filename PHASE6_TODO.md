# Open items on the Omega implementation

## 1. Source-verify the numeric scale against Norén et al. 2008

**Status: open. Requires the paper.**

`src/faers_ddi/omega.py` is verified by 34 invariant tests: it returns exactly
zero on tables generated with no three-way interaction term, detects synthetic
synergy, shrinks correctly at low counts, and its vectorised path matches its
scalar path. What has *not* been done is reproducing a worked numeric example
from the source paper.

That matters because the invariants pin down the *shape* of the statistic but
not the constants. Specifically unconfirmed:

- **α = 0.5.** The shrinkage constant. Standard for this family, but not
  verified against the paper.
- **The posterior form.** This implementation uses Gamma(n + α, rate = E + α)
  for the observed-to-expected ratio, giving Ω₀₂₅ as its 2.5th percentile.
  Consistent with how shrinkage measures in this literature are constructed, but
  not verified.
- **Whether Ω₀₂₅ or Ω itself is conventionally reported**, and against what
  threshold.

None of these affect the *ranking* of drug pairs, which is what Tier C depends
on. They affect the absolute threshold at which a pair is called a signal. Since
Tier B calibrates that threshold empirically from negative controls anyway, the
study does not hinge on this — but the methods section cannot claim conformance
with the published statistic until it is checked.

**Action:** obtain Norén GN, Sundberg R, Bate A, Edwards IR, "A statistical
methodology for drug-drug interaction surveillance," *Statistics in Medicine*
2008;27:3057-3070, and reproduce one worked example.

## 2. Deviation from the published closed form — decided, needs writing up

**Status: resolved in code, must be documented in the paper.**

The literature approximates the expected count under [AB][AZ][BZ] with

    E_111 ≈ (n_11· · n_1·1 · n_·11) / (n_1·· · n_·1· · n_··1) · n_···

This implementation does not use it. Measured against an exact IPF fit on
synthetic log-linear tables (`test_closed_form_error_grows_with_association`):

| pairwise log-odds | relative error in E_111 |
|---|---|
| 0.0 | 0% (exact under independence) |
| 0.5 | 4% |
| 1.0 | 26% |
| 2.0 | **237%** |
| 3.0 | 167% |
| 4.0 | 13% |

At λ = 2–3 the approximation is wrong enough to report **Ω < −1 on a table with
no synergy in it whatsoever**, and it is non-monotonic in true synergy strength.
The error also peaks mid-range rather than growing with association, so there is
no association strength above which it can be assumed safe.

Real drug/event tables sit in the bad regime: strongly co-prescribed drug pairs
and drugs individually associated with the event are exactly the cases a DDI
screen is built to examine.

IPF fits the model exactly, converges in microseconds on a 2×2×2 table, and is
vectorised across pairs here — a 20,000-pair screen fits in one call in ~1.2 s.
The approximation is retained as `expected_count_closed_form` purely for this
comparison.

**Action:** methods subsection stating the deviation and the measured error, and
report both estimators for the Tier A positive controls so the difference is
visible on real data rather than only on synthetic tables.

## 3. Ω is not an effect size — caveat for the discussion

`test_omega_is_not_monotonic_in_the_loglinear_interaction_parameter` documents
that Ω rises and then falls as the true three-way log-linear parameter grows,
because the fitted marginals absorb part of the change. Ω orders pairs by
evidence of synergy; its magnitude must not be read as interaction strength.
Monotonicity does hold in the observed count with margins fixed.
