# Phase 7 findings — Tier B negative controls

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

**False-positive rate is 6.2% at the nominal threshold, against a nominal 2.5%.**
Calibrated threshold set to **Ω_add,025 > +0.305**, which holds the rate at 5%
and costs nothing in sensitivity.

| stratum | n | FPR additive | FPR multiplicative |
|---|---:|---:|---:|
| easy (neither drug event-associated) | 1,000 | 4.4% | 4.7% |
| **hard (one drug event-associated)** | 1,000 | **8.0%** | 7.2% |
| all | 2,000 | 6.2% | 5.9% |

Operating characteristic, against the 14 adequately powered positive controls:

| threshold | sensitivity | FPR (all) | FPR (hard) |
|---:|---:|---:|---:|
| +0.00 (nominal) | 86% | 6.2% | 8.0% |
| **+0.305 (adopted)** | **86%** | **~5.0%** | ~6.5% |
| +0.50 | 71% | 4.7% | 5.8% |
| +1.00 | 57% | 3.1% | 3.7% |

## My prediction was wrong

I predicted 10–25%, and said that a result near the nominal 2.5% would mean the
negative controls were too easy rather than that the threshold was well
calibrated. The measured rate is **6.2%** — above nominal, below my range.

The direction of my reasoning held: the rate is ~2.5× nominal, and the hard
stratum is roughly double the easy one, so stratifying was worth doing. The
magnitude was not. I over-estimated how much unmodelled confounding survives
into a shrunk lower credibility bound.

## n = 50 was uselessly small, and it inverted the answer

The configured null set size was 50. A 95th-percentile calibration on 50 pairs
is the second-highest observation.

| | n = 50 | n = 2,000 |
|---|---|---|
| easy stratum FPR | 12.0% | 4.4% |
| hard stratum FPR | 8.0% | 8.0% |
| easy vs hard | easy **worse** | hard **worse** |
| calibrated 5% threshold | **+2.358** | **+0.305** |

At n = 50 the strata differ by 3 pairs against 2. That noise reversed the
qualitative conclusion and produced a threshold nearly eight times too strict —
one that would have cut Tier A recovery to about 2/16 while appearing rigorous.
`n_pairs` is now 2,000.

## The real finding: 0.09% of cases supply a third of all evidence

The strongest false positive was `ALIROCUMAB+IPRATROPIUM`: 88 co-reports, **88
events**. A 100% event rate.

Alirocumab is a PCSK9 inhibitor given to statin-intolerant patients, so
indication confounding was the obvious explanation. It was not the main one.
Those 88 cases have **5 distinct event dates, 1 distinct age and 2 sexes**
between them, and each lists **31–40 drugs**. They are residual near-duplicates
that the Phase 3 exact-set fingerprint could not merge because their drug lists
differ slightly.

A case listing 40 drugs contributes C(40,2) = 780 pairs. Across the database:

| drugs/case | cases | % of all pairs | event rate |
|---|---:|---:|---:|
| 1 | 15,366,836 | 0.0% | 0.13% |
| 2–5 | 4,424,434 | 28.6% | 0.43% |
| 6–10 | 411,109 | 22.3% | 0.53% |
| 11–20 | 71,563 | 14.4% | 0.67% |
| 21–30 | 9,861 | 6.7% | 0.85% |
| 31–50 | 5,842 | 10.0% | **1.44%** |
| 51+ | 3,302 | **18.0%** | 0.03% |

**19,005 cases — 0.09% of the database — contribute 34.7% of all drug pairs**, at
a 4× enriched event rate. One report in a thousand was driving a third of the
pair-level evidence, and precisely the event-enriched third. The 51+ group alone,
3,302 cases, supplies 18% of all pairs.

## Capping at 20 drugs improves both directions at once

| | before | after |
|---|---:|---:|
| Tier A recovery (primary/core) | 11/16 | **12/16** |
| Tier B FPR, all | 6.9% | **6.2%** |
| Tier B FPR, hard stratum | 9.2% | **8.0%** |
| alirocumab pairs in null set | 3 | **0** |

Not a trade-off: sensitivity rose and false positives fell. High-polypharmacy
reports were adding noise to the positive controls as well as manufacturing
spurious pairs. Sensitivity analyses at caps of 10 and 30 are configured.

This is what Tier B is for. Nothing in Tier A could have revealed it — the
positive controls recovered adequately with the polypharmacy cases included, and
the leverage problem was only visible from the false-positive side.

## Limitations

- **No DDI reference database.** The configured criteria call for excluding pairs
  documented in DrugBank and pairs sharing an ATC-3 class; neither resource is
  available yet. Exclusion falls back on a hand-curated list of 60 agents
  implicated in myotoxicity. Some generated "negatives" are therefore likely to
  be genuine undocumented interactions, so **6.2% is an upper bound** on the
  false-positive rate, not an estimate. The bias favours a stricter threshold,
  which is the safe direction.
- **The additive measure is anti-conservative for low-marginal pairs.** When both
  drugs have RR < 2 the additive expectation is close to baseline × n_ab, so a
  small absolute excess produces a large log ratio. `BUDESONIDE+SALMETEROL`
  reaches Ω_add,025 = 4.00 on 14 events among 1,975 co-reports. A
  stratum-specific threshold would fit better than the single value adopted here.
- **Sensitivity rests on 14 positive controls**, so each is worth 7 percentage
  points. The operating characteristic is coarse and the choice of +0.305 over
  +0.25 is not meaningfully supported by this data — both give 86%.
- **Residual near-duplicates remain.** The cap removes their leverage but not the
  clusters themselves; a fuzzy drug-set match (Jaccard rather than exact) would
  catch more, and is not implemented.
