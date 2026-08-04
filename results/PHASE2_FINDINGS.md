# Phase 2 findings — parsing 90 quarters to Parquet

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

**328,476,258 rows** across 630 table-quarters, 20.04 GB of delimited text into
2.57 GB of Parquet, in about three minutes.

| table | rows | Parquet MB |
|---|---:|---:|
| drug | 100,511,908 | 1,139 |
| reac | 82,257,716 | 319 |
| indi | 63,213,861 | 249 |
| ther | 35,772,081 | 230 |
| demo | 24,812,425 | 534 |
| outc | 19,191,409 | 85 |
| rpsr | 2,716,858 | 11 |

Quality: **3 skipped rows out of 328 million**, 7 unparseable ids, zero decode
errors, and **zero referential-integrity orphans** — every row in every child
table resolves to a DEMO row in its own quarter.

Plus 229,233 unique deleted case ids extracted from 31 files across five naming
conventions.

---

## Two silent-corruption bugs

Both would have produced a complete, plausible-looking dataset and a finished
paper built on wrong numbers. Neither raised anything.

### 1. A trailing delimiter shifted every column in the dataset

Every data line in every FAERS table ends with a delimiter its header does not
declare. LAERS REAC declares `ISR$PT` over rows like:

```
4204616$ABDOMINAL PAIN$
```

Three fields, two names. Given more fields than names, pandas promotes the
surplus leading column to the **index** and shifts every remaining column left
by one. `report_id` received the PT text; the real id vanished into the index.
No bad-line report, no exception, no warning.

**This applied to every table in every quarter — 100% of the 328 million rows.**

The dangerous part is how nearly it escaped. It was caught only because REAC's
second column holds text, so the integer cast failed loudly. In DRUG the same
shift moves `drug_seq` into `report_id` — both integers. Every type check passes.
The pipeline runs to completion, and every drug is attributed to the wrong
report. Had DRUG been checked first, nothing would have looked wrong.

Fixed with `index_col=False` plus a padded name list whose placeholder columns
are checked for content before being dropped, so a table genuinely carrying
undeclared data is reported rather than discarded. Guarded by
`test_trailing_delimiter_does_not_shift_an_all_integer_table`, which asserts on
values rather than dtypes precisely because dtypes cannot see this.

### 2. One quarter lost its entire demographics table to a filename

FDA ships 2018Q1 demographics as **`DEMO18Q1_new.txt`**, not `DEMO18Q1.txt`. The
member pattern anchored on `Q<digit>.TXT`, so the file was classified as
documentation and never read. The quarter parsed six tables instead of seven and
logged nothing unusual.

DEMO carries the report universe, sex, age, and case versions, so 2018Q1 would
have been silently absent from every downstream stage — including the case
deduplication and the report denominators that all disproportionality rests on.

Caught by the referential-integrity check: 2018Q1 REAC showed a **100% orphan
rate** while all 89 other quarters showed exactly 0%. The concentration is what
gave it away — a diffuse 1–2% would have looked like ordinary FDA untidiness.

Two fixes: the member pattern now tolerates a suffix, and `parse_quarter` raises
when a quarter yields fewer tables than expected rather than proceeding with a
short quarter.

### 3. The regression test for bug 2 corrupted the dataset

The test written to guard against the missing-table bug called `parse_quarter`
with a mocked archive but did **not** redirect the output directory.
`parse_quarter` writes each table as it goes and only checks for missing tables
at the end, so the test wrote its one-row REAC fixture over the real
`reac_2004q1.parquet` — destroying 264,409 rows.

Caught on the next validation run: `reac` was short by exactly 264,409 rows
against the manifest. The test now redirects both input and output into
`tmp_path`, and `parse_quarter` no longer raises when the output path lies
outside the project root.

The lesson is that a test which exercises a write path needs its output
redirected as deliberately as its input is mocked, and that running validation
after the test suite — not only after the pipeline — is what surfaced it.

---

## What this changed about the approach

The checks that caught both bugs were structural, not statistical. Row counts
were plausible throughout; nothing was null; no exception was raised. What
exposed the problems was asserting a relationship that must hold — every child
row resolves to a parent in its own quarter — and then noticing that a violation
was *concentrated* rather than spread.

Carried forward into Phase 3:

1. **Validate on invariants, not on plausibility.** Every stage should assert a
   relationship that must hold by construction, and fail rather than warn.
2. **Look at the distribution of violations, not just the rate.** A 2% aggregate
   orphan rate looked acceptable; it was one quarter at 100%.
3. **A "should be impossible" tolerance must be zero.** The orphan limit was set
   at 2% on the assumption that FDA ships some unparented child rows. The true
   value is exactly 0, and the loose threshold nearly let a broken quarter pass.
   The threshold is now known to be tightenable and should be tightened.
