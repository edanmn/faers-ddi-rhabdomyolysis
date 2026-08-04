# Phase 17 — the headline claim was false for one of the two nulls

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

An external-style adversarial review, run against the shipped pipeline rather
than against the prose. Every finding below is computed from
`results/canonical_numbers.json` and `results/tables/*.csv`; the 159 GB pipeline
was not re-run, so the scope is internal consistency plus independent statistics
on the reported counts.

Round 11 established that the false-positive rate had been measured outside the
regime where sensitivity was measured. Round 17 establishes that the *conclusion
drawn from the corrected rates* was wrong in the same way — a right number, read
wrongly, asserted in the title, abstract and conclusion of Paper A.

---

## 1. The central claim was false for Ω

Paper A asserted that **both** nulls are "severely miscalibrated" at their
conventional operating point. The evidence offered for the multiplicative null
was 2.2% against a nominal 2.5%. That is not miscalibration.

| null | in-regime | 95% CI (Jeffreys) | covers 2.5%? | exact binomial *p* |
|---|---:|---|---|---:|
| Multiplicative, rhabdomyolysis | 52/2345 = 2.22% | 1.68–2.87% | **yes** | **0.43** |
| Multiplicative, torsade | 3/152 = 1.97% | 0.6–5.2% | **yes** | **1.00** |
| Additive, rhabdomyolysis | 219/2345 = 9.34% | 8.21–10.57% | no | 2×10⁻⁶⁰ |
| Additive, torsade | 65/152 = 42.8% | 35.1–50.7% | no | 6×10⁻⁶² |

On both events Ω's in-regime type-I error is statistically indistinguishable
from nominal — and these are the *naive binomial* intervals, which ignore that
2,345 pairs are drawn from 1,577 drugs. The cluster bootstrap the paper's own
Methods mandate would be wider, making the null harder still to reject.

The paper contradicted itself: §6 said Ω was "roughly as advertised" while the
Abstract and Conclusion said "severely miscalibrated" for both. §6 was right.

**The corrected finding is asymmetric and stronger.** The additive null is
severely miscalibrated on error rate. Ω is correctly calibrated and disqualified
by *power* — it is systematically negative in this regime and buys its nominal
rate by almost never firing. The two nulls fail in different currencies. This is
now the framing in all three documents.

## 2. "About twice as conservative" was never computed

2.5 / 2.22 = **1.13×**. The additive figure ("about four times too permissive",
9.34/2.5 = 3.74×) was right; this one was not, and it appeared in the sentence
carrying the comparison in both `paper_a.md` and `manuscript.md`.

## 3. A round-11 withdrawal was still live, behind a synonym

The registry forbade `"essentially identical false-positive rate"`.
`manuscript.md`'s abstract carried **`"almost identical false-positive rate
(6.4% vs 6.7%)"`** — the same withdrawn claim, stated as current fact, for six
rounds and 329 passing tests.

This is the **fifth** time a guard here has been defeated by a surface detail
(after a substring, a phrase-only check, document scoping, and a line break).
The common cause is that the registry matches strings, so it catches only the
phrasing whoever wrote the entry had in front of them. Standing addition to §5
of `CLAUDE.md`: **when retiring a claim, register the phrasings you did not
write.**

## 4. The purpose-built pool inherits a weaker form of the defect it fixes

`regime.py:207` excludes pairs where both drugs are on the implicated list —
exactly the configuration all 16 positive controls have, and exactly the
exclusion the module's own docstring criticises `tier_b.generate` for.

The pool therefore matches the positive controls on *marginal strength* but
still cannot match them on *implication status*. Worse, the exclusion removes
the pairs most likely to fire, which pushes the measured rate **down** —
contradicting the Limitations claim that every rate is an upper bound. The two
biases run in opposite directions and neither is quantified.

Disclosed in Paper A §7 as of this round. **Not measured** — re-running with the
exclusion disabled is outstanding.

## 5. Paper B's strength-matched expectation is one number in disguise

The claim that the screen returns "fewer signals than chance predicts" (1,022
against 1,212) rests on a column that is 98.8% reproducible as a single rate
times the screen size:

```
17,375 × 0.0706  =  1,227     vs  1,212 reported
```

