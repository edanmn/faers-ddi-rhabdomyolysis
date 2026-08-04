# Phase 16 — descriptive titles, and the drift they exposed

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

Retitling the two conference papers surfaced a larger problem: the round-11
corrections had landed in two documents and not the other two, and the test
suite passed 328 throughout.

---

## 1. Titles no longer assert conclusions

| document | before | after |
|---|---|---|
| paper_a | *Both disproportionality nulls are severely miscalibrated…* | *Calibration of additive and multiplicative nulls for drug–drug interaction detection when both drugs are leading causes of the outcome: an analysis of 22 years of FAERS* |
| paper_b | *Circular annotation and reference blindness in…* | *Annotation independence and reference coverage in the evaluation of drug–drug interaction screens: 17,375 drug pairs in 22 years of FAERS* |
| manuscript | *The multiplicative null fails for…* | *Calibration and evaluation of disproportionality nulls for drug–drug interaction detection: an analysis of 22 years of FAERS* |

The manuscript's old title was not merely a claim; it was a claim round 11 had
already shown to be largely an operating-point artefact.

## 2. Three documents carried the withdrawn claim

Round 11 measured the false-positive rates in the regime where recovery is
measured (2.2% and 9.3%, not the pooled 6.4% and 6.7%) and withdrew the
"essentially identical false-positive rate" framing. That correction was applied
to `paper_a.md`. It was **not** applied to:

- `manuscript.md` — two occurrences, plus the torsade replication presented as
  successful and the pooled chance baseline
- `paper.md` — same
- `paper_b.md` — its Background restated the comparison "at a matched
  false-positive rate (6.4% versus 6.7%)"

The third was caught only by the new cross-document guard, after I had already
told myself the fix was complete.

## 3. `paper.md` retired

It restructured `manuscript.md` for a general venue before the work was split
into two conference papers. After the split it was pure duplication, and
maintaining four write-ups of the same results is what let the drift happen.
Moved to `paper/archive/` with a banner recording that it is superseded and why,
removed from `build.py`, and its four tests deleted rather than left to skip —
four permanently-skipping tests are four lines of green that assert nothing.

## 4. Guards now run across every maintained document

Five new tests, each asserting over the whole set rather than one document:

- `test_no_maintained_document_carries_a_withdrawn_claim` — an explicit registry
  of retracted phrases with the round that retracted each
- `test_every_document_that_compares_nulls_reports_in_regime_rates` — a document
  quoting 4/16 against 12/16 must give the error rates that comparison is made at
- `test_every_document_reporting_torsade_reports_the_matched_result`
- `test_no_document_title_asserts_a_conclusion`
- `test_retired_documents_are_not_built_and_are_labelled`

The second of these failed on first run and caught `paper_b`.

## Status

**329 tests, 0 skipped.** Three maintained documents: `manuscript.md` (8 body
pages), `paper_a.md` (8), `paper_b.md` (7), all under their caps and all
building clean.

## The standing lesson

Every round from 8 onward has produced at least one guard too weak to catch the
defect it was written for — a substring that matched a longer number, a test
requiring only the phrase "companion paper", and now a whole class of guards
scoped to whichever file was open. The pattern is consistent: **a test written by
the same person who just fixed the defect tends to encode where they were
looking, not what must be true.**

Two practices came out of it and are now standard here: mutation-test every new
guard, and scope document-level assertions to the document *set* rather than the
document. Passing tests remain evidence that stated numbers match computed ones —
not that the right quantity was computed, and not that every document says so.
