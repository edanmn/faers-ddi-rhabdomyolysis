# Phase 15 — round-11 review: the error rate was never measured where it mattered

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

Round 11 found one unexamined assumption underlying both papers: that the
false-positive rate is constant across the marginal-strength range. It is not —
it varies by an order of magnitude — and correcting for it **overturns Paper A's
headline claim and its replication**. This is the largest correction in fifteen
phases.

---

## 1. The false-positive rate was measured outside the regime under study

The positive and negative control populations barely overlap on the variable
that drives both nulls:

| | *n* | median log₂(RR_A × RR_B) | IQR |
|---|---:|---:|---|
| Positive controls | 16 | **8.23** | 7.92 – 8.99 |
| Generated negatives | 16,078 | **0.56** | −1.52 – 2.44 |

**Only 11 of 16,078 generated negatives (0.1%) reach the positive controls'
interquartile floor.** The mechanical cause: `tier_b.generate` excludes any pair
in which *both* drugs are on the implicated list — which is exactly what every
positive control is. The generator cannot produce a negative resembling a
positive.

Rate by quintile of marginal strength (additive / multiplicative): 0.93/1.62,
3.55/5.72, 7.21/8.64, 10.86/10.39, **10.91/5.97** — an order of magnitude of
variation and a crossover in the top quintile.

The published strata concealed this: easy 4.02% vs 4.94% (additive *lower*),
hard 8.54% vs 7.50% (additive *higher*). Two differences in opposite directions,
averaging to the "essentially identical" 6.67% vs 6.44%. **Paper A reported the
strata for the additive null only.**

## 2. A purpose-built negative pool, and what it shows

Built directly for the regime: all pairs among the 1,577 ingredients with
RR ≥ 2 and ≥ 20 co-reports, excluding positive controls and every
endpoint-documented pair, and excluding both-implicated undocumented pairs as
too likely to be unrecorded true interactions. **19,826 pairs.**

| pool | *n* | additive | multiplicative |
|---|---:|---:|---:|
| purpose-built, all | 19,826 | 7.2% | 3.7% |
| **purpose-built, at positive-control strength** | **2,345** | **9.3%** | **2.2%** |
| generated pool, at positive-control strength | 166 | 9.0% | 1.2% |

The two agree; the purpose-built pool carries fourteen times the sample.
**Against a nominal 2.5%, Ω is about twice as conservative as advertised in this
regime and Ω_add about four times too permissive.**

## 3. The headline recovery gap collapses

| operating point | additive | multiplicative | gap |
|---|---:|---:|---:|
| Ω₀₂₅ > 0 (as published) | 12/16 @ 9.0% | 4/16 @ 1.2% | **8** |
| matched at 5% in-regime FPR | 12/16 | 10/16 | **2** |
| matched at 10% | 12/16 | 11/16 | **1** |
| matched at 20% | 14/16 | 12/16 | **2** |

**Eight pairs becomes one to two.** The additive null still wins at every
matched rate, so the direction is real — but with 16 controls in five
victim-drug clusters and a 50–100% interval on the unmatched estimate, a
one-to-two-pair difference is not separable from noise, and the paper no longer
claims it is.

## 4. The torsade replication fails

In-regime rates at Ω₀₂₅ > 0: **2.0% for Ω, 42.8% for the additive null.** The
additive null fires on nearly half of strongly-associated non-interacting pairs.

| operating point | additive | multiplicative |
|---|---:|---:|
| Ω₀₂₅ > 0 (as published) | 9/10 @ 42.8% | 0/10 @ 2.0% |
| matched at 5% | **0/10** | **0/10** |
| matched at 10% | **1/10** | **1/10** |
| matched at 20% | **4/10** | **3/10** |

**At any common error rate neither null recovers these pairs and the additive
null has no advantage.** The 9-versus-0 result is an artefact of the
conventional threshold sitting at wildly different error rates for the two
measures. What replicates on torsade is the *calibration* finding, not the
recovery finding.

## 5. Paper B's chance baseline assumed a constant rate

| band | tested | observed | pooled (5.03%) | strength-matched |
|---|---:|---:|---:|---:|
| unsupported | 11,887 | 717 | 598 | **824** |
| plausible | 4,930 | 228 | 248 | **348** |
| known pair | 543 | 66 | 27 | **39** |
| positive control | 15 | 11 | 1 | 1 |
| **total** | 17,375 | **1,022** | **872** | **1,212** |

Under the pooled figure the screen shows a modest excess. Strength-matched, it
returns **fewer signals than chance predicts**, and only `known_pair` exceeds
its own expectation. This sharpens Paper B's negative result rather than
threatening it.

## 6. What the papers now claim

Paper A was retitled and rewritten around calibration rather than around which
null is better:

> *Both disproportionality nulls are severely miscalibrated for drug–drug
> interaction screening when the drugs under study dominate the outcome.*

That is a sharper and more actionable claim than the one it replaces, and it is
what the data support. The recommendation — compute the marginal relative risks
first, then calibrate against negative controls from the same regime — costs
nothing and would have prevented the error.

## 7. A layout defect found while trimming

Paper A went to 9 pages after the rewrite and the build correctly refused it.
The cause was in `paper/build.py`: every pandoc table was converted to a
full-width `table*` float, so a three-column table reserved the whole text
width. Narrow tables (≤ 4 columns) now use a single-column `table`, which
recovered roughly a page across the paper.

## Status

**328 tests passing** (321 → 328). New module `src/faers_ddi/regime.py`
(in-regime rates, matched recovery, purpose-built pool, strength-matched
chance). Paper A at 8 body pages, Paper B at 7, both under the cap.

The three critical guards were mutation-tested: restoring "essentially
identical", restoring the torsade replication claim, and reverting Paper B to
the pooled baseline each fail their test.

**Note on the test suite.** All 321 tests passed *before* these corrections and
*after* the central claim was withdrawn — no test was binding the claim that was
wrong. Passing tests are evidence that stated numbers match computed ones, not
that the right quantity was computed. That is the standing limitation of this
project's verification approach, and it is worth stating plainly rather than
taking 328 as reassurance.
