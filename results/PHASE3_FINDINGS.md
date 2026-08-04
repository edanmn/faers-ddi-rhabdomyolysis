# Phase 3 findings — deduplication

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

**24,812,425 raw DEMO rows → 20,293,421 distinct cases** (81.8% retained).

| stage | remaining | removed | rule |
|---|---:|---:|---|
| 0 raw DEMO rows | 24,812,425 | — | 90 quarters |
| 1 within-LAERS | 3,091,161 | 1,185,033 | highest `isr` per case |
| 2 within-FAERS | 17,683,864 | 2,852,360 | highest `caseversion` per caseid |
| 3 cross-era bridge | 20,692,683 | 82,342 | ids in both eras; FAERS record kept |
| 4 deleted cases | 20,588,497 | 104,186 | FDA-withdrawn case ids |
| 5 near-duplicates | 20,294,190 | 294,307 | event+age+drug set+PT set match |
| 6 one case per report | **20,293,421** | 769 | reports under two case numbers |

Sensitivity on the stage-5 rule: 20,102,124 (−486,373). The final count moves by
0.9% under the looser alternative.

Both keys are unique in the output: `case_id`, and `(era, report_id)` — the key
DRUG and REAC are joined on. 73,960,318 drug rows survive against surviving
cases, 73.6% of the raw 100.5M.

---

## The era bridge is real, and it was worth testing rather than assuming

The plan flagged the shared id space as an assumption to verify. 82,342 case ids
appear in both eras — 2.7% of LAERS cases, equally consistent with a shared
numbering where few cases span the boundary or with two independent numberings
occupying overlapping ranges. The ranges do overlap heavily (LAERS 3.0M–1.0B,
FAERS 3.0M–27.0M), so range alone settles nothing.

Comparing demographics on the overlapping ids against a chance baseline settles
it:

| | event_dt | sex | age | all three |
|---|---:|---:|---:|---:|
| matched ids (n=82,342) | 33.3% | 85.2% | 54.2% | 26.0% |
| chance baseline (n=3,091,162) | 0.0% | 38.8% | 0.5% | 0.0% |

Agreement far above chance on fields that would be unrelated under independent
numbering. It is not 100% because follow-up versions revise these fields and half
of all records leave `event_dt` blank — but 33% against 0.0% is unambiguous. The
bridge is applied; skipping it would double count 82,342 cases.

## The near-duplicate rule was wrong, and the error was large

The configured rule was "any 4 of the 6 fingerprint fields populated". It removed
**2,980,676 cases — 14.5%** — against 3–8% typical in published FAERS work.

The distribution of duplicate-group sizes showed why. The largest group held
**9,270 cases**, and every one of the largest groups sat exactly at the
`populated = 4` threshold. That is not a report submitted 9,270 times; it is a
fingerprint collision among sparse records.

The flaw is that a count treats every field as equal evidence. Country is nearly
constant (mostly US) and sex is binary, so a record with only sex, country, one
drug and one PT clears a 4-of-6 bar while carrying almost no identifying
information. Records missing both `event_dt` and age — the two strongest
discriminators — collapsed wholesale.

Measured alternatives:

| rule | eligible | removed | rate | max group | cases in groups >100 |
|---|---:|---:|---:|---:|---:|
| any 4 of 6 | 18,903,267 | 2,980,676 | 14.5% | 9,270 | 762,456 |
| any 5 of 6 | 13,226,932 | 914,924 | 4.4% | 775 | 32,716 |
| all 6 | 8,052,665 | 288,951 | 1.4% | 36 | 0 |
| event+drug+pt | 10,349,201 | 486,373 | 2.4% | 775 | 25,829 |
| **event+age+drug+pt** | **8,334,929** | **294,307** | **1.4%** | **36** | **0** |

Eligibility is now expressed as *required fields* rather than a count. The chosen
rule covers more cases than demanding all six while producing the same maximum
group size and no group above 100. `event+drug+pt` is carried as the sensitivity
analysis.

**Coverage limitation, stated plainly:** only 8.3M of 20.6M cases have the fields
needed to judge duplication at all — `event_dt` is populated on just 49.5% of
records and age on 58.0%. The remaining cases are kept unexamined. Duplicates
inflate exactly the co-occurrence counts a DDI signal is built from, so this is
not a harmless direction to err in; but a false merge destroys a real report
outright, and merging on a fingerprint of blanks is not deduplication. Keeping is
the defensible choice, and the residual duplicate rate is a limitation for the
discussion, not something the data can resolve.

## Two staging bugs found by reading the attrition table

**Stage 3 removed 181,066 rows where 82,342 were expected.** The cause was in my
staging, not the data: `era` has three values but only two id spaces, and stage 2
partitioned by `era`, so `faers_early` and `faers_modern` were deduplicated
separately despite sharing one `caseid` space. The ~98k cases spanning them then
fell to stage 3. The final count was correct either way — which is precisely why
this needed the attrition table to catch. Stage 2 now partitions on the era
*group* and stage 3 removes exactly 82,342.

**769 reports appeared under two case numbers.** After stage 5, `case_id` was
unique but `(era, report_id)` was not: 769 LAERS reports appear in consecutive
quarters with a reassigned `case` (same `isr`, same patient). Since DRUG and REAC
are joined on `(era, report_id)`, 5,682 drug rows would have been attributed to
two cases each and double-counted into the co-occurrence tables. Stage 6 enforces
one case per report, keeping the later quarter's corrected case number.

## Carried forward

The general lesson from this phase repeats Phase 2's: the failures were visible
in *counts that did not match a prediction*, not in errors. Stage 3's 181,066 vs
82,342 and stage 5's 14.5% vs a 3–8% expectation both surfaced only because there
was a number to check against beforehand. Phase 5 onward should predict the
magnitude of each filter before running it.
