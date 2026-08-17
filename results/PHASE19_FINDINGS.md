# Phase 19 — a QA pass, and a withdrawn claim that came back

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

A numerical-accuracy review of the merged manuscript: every derivable figure
recomputed, every cross-reference resolved, every citation matched, all
arithmetic re-derived from the canonical file and the shipped tables. The
pipeline was not re-run.

Two findings were regressions from the round-18 merge. One was a claim withdrawn
in round 10 that had been live in the Abstract ever since.

---

## 1. Neither estimand was defined

The manuscript contained **zero display equations**. Ω and Ω_add were written
out only in `paper_a.md`, so retiring it in round 18 deleted both formulae and
left the additive null described in prose that omitted the **cap at 1** and the
**multiplication by the co-report count** — both present in
`omega.py:334`. A methods paper comparing two nulls did not state either null
precisely enough to reimplement.

Both equations are restored to §3.8 with notation defined, and
`test_document_defines_both_estimands` now asserts their structure. Nothing had
asserted that a formula existed.

## 2. The round-10 withdrawn claim was live in the Abstract

The Abstract read *"structurally blind to 9.9% of screened pairs — 17.2% of
ingredients have no FDA label at all, including cerivastatin, the fibrates and
fusidic acid"*, and Limitations asserted 17.2% **"of screened ingredients"**
outright.

17.2% is 138/800, the label **cache**. The screened figure is **5.5%** (11/200).
Cerivastatin, bezafibrate, ciprofibrate and telithromycin are the canonical
`cited_but_not_screened` list — round 10 withdrew exactly this use of them.

**Why two guards passed.** Both checked that the qualifying phrase appeared
*anywhere in the document*. It did, in §4.5, roughly 700 lines away. A
document-level co-occurrence check cannot bind a claim to its qualification.
Both now bind **per sentence**, and both were mutation-tested against the exact
sentences that were live.

This is the **sixth** distinct way a guard here has been too weak: after a
substring, a phrase-only check, document scoping, a line break, and a synonym —
now **distance**.

## 3. A misleading key in the pipeline

`run_analysis.py` stored the era-stability chance expectation as

```python
"expected_era_stable_by_chance": round(bound * len(rows), 1)   # bound = UPPER CI
```

which evaluates to **33.2** where the expectation is **16.1**. The prose always
quoted 16.1 correctly, but anyone reading the key by its name would conclude the
19 observed pairs fall far *below* chance. Nothing asserted it.

Renamed to `expected_era_stable_at_upper_bound`, with
`expected_era_stable_point` emitted beside it.
`test_era_stable_chance_expectation_is_the_point_estimate` derives the
expectation from the rate and the screen size, so it holds whatever the key is
called. **The canonical file carries the old key until the next
`run_analysis`.**

## 4. Two rounding errors

- **9.8% → 9.9%.** 1,712/17,375 = 9.853%. The share was stored pre-rounded to
  4dp and re-rounded for display. The guard re-derived the paper's figure from
  the same rounded intermediate, so it could not fail. `audit.py` no longer
  rounds it, and the guard now derives from the counts.
- **CI 6.8 → 6.7.** The exact Jeffreys interval on 6/6,471 scaled to 17,375
  pairs is [6.73, 33.19].

## 5. Smaller

- Two cross-references read §3.6 where they meant §3.7; both resolved to a real
  section, so nothing warned. Fixed.
- The crude `plausible` enrichment appears as 0.77, 0.767 and 0.766 — one
  quantity computed in three modules that round differently. A note now says so.

## Checked and found correct

Recorded because a review that lists only faults misrepresents the artifact.

- All cross-references resolve; all 11 references are cited; no orphans.
- Figures 1–7 consistent across prose, filenames and captions.
- Population arithmetic exact: 20,293,421 − 19,005 = 20,274,416;
  41,889/20,274,416 = 0.207%.
- The apparent 24,812,418 vs 24,812,425 contradiction is **explicitly
  reconciled in-text** by the 7 NULL-`case_id` LAERS rows. The manuscript was
  more careful here than the check that flagged it.
- Vocabulary hygiene, screen arithmetic, recovery percentages: all verified.
- The r17 asymmetry correction survived the merge intact.

## Status

**331 tests, 0 skipped.** Build clean, manuscript 31 pages.

## The standing lesson

Round 17's was that a test cannot catch a wrong reading of a right number.
Round 19's is adjacent: **a guard that checks a document rather than a sentence
cannot catch a claim separated from its qualification.** Both withdrawn-claim
failures this project has had — r17's synonym and r19's distance — were the
registry matching text at the wrong granularity, not the wrong content.
