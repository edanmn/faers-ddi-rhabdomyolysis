# Phase 10 findings — confounding by clinical context

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

Phase 9 ended with the screen's top ranks dominated by ICU and anaesthesia
drugs, and I proposed restricting to ambulatory reports as a fix. That was
worth doing and **the hypothesis was wrong**.

## Restricting to ambulatory reports changes almost nothing

Excluding every case containing an inpatient/critical-care marker — neuromuscular
blockers, general anaesthetics, vasopressors, IV fluids — removes 275,205 cases
(1.4%).

| band | primary (all reports) | ambulatory | |
|---|---:|---:|---|
| positive_control | 80.0% (12.0×) | 80.0% (12.8×) | unchanged |
| known_pair | 12.9% (1.93×) | 12.0% (1.92×) | unchanged |
| **plausible** | **5.2% (0.78×)** | **5.0% (0.80×)** | **still no enrichment** |
| unsupported | 6.7% (1.00×) | 6.3% (1.00×) | — |

The ICU pairs do leave the top — rocuronium, IV saline and norepinephrine are
gone. But the screen's discriminative structure is identical, and the
`plausible` band still shows no enrichment whatsoever. Removing the confounder
removed its symptoms without improving the instrument.

## Because the confounding is structural, not specific

The new top of the ranking is simply a different flavour of the same problem:

    ESOMEPRAZOLE + INSULIN GLARGINE     NALOXONE + ZOPICLONE
    APIXABAN + INSULIN GLARGINE         CODEINE + LOSARTAN

`NALOXONE+ZOPICLONE` is an overdose signature — rhabdomyolysis from prolonged
immobilisation after an overdose. Confirmed directly: **64.9% of that pair's
event cases carry an overdose or impaired-consciousness PT, against a 13.2%
background — 4.9×.**

Rhabdomyolysis has many non-interaction causes: critical illness, overdose and
immobility, trauma, exertion, seizure. Each has its own drug signature. Excluding
one marker set reveals the next. There is no single adjustment that fixes this,
which is why the negative result from Phase 9 stands rather than being an
artefact of one unmodelled confounder.

## An unexpectedly clean triage signal

The overdose fraction separates confounded hits from pharmacological ones
sharply:

| pair | overdose PT | vs background | |
|---|---:|---:|---|
| naloxone + zopiclone | 64.9% | 4.9× | confounded |
| codeine + losartan | 16.7% | 1.3× | unclear |
| dextroamphetamine + paroxetine | 13.3% | 1.0× | unclear |
| esomeprazole + insulin glargine | 0.0% | 0.0× | not overdose |
| cyclosporine + diltiazem | 9.4% | 0.7× | genuine |
| fluconazole + simvastatin | 4.4% | 0.3× | genuine |
| **clarithromycin + simvastatin** | **0.4%** | **0.03×** | **genuine** |

Every established interaction sits below background; the overdose-driven pair
sits far above it. This is a per-pair diagnostic that costs one query and should
accompany any hit reported in the paper — a signal whose cases are mostly
overdose reports is not evidence of a pharmacokinetic interaction, however large
its Ω_add.

It does not explain everything. `ESOMEPRAZOLE+INSULIN GLARGINE` has a **0.0%**
overdose fraction and is still almost certainly confounded — by diabetic
polypharmacy and shared indication rather than by acute events. Different
confounders need different diagnostics.

## What this means for the study

The Phase 9 conclusion is unchanged and now better supported:

1. The pipeline demonstrably recovers real pharmacology — 80% of positive
   controls, 1.9× enrichment of known interaction pairs, and independent
   rediscovery of fluconazole + simvastatin and the HIV-booster/statin pairs.
2. It shows no capability to detect novel interactions, and that limitation
   survives the most obvious confounding adjustment.
3. Reporting an individual `plausible` hit as a discovery would not be supported.

The honest deliverable is a validated method with a characterised false-positive
rate and a negative discovery finding — not a list of new interactions.

## Limitations

- **The ambulatory restriction is blunt.** It costs propofol entirely, and
  propofol infusion syndrome is a genuine myotoxicity, so that mechanism is
  unstudiable under the restriction.
- **The overdose PT list is hand-built**, like the myotoxicity list, and shares
  its weaknesses.
- **Only two confounders were examined** — critical care and overdose. Trauma,
  exertional and seizure-related rhabdomyolysis were not, and the structural
  argument predicts they behave the same way.
- **Indication data was not used.** The `INDI` table is parsed and available
  (63.2M rows) but conditioning on indication is not implemented; that is the
  most promising remaining adjustment and the natural next step.
