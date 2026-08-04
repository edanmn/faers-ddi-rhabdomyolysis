# Phase 11 — round-7 review: the inference layer

> **Superseded by `results/canonical_numbers.json`.** Every figure below was
> true when written. Where this file and the canonical numbers disagree, the
> canonical numbers are right.

Rounds 1–6 attacked the pipeline: parsing, deduplication, ingredient
resolution, the estimator. Round 7 attacked the statistics built on top of it,
and found that six rounds of hardening the machinery had gone alongside an
evaluation instrument nobody had audited.

Twenty findings were raised. Four required new computation
(`src/faers_ddi/audit.py`); the rest were corrections to the manuscript, the
artifacts, or the tests. Four **contradicted** claims in the previous version.

---

## 1. The signature finding was framed wrongly (partly)

The paper reported that Ω grows more negative as the marginal associations
strengthen (r = −0.63) and read this as a defect **of the multiplicative null**.

Because Ω = log₂((O+α)/(E+α)) and E rises with the same marginals that form the
x-axis, part of any such correlation is mechanical — regressing a ratio on a
proxy for its own denominator (Oldham's fallacy). Two questions follow, and they
have different answers.

**Is it an artifact? No.** Drawing the triple count from each null's own
expectation and recomputing the statistic 10,000 times gives an induced
correlation centred on zero (median +0.03, 95% interval −0.23 to +0.26). The
observed −0.63 sits outside it. *The initial review claim that the correlation
was an artifact was too strong, and the simulation refuted it.*

**Is it diagnostic of the multiplicative null? No.** The decomposition:

| regressed on log₂(RR_A × RR_B) | r | p |
|---|---:|---:|
| observed event rate among co-reports | **+0.117** | 0.67 |
| expected rate, multiplicative null | +0.941 | — |
| expected rate, additive null | +0.935 | — |
| Ω (multiplicative) | −0.628 | 0.009 |
| **Ω_add (additive — the adopted remedy)** | **−0.646** | **0.007** |

Observed joint risk is flat in marginal strength; both nulls predict it to rise
steeply; **both are wrong in the same direction and at the same slope.** What
separates them is the *level* of the expectation, not its gradient. The same
pattern holds on torsade (Ω −0.810, Ω_add −0.793).

The recovery comparison — 4/16 vs 12/16 at a matched false-positive rate
(6.4% vs 6.7%) — is unaffected and is now the paper's stated primary evidence.

## 2. Threshold calibration was in-sample

`tier_b.py` took the 95th percentile of the negative-control pool whose
false-positive rate it then reported. A quantile evaluated on its own sample
returns the target by construction.

500 random half-splits — calibrate on one half, measure on the other:

| | value |
|---|---|
| in-sample threshold | +0.436 |
| held-out threshold (median) | +0.429 |
| **held-out FPR** | **5.03% (95% CI 4.37–5.74%)** |

The in-sample calibration was very nearly unbiased, so nothing downstream
changes materially — but "expected by chance" becomes **874 (759–997)** rather
than the 869 that merely restated the nominal 5%.

## 3. The reference is structurally blind to the endpoint's own drug classes

**138 of 800 screened ingredients (17.2%) have no openFDA label at all**, so no
pair containing one can ever be `label_documented`: **1,712 of 17,375 pairs
(9.8%)** are undocumentable by construction and fall into the denominator of the
null. Among the unlabelled: **cerivastatin** (withdrawn worldwide *for
rhabdomyolysis with gemfibrozil*), **bezafibrate**, **ciprofibrate**,
**telithromycin**, **fusidic acid**.

Restricting to pairs whose two labels both exist: enrichment 1.24 (0.68–2.26)
crude, **1.067 (0.292–1.972)** stratified. **The negative result survives.**

`§3.6` claimed under-sensitivity biases enrichment downward, "the conservative
direction for a claim that enrichment exists". The paper's claim is that
enrichment does *not* exist, so that bias runs **toward** its own conclusion.
Stated correctly now.

## 4. The screen's top-ranked pair is a contraindicated interaction

Ranked by event rate among co-reports (n_ab ≥ 150):

| rank | pair | rate | band |
|---:|---|---:|---|
| **1** | **ATORVASTATIN + FUSIDIC ACID** | **83.8%** (155/185) | *plausible* |
| 2 | ABIRATERONE + ROSUVASTATIN | 82.7% | *plausible* |
| 3 | INFLUENZA VACCINE + SIMVASTATIN | 78.2% | *plausible* |
| 4 | CYCLOSPORINE + SIMVASTATIN | 71.0% | positive control |

Atorvastatin + fusidic acid outranks **every** positive control, is era-stable
across all three eras, and — unlike the eight `unsupported` era-stable pairs
(88–100% carrying a third myotoxic drug) — carries one on only **8.4%** of its
event cases against a 48.7% background. It is not confounded. It is also not
novel: statin + systemic fusidic acid is contraindicated.

It sits in `plausible` because fusidic acid has no US marketing authorisation,
so openFDA has no label for it, and it is missing from the authors' curated list
too. **§4.7's claim that every era-stable pair traces to confounding was wrong**,
and the two `plausible` pairs — the band designated in advance as the discovery
target — had never been examined.

## 5. The era-stable composition claim does not survive its own standard

§4.6's one surviving positive claim (13.31×, CI 5.42–32.69) used the
*any-endpoint* reference that §4.5 shows is 82% endpoint-irrelevant, and was
unstratified on co-report count — the correction §4.5 calls mandatory.

| reference | scope | documented signalled | crude | stratified |
|---|---|---|---|---|
| any endpoint | all pairs | 10/1,339 | 13.31 (5.42–32.69) | — |
| any endpoint | no control drug | 2/1,069 | 4.45 (0.90–22.0) | — |
| endpoint-specific | all pairs | 8/240 | 51.9 (21.1–127.9) | 32.6 (0.0–173.8) |
| **endpoint-specific** | **no control drug** | **0/142** | — | **0.0** |

**Not one era-stable pair is documented** once the reference is endpoint-specific
and control drugs are removed. The claim rested on the same circularity §4.5
identifies, which the earlier draft asserted it had escaped.

## 6. Smaller corrections

| # | finding | resolution |
|---|---|---|
| Ω = −0.973 | appeared in no output; actual values −0.383/+0.004/−0.480/−0.187 | corrected to **−0.385** (Ω₀₂₅ −0.630) |
| artifact drift | `correlation_points` and `tier_a_results.csv` disagreed in the 3rd decimal on all 16 values, written by different runs | `run_analysis` now writes both; `tier_a.write_results_csv` is the single writer |
| optimism = 0.000 | forced to zero whenever selection is stable; presented as a measurement | reframed as a consequence, not evidence |
| stale §4.9 table | 53,396/320 vs canonical 53,229/321 — passed 280 tests because they asserted *properties*, not values | table regenerated; `test_screen_size_table_values_match_canonical` added |
| mixed thresholds | §4.10 scored Ω at 0 and Ω_add at +0.436 in the same table | both nulls at both thresholds: 29 vs 55 at 0, 15 vs 42 at calibrated |
| no multiplicity control | 17,375 tests, no FDR | BH on Poisson tails: **1,147** discoveries; all 1,022 shrinkage signals inside it, so the shrinkage rule is the more conservative |
| permutation reporting | p = 0.0012 quoted for the author annotation; **p = 0.14** for the independent one omitted | both reported |
| torsade PT list | included CARDIAC ARREST, VT and VF; event rate 0.66% vs 0.207% for the primary | curated to 5 repolarisation-specific PTs → 0.199%, and recovery **improves** to 0/10 vs 9/10 |
| cap chosen on controls | 20 drugs/case improved recovery *and* FPR — a decision made on the evaluation set, undisclosed | full sweep published; **cap 10 is better on both axes** (13/16 at 6.0%); uncapped is 11/16 at 6.9% |
| `cap=None` bug | `build_case_drugs` reads `None` as "use the configured cap", so the "uncapped" arm silently re-ran cap 20 | `NO_CAP = 10_000` sentinel |
| ONC list "unavailable" | it is open-access and was never checked | retrieved; **class-level**, and it explicitly excludes the gemfibrozil–statin pair, so it cannot serve as this endpoint's reference. Stated with the reason. |
| §3.3 table | mixed per-era and cumulative counts; era totals 7 short of the raw | labelled; the 7 are LAERS rows with a NULL `case_id`, verified by query |
| `_INVALID` p-values | shipped in the canonical artifact under a warning suffix | deleted |
| missing citation | additive-vs-multiplicative interaction | VanderWeele & Knol 2014, verified |
| §3.7 before §3.6 | — | renumbered |
| .md / .tex drift | a hand-maintained `.tex` beside the `.md` is the same defect as #6 row 2 | `paper/build.py` generates it; `--check` fails when stale |

## Status

**295 tests passing** (280 → 295; 15 added, all value-level). Full pipeline
re-run end to end: `run_analysis` → `sensitivity` → `generalization` → `audit`
→ `figures` → `build.py`.

Four claims in the previous version were contradicted by this round: the framing
of the Ω correlation, the era-stable composition claim, "every era-stable pair
traces to confounding", and the completeness of the reference. Each is now
stated with the correction visible rather than silently revised.
