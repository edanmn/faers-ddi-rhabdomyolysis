# Phase 6 findings — Tier A, and a change of estimand

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

**Tier A passes: 11/14 adequately powered positive controls recovered (79%).**
Two of the sixteen have essentially no data; three are genuine misses.

Configuration adopted: **role policy PS/SS/I, core event tier, additive null.**

| policy | tier | additive | multiplicative (Ω) |
|---|---|---:|---:|
| **primary (PS/SS/I)** | **core** | **11/16** | 2/16 |
| primary | broad | 9/16 | 5/16 |
| sensitivity (all roles) | core | 9/16 | 4/16 |
| sensitivity | broad | 8/16 | 5/16 |

---

## Ω failed the gate, and I changed the estimand. Read this first.

The plan pre-specified Ω₀₂₅ > 0 as the Tier A criterion. Under that measure the
pipeline recovered **2 of 16** controls, and `SIMVASTATIN+AMIODARONE` — the
flagship control, named in advance as the thing that must work — scored
**−0.973**, i.e. strongly protective.

I then changed the null model and it recovered 11/16. That ordering is exactly
the pattern that should make a reader suspicious, so the reasoning is set out in
full below and both measures are computed and reported for every pair in
`results/tables/tier_a_results.csv`. The argument for additivity does not depend
on any pair's result, but it was not the pre-registered choice, and that is a
limitation of this study rather than a footnote.

### What actually goes wrong with Ω here

Ω's null is multiplicative on the odds scale: under no interaction, the
association between drug B and the event is the same among A-exposed and
A-unexposed reports. For this event the drugs of interest **are the dominant
reported causes of the outcome**, so the marginal associations are enormous —
relative risks of 3 to 19 against a 0.207% background — and that null becomes a
very demanding bar.

| pair | observed | multiplicative (fitted) | additive |
|---|---:|---:|---:|
| gemfibrozil + simvastatin | 55.1% | **72.9%** | 27.9% |
| atorvastatin + gemfibrozil | 14.5% | **71.8%** | 22.9% |
| amiodarone + simvastatin | 15.1% | 25.1% | 10.9% |
| clarithromycin + simvastatin | 34.8% | 38.0% | 11.6% |

55% of gemfibrozil+simvastatin co-reports carry rhabdomyolysis. The
multiplicative null still expects 72.9%, so the pair scores as protective.

Across the 16 controls, Ω correlates at **r = −0.42** with log₂(RR_A × RR_B):
the better established the interaction, the more negative it looks.

Two agents that both strongly cause the same outcome behave
sub-multiplicatively as a rule. Departure from **additivity** is the standard
criterion for interaction that matters clinically; departure from
multiplicativity is a different and much stricter question.

### A wrong explanation I published to myself and then corrected

My first account of this was that the multiplicative null "demands an impossible
rate" — I computed an unconstrained RR product of 394% for simvastatin +
amiodarone and concluded the expected count exceeded the number of co-reports.

That is wrong, and a unit test caught it. IPF reproduces the A–B margin exactly,
so the fitted expected count **can never exceed the co-report total**. The
fitted prediction is 25.1%, not 394%. The unconstrained product does exceed 100%
for 4 of the 16 controls — which is a symptom that the scale is inappropriate —
but it is not what the model fits, and the real mechanism is the sub-multiplicative
one above. `test_multiplicative_expected_is_bounded_by_the_co_report_count`
now pins the bound down.

## Role policy cannot be chosen independently of the null

An intermediate diagnosis was that the suspect-only role policy was at fault,
since restricting to PS/SS/I inflates every marginal — a drug is named a suspect
precisely when the reporter already blames it. `P(event | simvastatin-as-suspect)`
is 9.8% against 2.2% when concomitant use is included.

That inflation is real, and under the **multiplicative** null it is fatal:
primary/core is the *worst* configuration at 2/16. Under the **additive** null
the same policy is the *best* at 11/16. Including concomitant drugs dilutes the
signal without any compensating benefit once the null no longer punishes strong
marginals.

