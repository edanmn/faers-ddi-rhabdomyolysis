# Phase 12 — round-8 review: control sets and the specification space

> **Superseded by `results/canonical_numbers.json`.** Where this file and the
> canonical numbers disagree, the canonical numbers are right.

Round 7 audited the statistics. Round 8 audited the things underneath them that
no round had looked at: the control sets, the space of design choices, and the
instruments used for confounder adjustment. Ten findings; two of the eight
checks run came back clean and are recorded as such.

---

## 1. A specification arm that reverses the headline, unreported

Two binary design choices exist — event tier (`core`/`broad`) and drug role
policy (`primary`/`sensitivity`). All four arms were computed and shipped in
`tier_a_results.csv`. **One was reported.**

| tier | policy | additive | multiplicative | advantage |
|---|---|---:|---:|---:|
| **core** | **primary** *(pre-specified)* | **12/16** | **4/16** | **+8** |
| core | sensitivity | 12/16 | 4/16 | +8 |
| broad | primary | 11/16 | 4/16 | +7 |
| **broad** | **sensitivity** | **6/16** | **6/16** | **0** |

Under the widest event definition *and* the widest role policy the additive
null's advantage **vanishes entirely**. `core`/`primary` is genuinely
pre-specified (`config.yaml: event.primary_tier`), so this is not
cherry-picking — but the manuscript never disclosed that four arms existed, and
"broad tier" appeared zero times in the Results.

The grid is now `numbers["specification_grid"]`, published as a table in §4.3,
with the pre-specified arm marked. The test asserts each arm appears as a
**table row** rather than as a substring — the first version of the guard passed
with the row deleted, because `6/16` also occurs inside `16/16`.

## 2. The control set is five drugs, not sixteen trials

| victim | pairs | recovered (powered) |
|---|---:|---:|
| SIMVASTATIN | 7 | 7/7 |
| COLCHICINE | 3 | 3/3 |
| ATORVASTATIN | 2 | 1/2 |
| ROSUVASTATIN | 2 | 1/2 |
| LOVASTATIN | 2 | unpowered |

Simvastatin is in **7 of 16**. The published interval was a Jeffreys binomial on
14 assumed-independent trials.

| estimate | naive binomial | cluster bootstrap (victim drug) |
|---|---|---|
| 12/14 powered = 86% | 62–97% | **50–100%** |
| 12/16 all = 75% | 51–91% | **30–96%** |

The naive interval is ~40% too narrow. The project already used a drug-level
cluster bootstrap for screen enrichment and labelled the pairwise interval
`_ANTICONSERVATIVE` in the canonical file — then applied the naive method to its
own headline. `statistics.cluster_proportion_ci` fixes it.

## 3. The validation basis was marked unverified in its own source file

All 16 rows of `config/positive_controls.csv` carried
`citation_status: to_verify`. The field was created with the intent to check
them and never filled in, while §2 interrogated the *evaluation* reference at
length.

`faers_ddi.verify_controls` runs the check against the same cached label corpus
the independent reference uses:

| status | pairs |
|---|---:|
| named, myotoxicity-relevant, **and contraindicated or dose-limited** | **14** |
| named and myotoxicity-relevant | 2 |
| not found | **0** |

**All 16 verify.** The two weaker ones (colchicine + cyclosporine, colchicine +
atorvastatin) are flagged rather than dropped — removing a control for scoring
poorly would be selection on the evaluation set. `citation_status` now records
the outcome; a test fails if `to_verify` reappears.

## 4. The confounder adjustment used a proxy touching 1.4% of the data

§4.7 excluded cases containing any of 30 hand-picked procedural/critical-care
drugs — **275,205 cases, 1.4%** — and reported band enrichment unchanged as
evidence that inpatient confounding does not drive the result. Perturbing 1.4%
of the data cannot exclude a confounder; the null was near-guaranteed. (The
phrasing also read as though 275,205 were the analysed set. It is the excluded
set.)

FAERS records the outcome directly. `outc_cod = 'HO'` covers **5,709,555**
reports and was already parsed but unused:

| stratum | cases | event rate | `plausible` | `known_pair` |
|---|---:|---:|---:|---:|
| hospitalised | 4,274,465 | 0.669% | **0.639** | 1.839 |
| not hospitalised | 15,999,951 | 0.083% | **0.825** | 1.885 |

An **8-fold** event-rate difference confirms hospitalisation is a real
confounder — which is exactly why the 1.4% proxy could not have detected one.
**The result reproduces in both strata.**

## 5. Band enrichment was unadjusted for the covariate §4.1 proves matters

The bands differ systematically on marginal strength — median log₂(RR_A × RR_B)
of 2.85 (`unsupported`), 4.16 (`plausible`), 5.32 (`known_pair`), 8.15
(positive controls) — and were compared adjusting only for co-report count.

| band | crude | stratified on marginal strength |
|---|---:|---|
| `plausible` | 0.767 | **0.749 (0.567–0.973)** — still below unity |
| `known_pair` | 2.015 | 1.835 (0.99–2.989) — **now includes unity** |

**The `plausible` deficit survives.** The `known_pair` 2× does not survive
intact, which is consistent with the circularity argument rather than a new
finding. The confound is small and non-monotone (quintile signal rates 3.7%,
7.2%, 6.6%, 5.2%, 6.7%), so the review's suspicion that it explained the 0.77
was **wrong** — and the measurement says so.

## 6. The anaphylaxis arm was invalid, not underpowered

Reported as "only 4 usable controls and uninformative", implying more data would
help. It would not: anaphylaxis is essentially single-agent, so the pairs are
co-exposures among independently causative drugs, with **no interaction present
for either null to detect**. Two entries were worse than weak —
`AMOXICILLIN + CLAVULANATE POTASSIUM` is a fixed-dose combination product, and
`CONTRAST MEDIA + IOHEXOL` pairs a class with a member of that class. Both
removed; the arm carries `design_valid: false`.

## 7. Smaller corrections

| finding | resolution |
|---|---|
| era filter applies the full-data threshold to third-sized bins, so it selects on co-report count as much as temporal persistence | documented in §4.6; the count comparison is unaffected because negatives get the identical filter |
| `275,205 cases, 1.4%` ambiguous | stated as the **excluded** set |
| no pre-specification statement | §4.3 names the pre-specified arm and its config key |
| case-report-sourced control undifferentiated | colchicine + atorvastatin flagged in §3.6 as `probable`/case-reports |

## 8. Checks that came back clean

Recorded so they are not re-litigated:

- **Only 1.0%** of the 17,375 screened pairs (172) are structurally unable to
  signal even if every co-report carried the event. "17,375 pairs tested" is
  honest; low-count pairs are not silently untestable.
- Artifact provenance, determinism, and the `.md`→`.tex` generation added in
  round 7 all hold.

## Status

**304 tests passing** (295 → 304; 9 added, all value-level, one mutation-tested
after the first version proved too weak to bite). New module
`src/faers_ddi/verify_controls.py`; new analyses in `audit.py`
(`band_enrichment_by_marginal_strength`, `inpatient_stratification`); new
`statistics.cluster_proportion_ci`.

Two claims in the previous version were weakened by this round — the headline
interval and the `known_pair` enrichment — and one previously unreported
specification arm now qualifies the central contrast. One review suspicion
(marginal strength explaining the 0.77) was **refuted** by the measurement it
prompted.
