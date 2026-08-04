# Phase 4 findings — drug normalization

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

**98.0% of 73,960,283 drug rows resolved to an active ingredient**, from 853,439
distinct verbatim strings down to 400,389 ingredients. All 12 control-set drugs
present and correctly consolidated. No external dictionary required.

## Resolution ladder

| level | laers | faers_early | faers_modern | all |
|---|---:|---:|---:|---:|
| 1 `prod_ai` | 0.0% | 0.0% | 97.8% | 78.3% |
| 2 exact backfill | 90.1% | 87.6% | 0.4% | 18.1% |
| 3 relaxed backfill | 5.6% | 6.5% | 0.5% | 1.6% |
| 4 unresolved | 4.3% | 5.9% | 1.3% | 2.0% |

## The prediction, and what it got right and wrong

Phase 3 closed with a prediction: coverage should be near-total after 2014Q3 and
materially worse in the LAERS years, and *if it isn't worse, something is wrong
with the measurement*.

Half right. Raw `prod_ai` coverage is exactly as predicted — 97.8% in
faers_modern, **0.0%** in both earlier eras, since the column does not exist
before 2014Q3. But the conclusion drawn from that in the plan — that the early
years would need an external dictionary and would end up materially degraded —
was wrong.

The 59M modern rows are themselves an FDA-curated `drugname → active ingredient`
lookup, and the same verbatim strings recur throughout the earlier eras. Applying
that lookup backwards resolves **90.1% of LAERS rows and 87.6% of faers_early
rows** with no external resource at all. A relaxed pass that strips dose, form
and packaging detail (`TOPROL-XL`, `HUMIRA 40 MG/0.8 ML PEN`) adds ~6 points
more.

Final coverage by era is 95.7% / 94.5% / 98.7% — the early eras are *slightly*
worse, not materially so. The planned DiAna and RxNav dependencies were not
needed; if the residual 2.0% ever matters, they remain available for it.

## Salt stripping, and a bug in my own rule

`ATORVASTATIN` and `ATORVASTATIN CALCIUM` must be one drug, not two — otherwise
every statin-interaction count splits across spellings and the signal this study
exists to measure is halved. Trailing salt, ester and hydrate tokens are
therefore stripped, repeatedly, so `FORMOTEROL FUMARATE DIHYDRATE` reduces fully.

Checking for over-merging exposed an inconsistency. `CALCIUM CARBONATE` reduced
to bare `CALCIUM` while `SODIUM CHLORIDE` survived intact — because the token
list contained `CARBONATE` but not `CHLORIDE`. Indefensible in either direction,
and the consequence was real: calcium carbonate, calcium citrate and calcium
acetate were collapsing into one high-volume pseudo-drug that would then have
appeared in the Tier C screen as a meaningless node.

The fix is a protected list of compounds whose head token is an element rather
than a drug, plus completing the token list. `LITHIUM CARBONATE` is deliberately
*not* protected — lithium is the active moiety and lithium citrate is the same
drug, so it correctly reduces to `LITHIUM`.

| after the fix | rows |
|---|---:|
| CALCIUM CARBONATE | 159,053 (was 0) |
| FERROUS SULFATE | 70,520 (was 0) |
| MAGNESIUM SULFATE | 23,541 (was 0) |
| LITHIUM CARBONATE | 0 — correctly folded into LITHIUM |

A further test asserts every protected compound actually ends in a recognised
salt token. It failed on first run: `SODIUM BICARBONATE` and `SODIUM FLUORIDE`
were "protected" from stripping that would never have happened, because
`BICARBONATE` and `FLUORIDE` were missing from the token list. Dead configuration
that read as a working exemption.

## Control-drug acceptance test

Aggregate coverage can look excellent while the specific drugs a study depends on
are missing or fragmented, so each control drug is checked by name:

| drug | reports | | drug | reports |
|---|---:|---|---|---:|
| ATORVASTATIN | 528,898 | | AMIODARONE | 81,879 |
| SIMVASTATIN | 287,492 | | VERAPAMIL | 49,802 |
| ROSUVASTATIN | 231,264 | | CLARITHROMYCIN | 44,425 |
| CYCLOSPORINE | 138,029 | | COLCHICINE | 31,425 |
| DILTIAZEM | 98,006 | | LOVASTATIN | 29,075 |
| GEMFIBROZIL | 16,021 | | ITRACONAZOLE | 13,574 |

Residual fragmentation is a long tail of manufacturer names and typos
(`AMIODARONE HCI`, `SIMVASTATIN STADA`, `ATORVASTATIN XIROMED`) accounting for
**0.1–0.2%** of each drug's rows. Not worth chasing.

## Limitations

- **2.0% of drug rows are unresolved** and retained under their normalised
  verbatim string, flagged with `resolution_level = 4`. They still contribute to
  report counts, so denominators stay correct, and their share is visible rather
  than silently dropped.
- **Level 2 and 3 matches inherit any error in FDA's own `prod_ai` mapping.** The
  backfill is only as good as the modern-era annotation it is derived from.
- **Relaxed matching (1.6%) discards formulation.** `TOPROL-XL` and `TOPROL` map
  to the same ingredient, which is correct at ingredient level but erases a
  distinction that could matter for a formulation-specific interaction.
- **Combination products are split into their constituents**, so each ingredient
  counts toward its own drug. A report of a fixed-dose combination therefore
  contributes to two drugs — correct for ingredient-level analysis, but it means
  co-prescription counts include single-pill combinations.