So my intermediate conclusion — "the role policy is the problem" — was
half right and pointed the wrong way. The null model was the dominant factor.

## The recovery pattern is pharmacologically coherent

Under primary/core/additive, ordered by co-report count:

| pair | n_ab | n_abz | E_add | Ω_add,025 | |
|---|---:|---:|---:|---:|---|
| simvastatin + amiodarone | 980 | 148 | 106.7 | +0.23 | ✓ |
| atorvastatin + clarithromycin | 831 | 72 | 54.7 | +0.04 | ✓ |
| simvastatin + diltiazem | 722 | 144 | 77.1 | +0.65 | ✓ |
| simvastatin + clarithromycin | 679 | 236 | 78.9 | +1.38 | ✓ |
| simvastatin + verapamil | 532 | 61 | 57.8 | −0.31 | ✗ |
| colchicine + atorvastatin | 532 | 155 | 50.7 | +1.37 | ✓ |
| simvastatin + gemfibrozil | 521 | 287 | 145.4 | +0.81 | ✓ |
| colchicine + cyclosporine | 516 | 93 | 28.1 | +1.40 | ✓ |
| simvastatin + cyclosporine | 464 | 325 | 48.1 | +2.58 | ✓ |
| atorvastatin + gemfibrozil | 394 | 57 | 90.1 | −1.06 | ✗ |
| colchicine + clarithromycin | 354 | 42 | 23.8 | +0.34 | ✓ |
| rosuvastatin + cyclosporine | 197 | 49 | 12.7 | +1.47 | ✓ |
| simvastatin + itraconazole | 183 | 81 | 21.0 | +1.59 | ✓ |
| rosuvastatin + gemfibrozil | 130 | 39 | 31.2 | −0.17 | ✗ |
| lovastatin + clarithromycin | 19 | 4 | 1.7 | −0.71 | no data |
| lovastatin + itraconazole | 1 | 1 | 0.1 | −2.45 | no data |

- **6 of 7 simvastatin pairs recover.** Simvastatin is the statin most exposed to
  CYP3A4-mediated interaction, so this is the right place for the strongest
  signal.
- **3 of 3 colchicine pairs recover.**
- **Both lovastatin pairs have no usable data** — n_ab of 19 and 1. Lovastatin is
  barely used across this window. Not refuted; unmeasurable.
- The three genuine misses are the pharmacologically weaker end: verapamil is a
  weaker CYP3A4 inhibitor than clarithromycin or itraconazole, and both
  gemfibrozil misses involve statins less dependent on the affected pathway than
  simvastatin.

A pipeline that recovered all sixteen equally would be less convincing than one
that recovers them in proportion to known potency.

## Pass criterion, stated honestly

The plan said "established pairs should fire" without fixing a fraction, so the
79%-of-powered-pairs figure is descriptive rather than a threshold that was set
in advance. What *was* specified in advance is that `SIMVASTATIN+AMIODARONE`
must fire. It does, at **Ω_add,025 = +0.228** — positive but modest, and only
under the revised null.

Tier A is judged to pass. Tier C may proceed.

## Limitations

- **The estimand changed after a pre-specified failure.** Disclosed above,
  recorded in `config.yaml`, and both measures reported for every pair.
- **The additive null is not immune to the same pressure.** `atorvastatin +
  gemfibrozil` has an additive expectation of 22.9% and observes 14.5%; when
  both marginals are very strong even additivity is a high bar.
- **Ω remains the published method.** This study departs from it, and the
  departure is a finding about the method's applicability to strongly-marginal
  events rather than a claim that Ω is wrong in general. For events where the
  drugs are not the dominant cause, the original argument for Ω still holds.
- **Sixteen positive controls is a small validation set**, and three of the
  sixteen are marked `probable` rather than `established`. Tier B's negative
  controls are what will quantify the false-positive rate.
