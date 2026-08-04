# Detecting Drug–Drug Interaction Signals for Rhabdomyolysis in FAERS

A disproportionality analysis of drug–drug interaction (DDI) signals for
rhabdomyolysis and related myotoxicity, using the complete public history of the
FDA Adverse Event Reporting System: **2004Q1 – 2026Q2, 90 quarters**.

## Design

Three tiers, run in order. Each is a gate on the next.

| Tier | Purpose | Pass condition |
|------|---------|----------------|
| **A — Positive controls** | Can the pipeline recover interactions we already know are real? | **12/16 (12/14 with adequate power)** |
| **B — Negative controls** | What is the false-positive rate? | **6.7% on 16,138 generated frequency-matched pairs (the full eligible pool, not a sample); threshold calibrated to +0.436** |
| **C — Screen** | Discovery | 17,375 pairs among the top 200 drugs. **No enrichment in the novel-discovery band (0.76×)** |

Tier C is not run until Tier A passes. A pipeline that cannot find
simvastatin + amiodarone cannot be trusted to have found anything new.

## Statistics

**Primary measure is Ω_add,025 — an ADDITIVE null, not the multiplicative Ω the
protocol specified.** Ω (Norén et al. 2008) was pre-specified, failed at 2/16
positive controls, and was replaced after that failure. Both are computed and
reported for every pair; the change and its justification are stated in the
manuscript abstract, not buried in methods.

The reason is that this event's leading reported causes are the drugs under
study, so marginal RRs run 3–19 and the multiplicative null predicts joint event
rates of 13–85% among co-reports. Ω correlates at r = −0.42 with
log2(RR_A × RR_B): the better established the interaction, the more protective
it looks. Departure from *additivity* is the standard criterion for clinically
meaningful interaction.

Ω is fitted exactly by IPF rather than the published closed-form approximation,
which we measured at up to 237% error in the regime real drug/event tables
occupy.

Sensitivity analyses: suspect-only vs. all drug roles, core vs. broad event
tier, polypharmacy caps of 10/20/30, ambulatory restriction, and era-stratified
estimates. **The era stratification turned out to matter more than any of them** —
see the headline result.

## Layout

```
config/          config.yaml, control sets, MedDRA PT lists
data/raw/        FDA zips, untouched
data/interim/    parsed parquet
data/processed/  faers.duckdb
data/reference/  (unused - ingredient resolution needed no external source)
src/faers_ddi/   the pipeline, one module per stage
results/         tables, figures, logs
paper/           manuscript
tests/           224 tests; Ω validated by invariants, not source-verified
```

## Pipeline stages

| Phase | Module | Output |
|-------|--------|--------|
| 0 | — | environment, scaffold, config |
| 1 | `00_download.py` | 90 quarterly zips + checksum manifest |
| 1a | `01a_column_audit.py` | actual column manifest per table per quarter |
| 2 | `01_parse.py` | parquet, via a schema adapter driven by the audit |
| 3 | `02_dedup.py` | deduplicated case set + attrition table |
| 4 | `03_normalize_drugs.py` | ingredient-level drug names + coverage-by-era table |
| 5 | `04_define_event.py` | curated PT list verified against observed REAC terms |
| 6 | `05_contingency.py`, `06_omega.py` | Ω₀₂₅ implementation + unit tests |
| 7 | `08_controls_eval.py` | Tier A results |
| 8 | `08_controls_eval.py` | Tier B results, calibrated threshold |
| 9 | `09_screen.py` | Tier C ranked table |
| 10 | `07_logistic.py` | sensitivity analyses |
| 11 | `triage.py` | era stability + confounding diagnostics per pair |
| 12 | `paper/manuscript.md` | manuscript |

**Status: complete.** All phases run. See `paper/manuscript.md` for the result and
`results/PHASE*_FINDINGS.md` for per-phase detail including errors made and corrected.

## Headline result

The pipeline recovers 12/14 adequately powered positive controls, has a measured
false-positive rate of 6.7% (calibrated threshold +0.436), and independently
rediscovers established interactions never supplied to it — including both
fusidic acid + statin pairs, a contraindicated combination causing fatal
rhabdomyolysis, at 155 events among 185 co-reports.

It does **not** demonstrate capacity to find novel interactions, and the
evidence is weaker than an earlier version of this work claimed. Every
positive-control drug is also on the list defining "known pair", so the pooled
enrichment is circular. Restricted to pairs containing no control drug,
enrichment is **1.12x (95% CI 0.69-1.81)** — indistinguishable from
unity. Every temporally stable signal without prior support traced to
confounding; most carried a statin on 88-100% of their event cases against a
40.5% background.

Three transferable findings:

