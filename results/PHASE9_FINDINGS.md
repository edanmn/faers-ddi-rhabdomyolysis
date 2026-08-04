# Phase 9 findings — the Tier C screen

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

17,375 pairs tested among the 200 drugs most co-reported with myotoxicity.
**1,131 above the calibrated threshold (6.5%), of which roughly 870 are expected
by chance.**

The headline is a validated method and a negative discovery result:

- **The screen independently rediscovers established interactions that were not
  in the control set.** Known interaction pairs are enriched 1.93× over
  background (p = 1.3 × 10⁻⁷).
- **It provides no evidence of detecting novel interactions.** The band where a
  new finding would live shows *no* enrichment at all — 0.78×, below background.
- **The top of the ranking is contaminated by clinical-context confounding**,
  not drug interaction: the top 100 is 2.9× enriched for ICU and anaesthesia
  drugs.

## Signal rate by prior support

| band | signalled | rate | enrichment | p |
|---|---|---:|---:|---|
| positive_control | 12/15 | 80.0% | 12.0× | 2.9e-12 |
| known_pair (both drugs implicated) | 70/543 | 12.9% | 1.93× | 1.3e-07 |
| plausible (one drug implicated) | 256/4,930 | 5.2% | 0.78× | 1 |
| unsupported (neither) | 793/11,887 | 6.7% | 1.00× | — |

The first two rows are the validation. The third is the result.

`plausible` was designated in advance as the band where a real but undocumented
interaction would appear: one genuinely myotoxic drug plus a partner not yet
implicated. It shows no enrichment whatsoever. Whatever true novel interactions
exist in this data, this screen does not separate them from noise at a rate the
design can detect.

## What the screen rediscovered

The most credible hits — both drugs independently implicated in myotoxicity, but
the pair **absent from the 16-pair positive control set**:

| pair | n_ab | n_abz | Ω_add,025 | mechanism |
|---|---:|---:|---:|---|
| cyclosporine + diltiazem | 81 | 32 | 3.58 | CYP3A4 + P-gp |
| cyclosporine + ranolazine | 13 | 12 | 3.22 | CYP3A4 + P-gp |
| pravastatin + ritonavir | 85 | 37 | 2.75 | OATP1B1 |
| cobicistat + pravastatin | 23 | 16 | 2.68 | pharmacokinetic booster |
| cobicistat + fenofibrate | 17 | 16 | 2.67 | pharmacokinetic booster |
| cyclosporine + lovastatin | 23 | 18 | 2.27 | contraindicated on label |
| **fluconazole + simvastatin** | **234** | **137** | **2.12** | **CYP3A4 inhibition** |
| simvastatin + sirolimus | 58 | 38 | 2.06 | CYP3A4 |
| atorvastatin + cyclosporine | 474 | 116 | 1.90 | OATP1B1 + CYP3A4 |

Fluconazole + simvastatin is the strongest single piece of evidence that the
pipeline works. It is a textbook CYP3A4 interaction, it is not in the control
set, and the screen surfaced it on 234 co-reports with 137 events. The HIV
booster pairs (cobicistat, ritonavir, raltegravir with statins) are likewise
real and were not supplied to the method.

## The top of the ranking is confounded, not informative

Both of my pre-stated predictions were wrong, and the second was wrong in a
useful way.

I predicted 300–800 pairs above threshold; the count is **1,131**. I predicted
the ranking would be topped by statin and fibrate pairs already known. It is
not. The top 15 is dominated by a recurring structure:

    PALIPERIDONE + SODIUM CHLORIDE      PAROXETINE + ROCURONIUM
    CLOZAPINE + SODIUM CHLORIDE         QUETIAPINE + ROCURONIUM
    NOREPINEPHRINE + PAROXETINE         DIAZEPAM + ROCURONIUM

One drug is a hospital or ICU context marker — rocuronium, IV saline,
norepinephrine, a benzodiazepine — and the other is a psychotropic. These are
critically ill patients in whom rhabdomyolysis is common, and antipsychotics
cause it through neuroleptic malignant syndrome. The association is real; the
*interaction* is not. The top 100 pairs are **2.9× enriched** for ICU/anaesthesia
drugs relative to their share of pairs tested.

Nothing in the additive null accounts for shared clinical setting. This is the
single largest limitation of the screen as built.

## A bug the failed prediction exposed

The first screen run ranked `DEXAMETHASONE+LENALIDOMIDE` first out of 17,375
pairs: 38,469 co-reports, 53 events, additive expected **0.0**.

An expectation of zero on 38,469 co-reports is impossible, and the cause was in
`additive_expected`. Where a drug is reported with the event *less* often than
the database background its excess risk is negative, so
P(Z|A) + P(Z|B) − P(Z) can fall below zero; I clipped it at zero, which makes
Ω_add = log2(2n + 1) — unbounded in the observed count. That pair has an event
rate of 0.138% against a 0.207% background. **A negative association was ranked
as the strongest signal in the database.**

The expectation is now floored at max(P(Z|A), P(Z|B)) instead: adding a second
drug cannot make the event less likely than the more dangerous drug alone. Where
both risks exceed background — the case the additive model exists for — the
floor never binds and the formula is unchanged. Four regression tests cover it.

This is exactly what the prediction was for. "The top will be pairs I already
know" was checkable, it failed, and the failure was a bug rather than a
discovery.

## Limitations

- **Confounding by clinical context is unmodelled and dominates the top of the
  ranking.** Restricting to ambulatory reports, or conditioning on indication,
  would be the fix. Neither is implemented.
- **No enrichment in the `plausible` band means no demonstrated discovery
  capability.** Reporting any individual `plausible` hit as a finding would not
  be supported by this analysis.
- **~870 of the 1,131 signals are expected by chance.** Membership in the list
  carries almost no information; only rank and prior support do.
- **Support annotation depends on the hand-curated 60-agent list**, not a DDI
  reference database. `known_pair` enrichment is therefore measured against my
  own list, which is a weaker instrument than DrugBank would be.
- **The screen covers only the top 200 drugs by event co-reporting**, so a real
  interaction involving an uncommon drug is out of scope by construction.
