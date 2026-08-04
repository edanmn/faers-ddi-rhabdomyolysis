# Phase 13 — round-9 review: what splitting the paper cost

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

Round 9 reviewed `paper_a.md` and `paper_b.md` — the two condensed conference
papers — rather than the full manuscript. The question was what condensation and
splitting cost. Five findings, one of which the split itself created and one of
which was a false guarantee that had stood in all four documents.

---

## 1. The split reintroduced a defect round 8 had fixed

Round 8's critical finding was that the paper reported one of four
tier × role-policy specifications without disclosing the others, one of which
nullifies the headline contrast (6/16 versus 6/16). The fix was to publish the
grid.

Splitting undid it. Paper A kept the grid. **Paper B kept the claim.** B's
abstract asserted "a pipeline that recovers 12 of 16 label-verified positive
controls" and §2 restated the 4-versus-12 contrast, with **zero** occurrences of
"specification grid", "role policy", "broad tier" or "four arms".

That matters more in B than in A: B's negative discovery result draws its force
entirely from the premise that the pipeline demonstrably finds known
interactions. If that premise is specification-dependent, so is the null result.

The grid is now Table 1 of Paper B, with an explicit statement that the
foundation inherits the dependence. This also resolves the round-8 concern about
B resting on an unpublished companion: B no longer needs A for its foundation.

## 2. A guard that did not guard

`test_both_papers_carry_the_specification_grid_or_cite_it` required the grid in
paper A, and required paper B only to contain the phrase **"companion paper"**.
It passed throughout, while B carried an unqualified 12/16.

This is the second time in three rounds that a test written to catch a specific
defect was too weak to catch it — the first was the `6/16` substring that also
matches `16/16`. Both were written by the same author as the defect they were
meant to catch, which is the pattern worth noting rather than the individual
bugs. The test now requires every arm of the grid to appear as a table row in
**both** papers, plus the word "specification-dependent" in B.

## 3. The availability statement was false in all four documents

Every document claimed some form of:

> "Every figure quoted is generated into a single canonical results file and
> asserted against this text by an automated test suite."

Of 18 substantive quoted figures checked, **11 were absent from
`canonical_numbers.json`** and therefore asserted by nothing:

| Figure | In canonical before? |
|---|---|
| 5,709,555 hospitalisation reports | no |
| 275,205 hospital-context cases | no |
| 28.47% / 137.8× author-selected event rate | no |
| 40.5% implicated-drug background | no |
| 189.2 expected (simvastatin + amiodarone) | no |
| 25,047 PT strings | no |
| 82,342 cross-era bridge identifiers | no |
| 19,005 polypharmacy cases | no |
| 4,928,413 / 5,337,888 AEOLUS benchmark | no |
| 16.1 era-stable by chance | no |

Most were correct but computed in ad-hoc queries during earlier rounds and never
persisted. `audit.provenance` now computes and stores them, and the availability
statement now says precisely what is guaranteed rather than claiming everything.

## 4. Persisting provenance immediately caught two stale numbers

This is the argument for doing it.

**189.2 → 189.54.** The expected count for simvastatin + amiodarone, the pair
named in advance as the one that must work, was quoted as 189.2 in the
manuscript and in Paper A. The Tier A table says **189.54**. The prose figure
was stale. `provenance` now reads that row from `tier_a_results.csv` rather than
recomputing it, so the number has exactly one source.

**137.8× → 141.4×.** The event rate among co-reports for the author-selected
control set — the mechanism behind the 86%-versus-12% recovery gap — recomputes
to 29.2% (141.4× baseline), not the 28.47% (137.8×) quoted since round 5. The
top decile of label-selected pairs recomputes to 0.12% (0.57× baseline) rather
than 0.11% (0.5×). All four documents corrected.

The qualitative claim is unaffected: the two control sets differ by a factor of
**40** in event rate among co-reports, and the most heavily co-reported
label-documented pairs still sit below the database baseline.

## 5. A benchmark test that was a tautology

`test_manuscript_reports_the_aeolus_benchmark` asserted that two hardcoded
literals appeared in prose containing the same two literals:

```python
assert "5,337,888" in manuscript and "4,928,413" in manuscript
```

`5,337,888` — the principal external benchmark for deduplication — appeared
nowhere in the repository except the prose and that test. It was not produced by
any pipeline stage and not recomputable from anything shipped. The test would
have passed with the number wrong.

It recomputes correctly: **5,337,888** cases over 2004q1–2015q2 against AEOLUS's
published 4,928,413, 8.3% apart. The figure is now generated by
`audit.provenance` and the test checks the generated value, the window, and that
the two counts are within 15% of each other.

One related correction: the cross-era bridge count (82,342) is **not** recoverable
after deduplication — there is one row per `case_id` by then, so a self-join
returns 0, which my first version of the provenance query duly reported. It is
read from `results/tables/attrition.csv` instead, with the source recorded.

## 6. Caveats partitioned such that neither paper was complete

The split distributed caveats by topic, which is mostly right. Two were not:

- **Paper A** reported the label-selected control set and the 12–16% recovery
  rate without noting that the reference generating those controls is blind to
  17.2% of screened ingredients, including the fibrates and fusidic acid. Added.
- **Paper B** never mentioned α, though its screen threshold depends on it and
  it is unverified against the primary source. Added, with a pointer to the
  20-fold sensitivity in the companion.

## Status

**315 tests passing.** Both conference papers at **7 body pages** against the
8-page cap (up from 6 — the grid table, the two caveats and the longer
availability statement). Audit verified deterministic across a full re-run.

New: `audit.provenance`. Rewritten: the AEOLUS test, the specification-grid
guard, and the recovery-gap test (now sourced from canonical rather than
hardcoded).

Two numbers in the write-ups were wrong and are now right. Both were found by
building the provenance the documents had already claimed to have.