1. **The multiplicative null (Ω) fails when the drugs under study are the leading
   causes of the outcome.** Pre-specified, it recovered 4/16 controls and scored
   simvastatin+amiodarone at -0.973; it correlates at r = -0.42 with
   log2(RR_A x RR_B). An additive null recovers 12/16.
2. **High-polypharmacy reports have extreme leverage.** 0.09% of cases supplied
   34.7% of all drug pairs at a 4x enriched event rate.
3. **Temporal stability does NOT survive validation.** An earlier version of
   this work promoted it as the main contribution. Applied to negative controls
   the filter admits 0.093% of them, implying 16 era-stable pairs by
   chance against 19 observed. The count is not distinguishable from the
   null. Reported here as a negative result.

## Reproducing

```bash
python -m faers_ddi.verify_controls --write   # check the 16 controls vs FDA labels
python -m faers_ddi.run_analysis    # writes results/canonical_numbers.json
python -m faers_ddi.sensitivity     # design-choice sensitivity analyses
python -m faers_ddi.generalization  # torsade / anaphylaxis replication
python -m faers_ddi.audit           # induced-correlation, held-out calibration,
                                    # reference coverage, FDR, cap sweep
python -m faers_ddi.regime          # error rates in the drug-dominant regime,
                                    # purpose-built high-marginal negative pool
python -m faers_ddi.figures         # all seven figures, from canonical numbers
python -m pytest                    # asserts the prose matches it

python paper/build.py               # both documents: .md -> .tex -> .pdf
python paper/build.py --only paper  # just one of them
python paper/build.py --check       # fails if either .tex is stale
```

Every figure quoted in `paper/manuscript.md` and in this file is checked against
`results/canonical_numbers.json` by `tests/test_canonical_numbers.py`. That test
exists because the write-ups previously carried figures from three different
generations of the pipeline.

Three documents are maintained, all from the same canonical numbers:

| file | format | body cap |
|---|---|---|
| `paper/manuscript.md` | full-detail version / preprint | none |
| `paper/paper_a.md` | **calibration**: error rates of the two nulls in the drug-dominant regime | 8 pages |
| `paper/paper_b.md` | **evaluation**: annotation independence, reference coverage | 8 pages |

`paper_a` and `paper_b` are two-column and carry an 8-page body cap excluding
references. `paper/build.py` pushes references onto a fresh page with
`\clearpage`, reads the page number of the resulting label from the `.aux`, and
**exits non-zero if the body exceeds the cap** — the limit is enforced by the
build, not checked by eye.

A fourth document, `paper.md`, was retired in round 11 and moved to
`paper/archive/`. Maintaining four write-ups is what allowed a corrected claim
to land in two of them and not the others; the test suite passed throughout,
because each round's guards were written against whichever documents happened to
be open. `tests/test_canonical_numbers.py` now asserts the withdrawn-claim and
in-regime-rate checks across **every** maintained document rather than one at a
time.

`paper/manuscript.md` is the single source of truth. `manuscript.tex` and
`manuscript.pdf` are **generated** by `paper/build.py` (pandoc + tectonic) and
must not be edited by hand: a second hand-maintained copy is free to drift from
the first, which is precisely the defect that put `tier_a_results.csv` and
`canonical_numbers.json` a third-decimal apart on all 16 control values.

## Schema eras

FAERS is not one format. Filename prefixes and the era boundaries below were
verified against the live FDA server, not taken from documentation:

- `aers_ascii_*` (LAERS), 2004Q1 – 2012Q3, 35 quarters — keyed on `isr`/`case`
- `faers_ascii_*`, 2012Q4 – 2026Q2, 55 quarters — keyed on `primaryid`/`caseid`
- `prod_ai` (active ingredient) exists only from 2014Q3, so drug normalization
  for the earlier ~40% of quarters relies on verbatim `drugname`

The era metadata in `config.yaml` is an *expectation*. Phase 1a reads the real
headers and is authoritative where the two disagree.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
```

## Limitations (stated up front)

Spontaneous reporting has no exposure denominator. Nothing here estimates risk —
only *reporting disproportionality*. Signals are hypotheses subject to
notoriety, masking, and indication bias — and confounding by clinical context
dominates the pooled screen's top ranks. MedDRA hierarchy and SMQs require a
license, so event definition is PT-level only. No DDI reference database was
available, so support annotation uses a hand-curated list and the measured
false-positive rate is an upper bound.

(An earlier draft of this file stated that deleted-case lists exist only for part
of the window. That was wrong — the Phase 1a audit found them for every quarter
from 2019Q1 under five different naming conventions, giving complete coverage.)

**This repository is research code. It is not clinical guidance.**