The negative pool's top quintile spans marginal strength 2.80–8.95, and the
median pair of *every* band — 2.85 unsupported, 4.16 plausible, 5.32 known pair,
8.15 positive control — falls inside it. More than half the screen collapses
into one bin and inherits one rate, estimated from negatives concentrated at the
bottom of that bin. The rate is also **non-monotone** at the top (0.78, 2.83,
5.72, 8.71, **7.06**%), so extrapolating upward is not demonstrably
conservative.

Now stated explicitly in §4.1, with the claim narrowed to the direction of the
error rather than its size. The honest fix — recomputing the expectation on the
purpose-built pool, which measures the high-strength rate directly — is
outstanding.

## 6. Paper B's table cross-references pointed at the wrong tables

Three tables were numbered "Table 1" in the markdown (the design grid, the
chance expectation, the band signal rate). `build.py` strips manual numbers and
lets LaTeX number sequentially, so the built PDF had Tables 1–7 while the prose
still used the markdown numbering:

| prose said | author meant | PDF showed |
|---|---|---|
| "(Table 4)" | era-stable composition | **Table 6** |
| "(Table 5)" | two era-stable pairs | **Table 7** |

Renumbered 1–7; both cross-references corrected. No test covered table
numbering, and none does now — worth adding.

## 7. Smaller findings, all fixed in prose

- **The mechanistic claim was argued with a fallacy.** Paper A inferred that the
  observed and predicted gradients differ because one correlation was
  significant and the other was not (Gelman–Stern). The correct test for
  dependent overlapping correlations **supports** the claim — Steiger *z* ≈
  −4.75 (multiplicative) and −4.22 (additive), *p* < 10⁻⁴, from an approximate
  reconstruction. Computing it in the pipeline and reporting it is outstanding.
- **"Flat" was an overclaim.** *r* = +0.12 with CI −0.40 to +0.58 cannot exclude
  a moderate rise. All three documents now say "far more shallowly than either
  null predicts".
- **Paper B never disclosed that one control is absent from the screen.**
  Itraconazole + lovastatin: both ingredients are in the top 200, but the pair
  is co-reported **once** in 22 years and falls below the three-co-report floor.
  Hence 11/15 in the band table against "12 of 16" in the abstract. Disclosed.
- **The adopted polypharmacy cap is dominated.** Cap 10 gives 13/16 at 6.0%
  against cap 20's 12/16 at 6.7%. Retained deliberately — re-tuning on the same
  16 controls used to measure performance would convert a pre-specified
  parameter into a fitted one — and the reasoning is now stated.
- **"Nominal 2.5%" is a convention, not a guarantee.** Ω₀₂₅ is a gamma-Poisson
  posterior percentile, not a frequentist statistic. Noted in Methods.
- **Reproducibility gap.** `rr_a`/`rr_b` ship only in `tier_b_pairs.csv`, so
  Paper A Table 2 and Paper B §4.4 cannot be recomputed from shipped tables, and
  the 19,826-pair pool ships nowhere. Outstanding.

## New guards

Two, both mutation-tested (defect reintroduced, test observed to fail, restored):

- `test_no_maintained_document_carries_a_withdrawn_claim` — four entries added:
  the synonym withdrawal, "twice as conservative", "does not rise with marginal
  strength at all", and "both disproportionality nulls are severely
  miscalibrated".
- `test_documents_report_the_in_regime_miscalibration_as_one_sided` — new. A
  negative guard passes when a bad sentence is deleted and nothing written in
  its place, so this asserts the *replacement* is present: any document quoting
  both in-regime rates must state which way the miscalibration runs. Both rates
  are read from the canonical file rather than hardcoded.

## Status

**330 tests, 0 skipped.** Both conference papers at 8 body pages against a cap
of 8 — zero slack, and Paper A required four build cycles and compensating cuts
elsewhere to absorb this round's additions.

## The standing lesson

Round 16's lesson was that guards must be scoped to the document set. Round 17's
is narrower and worse: **the tests cannot catch a wrong reading of a right
number.** The pipeline computed 2.2%, the prose reported 2.2%, the test verified
2.2% against the canonical file, and the sentence built on it asserted the
opposite of what 2.2% means. Every check in the suite passed at every point.

When a number is quoted as *evidence for a claim*, the number matching is the
weakest thing that could be verified. Check the inference.
