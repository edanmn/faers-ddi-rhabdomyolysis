# Phase 14 — round-10 review: the two conference papers

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

Round 10 reviewed `paper_a.md` and `paper_b.md` against the field's own
standards rather than an ML-conference frame. Five findings, one of them a
factual error that overstated the papers' own limitation threefold, plus one
further defect found while fixing them.

---

## 1. The reference-blindness denominator was wrong

Both papers stated:

> "138 of the **800 screened ingredients (17.2%)** have no FDA label."

Paper B stated three sections earlier that the screen covers the **top 200**
ingredients. Both cannot be true. 800 is the size of the label *cache*, built
out for the screen-size sensitivity analysis; the screen covers 200.

| denominator | ingredients | no label | rate |
|---|---:|---:|---:|
| label cache (as published) | 800 | 138 | 17.2% |
| **ingredients actually screened** | **200** | **11** | **5.5%** |

**The papers overstated their own limitation by a factor of three.** The pair
figure — 1,712 of 17,375 (9.8%) — was correct throughout and is retained; the
11 blind drugs are well co-reported, so they touch a disproportionate share of
the pair space.

## 2. Four of the five drugs cited as evidence were never screened

The claim that blindness "is concentrated on... members of the classes that
define this endpoint" was supported by cerivastatin, bezafibrate, ciprofibrate
and telithromycin. **None of the four is in the screened top-200.** The screen
was not blind to cerivastatin; cerivastatin was never a candidate.

Only **fusidic acid** is both unlabelled and screened — and it is the strongest
example, being the screen's highest-ranked pair by event rate, so the argument
survives on one example rather than five. Paper B now reports the 800-drug
figure separately and explicitly labelled as the wider reference's coverage,
noting the four drugs did not enter the screen and therefore do not bear on the
result.

## 3. Four entries in the screened vocabulary are not drugs

The drug-selection rule is applied mechanically to FDA's resolved
active-ingredient field. Four of the resulting 200 "ingredients" are
placeholders that field supplies where it cannot resolve a moiety:

`UNSPECIFIED INGREDIENT`, `HERBALS`, `INSULIN NOS`,
`CANNABIS SATIVA SUBSP INDICA TOP`

A further three pairs are one moiety with itself — valproate reaches the
vocabulary as `VALPROATE`, `VALPROIC ACID` and `DIVALPROEX`, and all three
pairings among them are in the screen. (This one was found while fixing the
others, not by the review.)

Together: **719 pairs (4.1% of the screen), 38 signals, 122 in the `plausible`
band.**

**They are not material**, and the sensitivity was measured rather than assumed:

| band | as specified | excluding invalid pairs |
|---|---:|---:|
| known pair | 2.015 | 1.995 |
| **plausible** | **0.766** | **0.752** |

They are **not removed from the primary analysis**: the selection rule was fixed
in advance, and excluding terms after seeing results would be a researcher
degree of freedom. `audit.vocabulary_hygiene` computes both and Paper B reports
the comparison. The residual concern is interpretive rather than aggregate — a
pair naming `UNSPECIFIED INGREDIENT` is uninterpretable however it scores, and
122 such pairs sit in the discovery band.

## 4. Neither paper stated its computational environment

Both claimed byte-identical reruns. Neither gave a language version, a database
version, hardware, runtime, or a seed — while running a 20,000-draw cluster
bootstrap, a 10,000-permutation test, a 10,000-draw null simulation and a
500-split calibration. **A determinism claim without a stated seed is
unverifiable.** The full manuscript carries all of it; condensation dropped it.
Both papers now have a Computational environment section.

## 5. Two presentation defects

**Paper A's held-out control table mixed denominators within a row** — *n* read
"14 powered" while the multiplicative cell reported out of 16. Split into four
rows, each carrying its own denominator; the powered multiplicative count
(4/14) was verified against the Tier A table rather than inferred.

**Paper B promised "five progressively more independent annotation schemes"**, a
count not derivable from what it reports. Replaced with the actual structure:
three annotations, two scopes, plus a label-coverage restriction.

## Guards

Six tests added, and the two protecting the factual error were mutation-tested:
reintroducing `138 of the 800 screened ingredients (17.2%)` fails
`test_blindness_is_reported_over_the_screened_set`, and re-citing cerivastatin
fails `test_drugs_cited_as_blind_were_actually_screened`. Both bite.

This mattered because the last two rounds each produced a guard too weak to
catch the defect it was written for. Mutation-testing each new guard is now the
practice.

## Status

**321 tests passing** (315 → 321). Both papers at **7 body pages** against the
8-page cap. New in `audit`: `vocabulary_hygiene`, and `reference_coverage` now
reports the screened-set denominator alongside the cache-wide one.

The correction in finding 1 makes the papers' stated limitation *smaller*, not
larger — the error was in the conservative direction, which is why ten rounds of
review had not caught it.
