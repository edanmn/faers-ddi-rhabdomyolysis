> **ARCHIVED, and superseded.** This document restructured the full manuscript
> for a general technical venue, before the work was split into two conference
> papers (`paper/paper_a.md`, `paper/paper_b.md`). It is retained for history
> only and is **not** maintained: it still states that the recovery comparison
> was made at "an essentially identical false-positive rate", a claim withdrawn
> in round 11 after the error rates were measured in the regime where recovery
> is measured (2.2% vs 9.3%, not 6.4% vs 6.7%). Do not cite or build from it.
> The maintained documents are `paper/manuscript.md` and the two conference
> papers.

# Additive and multiplicative nulls in drug–drug interaction surveillance: a negative result from the complete public history of FAERS

**Authors.** [TODO: author list, affiliations, corresponding author, ORCIDs]

## Abstract

**Background.** Most drug–drug interactions (DDIs) are identified after approval, and spontaneous reporting databases are the primary instrument for detecting them. The established disproportionality measure for DDI surveillance, Ω, tests the observed joint report count against a null in which the joint relative risk of two drugs is the product of their individual relative risks (Norén et al., 2008). Whether that multiplicative null is appropriate for an adverse event whose leading reported causes are the drugs under test has not, to our knowledge, been examined empirically.

**Methods.** We assembled the complete public history of the FDA Adverse Event Reporting System (FAERS) — 90 quarterly archives spanning 2004Q1–2026Q2, 328,476,258 rows — and reduced it to 20,293,421 distinct cases by six-stage deduplication, including a cross-era identifier bridge validated against a chance baseline. After excluding 19,005 cases listing more than 20 drugs, the analysis population comprised **20,274,416 cases carrying 41,889 myotoxicity events (0.207%)**. Drug entries were resolved to active ingredients (98.0% of 73,960,283 rows), and the event was defined by 23 hand-curated MedDRA Preferred Terms across 10 concepts, verified continuous across two MedDRA renamings. We validated against 16 positive controls, measured the false-positive rate against the full pool of 16,138 generated negative controls, and screened 17,375 drug pairs.

**Deviation from protocol.** Ω was pre-specified and failed, recovering 4/16 positive controls against **12/16** for an additive (excess-risk) null at the same threshold and an almost identical false-positive rate (6.4% versus 6.7%). We adopted the additive null after observing this. Ω becomes more negative as the marginal associations strengthen (*r* = −0.63, *n* = 16, 95% CI −0.86 to −0.19, *p* = 0.009), but so does $\Omega_{\mathrm{add}}$ (*r* = −0.65, *p* = 0.007), while the *observed* joint event rate is flat in marginal strength (*r* = +0.12, *p* = 0.67). Both nulls therefore over-predict for strongly associated pairs; what separates them is the magnitude of the expectation, not its gradient. Because the estimand was selected on the evaluation set, the binary selection was cross-validated: the additive null wins in 16/16 leave-one-out folds.

**Results.** Under the additive null the pipeline recovered 12/16 controls (12/14 adequately powered; 95% CI **50–100%** resampling the victim drug, since the 16 controls comprise five victim drugs with simvastatin in seven). All four tier × role-policy arms are reported: the additive advantage holds in three (+8, +8, +7 pairs) and is **null in the fourth** (6/16 versus 6/16). On a second control set selected by FDA labelling rather than by the authors (349 pairs), the direction replicates at both operating points — 55 versus 29 at $\Omega_{025}$ > 0, and 42 versus 15 at the calibrated threshold — but the recovery *rate* falls to 12–16%. The failure of Ω replicates on an independent drug-dominant event matched on event rate, torsade de pointes (**0/10** multiplicative versus 9/10 additive). The false-positive rate at $\Omega_{025}$ > 0 was 6.7% against a nominal 2.5%; the threshold was calibrated to $\Omega_{\mathrm{add},025}$ > +0.436 and validated out of sample at **5.03% (95% CI 4.37–5.74%)**. The screen returned 1,022 signals of which **874 (759–997)** are expected by chance.

**The screen shows no enrichment for genuine interactions once the annotation is made independent of the control set.** Pooled enrichment of known interaction pairs appears significant (2.02×, 95% CI 1.59–2.55), but every positive-control drug also appears on the list defining "known pair". Restricting to pairs containing no positive-control drug, enrichment is **1.12× (95% CI 0.69–1.81)**. An independent, endpoint-specific reference built from FDA product labelling reproduces this: 3.52× (2.71–4.56) over all pairs, falling to 1.23× (0.67–2.24) once control drugs are excluded and to 1.045 after stratification on co-report count. The band in which a novel interaction would appear shows enrichment **below** unity (0.77×, 95% CI 0.66–0.89), which survives adjustment for marginal strength (0.749, 0.567–0.973).

**Conclusions.** We report a validated pipeline, a characterised false-positive rate, and a negative discovery result. The robust methodological finding is that the multiplicative null is unusable for events in which the drugs of interest are the dominant reported cause, demonstrated on two such events. A secondary finding is that 0.09% of reports — those listing more than 20 drugs — contribute 34.7% of all drug pairs at a 4× enriched event rate and must be capped in any pairwise screen. The negative discovery result is bounded by the reference rather than by the method: the screen's highest-ranked pair by event rate, atorvastatin + fusidic acid (155 events in 185 co-reports), is a contraindicated interaction that no available reference contained.

**Keywords.** pharmacovigilance; drug–drug interactions; disproportionality analysis; FAERS; rhabdomyolysis; negative results; reproducibility

---

## 1. Introduction

Drug–drug interactions are largely discovered after approval. Pre-marketing trials cannot test the combinatorial space of co-prescriptions, so the burden of detection falls on post-marketing surveillance of spontaneous adverse event reports. In the United States, the FDA Adverse Event Reporting System (FAERS) is the largest public instrument available for this purpose, and disproportionality analysis over its contents is the standard computational approach.

Methods for the single drug–event case are mature. Extending them to drug *pairs* requires a decision that the single-drug case does not force: what the joint report count should be compared against when neither drug is inert. The dominant answer in pharmacovigilance is the measure Ω (Norén et al., 2008), which compares the observed triple count against a log-linear model containing all pairwise associations and no three-way term. The implicit null is multiplicative — two drugs that each raise reporting of an event should, absent interaction, raise it jointly by the product of their individual relative risks.

That null carries a hidden assumption. It is unremarkable when each drug's marginal association with the event is weak, but the best-characterised interaction classes are precisely those in which both drugs are leading reported causes of the outcome. Statin–fibrate and statin–macrolide combinations and rhabdomyolysis are the canonical example: the drugs under test are among the dominant causes of the event being tested. Under a multiplicative null, the expected joint reporting rate for such a pair can approach the co-report count itself, leaving almost no room for an observed excess. Whether Ω remains usable in that regime is an empirical question, and to our knowledge it has not been asked.

We set out to answer it while building something independently useful: a reproducible pipeline over the complete public FAERS history, validated against known interactions, with a measured false-positive rate, applied to a screen for undocumented interactions. The first three aims succeeded. The fourth returned a negative result, which we report as a finding rather than suppress.

### 1.1 Contributions

1. **An empirical demonstration that the multiplicative null fails when the drugs under study are the dominant reported causes of the outcome.** Ω recovers 4 of 16 established interactions where an additive null recovers 12, at a matched false-positive rate (6.4% versus 6.7%). The failure replicates on a second, independently constructed drug-dominant event.

2. **A decomposition of the mechanism.** The observed joint event rate is flat in marginal strength (*r* = +0.12), while both nulls predict it to rise steeply (*r* ≈ +0.94). Joint risk saturates, and both models miss it; the multiplicative null fails harder only because its expectation is larger at every point. We report this correction explicitly because an earlier reading of our own data attributed the effect to multiplicativity alone.

3. **Quantification of polypharmacy leverage.** 19,005 cases (0.09% of the database) contribute 34.7% of all drug pairs at a 4× enriched event rate. This is invisible from positive controls and appears only from the false-positive side.

4. **A negative discovery result, robust across five annotation schemes**, together with the demonstration that an evaluation whose annotation is authored by the same investigators as the control set will show enrichment regardless of whether the method works.

5. **A fully reproducible artefact.** Every reported number is generated by a single deterministic pipeline into one canonical file and asserted against the manuscript text by an automated test suite.

### 1.2 Roadmap

Section 2 situates the work in the disproportionality and interaction-analysis literature. Section 3 states the problem formally and identifies the gap. Section 4 describes the methodology, from archive acquisition to the two estimands. Section 5 gives the system architecture and data flow. Section 6 specifies the evaluation design, including the full space of design choices. Section 7 presents results. Sections 8–10 discuss interpretation, limitations and required future work, and Section 11 concludes.

---

## 2. Background and related work

> **Verification status.** Every citation in this section has been verified against an indexed source; full bibliographic detail appears in the References. One exception is recorded explicitly. The Ω definition used here (α = 0.5, threshold $\Omega_{025}$ > 0) is corroborated by two independent *secondary* sources — a peer-reviewed review of DDI signal-detection methods stating that "α = 0.5 was set to provide sufficient shrinkage for avoiding disproportional highlighting based on rare reports", and Uppsala Monitoring Centre operational documentation listing "Interaction disproportionality measure Omega 025 > 0" — but the primary paper is paywalled and has not been read by the authors. A further work on FAERS duplication practice was cited in an earlier draft and has been removed rather than cited from memory, its bibliographic detail being unconfirmable.

### 2.1 Disproportionality for single drug–event pairs

The standard measures are the proportional reporting ratio (Evans, Waller and Davis, 2001), the Bayesian confidence propagation neural network and its information component (Bate et al., 1998), and the multi-item gamma-Poisson shrinker (DuMouchel, 1999). All share the shrinkage logic adopted here: a lower credibility bound withholds a signal at low counts, so that a single co-report cannot generate an alert.

### 2.2 Extension to drug pairs

Thakrar, Grundschober and Doessegger (2007) set out both additive and multiplicative models for interaction signals in spontaneous reports and observed that the two answer different questions. Norén, Sundberg, Bate and Edwards (2008) introduced Ω, the measure this study pre-specified, which compares the observed triple count against a log-linear model with all pairwise associations and no three-way term. Our contribution is not a new estimator but an empirical demonstration of where Ω's null breaks down, together with identification of the condition under which it does.

### 2.3 Additive versus multiplicative interaction

The argument that departure from *additivity* is the criterion for interaction of public-health relevance, while departure from multiplicativity answers a different question, is long-standing in epidemiology. Rothman (1976) established departure from additivity as the test for synergism under the sufficient-cause framework. VanderWeele and Knol (2014) give the modern treatment; their recommendation that both scales be reported rather than one chosen is the practice adopted here. We arrived at this argument empirically and then found it already established, and we claim novelty only for the demonstration in the spontaneous-reporting setting.

### 2.4 FAERS curation

Banda et al. (2016) published AEOLUS, a curated and standardised FAERS resource covering January 2004 to June 2015 and retaining 4,928,413 unique cases. Over the identical window our pipeline retains 5,337,888, a difference of 8% in the direction expected: AEOLUS applies an additional pass deduplicating on event date, age, sex and country alone, regardless of case number, which merges distinct patients sharing those fields.

The DiAna dictionary (Fusaroli et al., 2024) provides a curated FAERS drug-name-to-ingredient mapping. We did not use it, having found that FDA's own `prod_ai` field applied backwards suffices. The two agree closely on coverage: DiAna reports standardising 98.94% of 74,143,411 drug entries; this pipeline resolves 98.0% of 73,960,283. That near-agreement, reached by independent means, is the closest available external check on our ingredient resolution.

### 2.5 Reference sets for interaction evaluation

TWOSIDES (Tatonetti et al., 2012) is derived from FAERS itself and is therefore unsuitable as an independent reference here. DrugBank is licensed and was not available.

The ONC high-priority DDI list (Phansalkar et al., 2012) *is* available — a 15-row table in an open-access paper — and an earlier draft of this work described it as unavailable without checking. We retrieved and examined it. It is not usable as a reference for this study, for a reason specific to its construction rather than to access: the list is expressed as *drug-class* pairs (for example, "HMG Co-A reductase inhibitors ↔ CYP3A4 inhibitors" and "QT prolonging agents ↔ QT prolonging agents") rather than ingredient pairs, so applying it requires an ingredient-to-class mapping that would itself have to be author-written — reintroducing the circularity this study is trying to escape. Only one of the 15 entries concerns myotoxicity, and the source explicitly excluded the gemfibrozil–statin interaction, one of our positive controls, on the grounds that clinical benefit of co-prescribing outweighs risk.

A curated, ingredient-level, severity-graded DDI compendium remains unavailable, and that absence is the single largest limitation of this evaluation (Section 9).

---

## 3. Problem statement

Let $A$ and $B$ denote two drugs and $Z$ an adverse event. In a spontaneous reporting database, each case is a set of reported drugs and a set of reported event terms. Collapsing to the three binary indicators of interest yields a $2 \times 2 \times 2$ contingency table whose eight cells are recoverable from the triple count $n_{111}$, the six marginals and the total.

An interaction signal is declared when $n_{111}$ exceeds what would be expected in the absence of interaction. The methodological question is what "expected" means.

**The multiplicative null.** Ω compares $n_{111}$ against the fit $E^{\mathrm{mult}}_{111}$ of the log-linear model $[AB][AZ][BZ]$ — all pairwise associations, no three-way term:

$$\Omega = \log_2\!\left(\frac{n_{111} + \alpha}{E^{\mathrm{mult}}_{111} + \alpha}\right)$$

with a gamma-Poisson posterior supplying the lower credibility bound $\Omega_{025}$.

**The additive null.** The excess-risk alternative expects the joint risk to be the sum of the two individual excess risks over background:

$$E^{\mathrm{add}}_{111} = n_{11\cdot} \cdot \min\!\Big(\max\big(P(Z \mid A) + P(Z \mid B) - P(Z),\; P(Z \mid A),\; P(Z \mid B)\big),\; 1\Big)$$

with identical shrinkage, so that the two estimands differ *only* in the null.

**The gap.** When $P(Z \mid A)$ and $P(Z \mid B)$ are both small, the two nulls nearly coincide and the choice is immaterial. When both are large — the regime occupied by the best-characterised interaction classes — they diverge sharply, and the multiplicative expectation can approach the co-report count itself. No published work has examined empirically whether Ω remains usable in that regime, yet that regime is precisely where a DDI method is most likely to be validated.

**The study question.** Does the multiplicative null retain discriminative power for an adverse event whose leading reported causes are the drugs being tested, and if not, what is the mechanism?

We instantiate the question on rhabdomyolysis and related myotoxicity. The choice is deliberate: the event is severe, has well-characterised drug causes, and offers an unusually strong positive-control set in the statin interactions. That same property — the controls being the dominant causes of the outcome — creates the methodological problem that constitutes this paper's main contribution.

---

## 4. Methodology

### 4.1 Data acquisition

All 90 quarterly archives (3.55 GB compressed, 20.04 GB uncompressed) were downloaded with a manifest recording a SHA-256 hash per archive, because FDA silently re-issues quarterly files.

The archives are not a single format. An audit of every column header in every table across all 90 quarters found 21 schema changepoints, three of which would have corrupted results without raising an error:

- A UTF-8 byte-order mark on the first column name of `DRUG12Q4.txt` and nowhere else, causing every drug-to-demographics join for that quarter to match zero rows.
- 2012Q4 spells three columns differently from both neighbouring quarters (`outc_code`/`outc_cod`, `lot_nbr`/`lot_num`, `i_f_code`/`i_f_cod`).
- `DEMO18Q1_new.txt`, a non-standard filename that any pattern anchored on `Q<digit>.TXT` classifies as documentation, silently dropping a quarter of demographics.

Deleted-case lists ship for 2019Q1–2026Q2 under five naming conventions, including `Deleted/DELETEnnQn.txt` from 2021Q4, which contains no occurrence of the string "deleted". A cumulative list in 2019Q1 covers everything prior.

### 4.2 Parsing and validation

Every data line in every FAERS table ends with a trailing delimiter that its header does not declare. Given more fields than names, common CSV readers promote the surplus leading column to the index and shift every column left by one, silently. In the `DRUG` table this moves `drug_seq` into `primaryid`; both are integers, every type check passes, and the pipeline completes with every drug attributed to the wrong report.

Parsing is therefore validated by referential integrity rather than by type: **0 orphan rows across all 328,476,258 rows**.

### 4.3 Deduplication

Six stages reduce 24,812,425 raw demographics rows to 20,293,421 distinct cases. The first two rows of Table 1 are per-era rather than cumulative: LAERS and FAERS use disjoint identifier spaces and are deduplicated separately before being bridged, so their `remaining` values are counts within their own era (4,276,201 and 20,536,224 raw rows respectively), summing to 20,775,025 entering the bridge. From the cross-era bridge onward the counts are cumulative. Seven LAERS rows carry a NULL `case_id` and are dropped before stage 1, so the two era totals sum to 24,812,418 rather than the 24,812,425 raw.

**Table 1.** Deduplication stages.

| Stage | Remaining | Removed |
|---|---:|---:|
| Raw DEMO rows (all eras) | 24,812,425 | — |
| Within-LAERS, per era (highest `isr` per case) | 3,091,161 | 1,185,033 |
| Within-FAERS, per era (highest `caseversion`) | 17,683,864 | 2,852,360 |
| Cross-era bridge | 20,692,683 | 82,342 |
| FDA-deleted cases | 20,588,497 | 104,186 |
| Near-duplicates | 20,294,190 | 294,307 |
| One case per report | 20,293,421 | 769 |

The cross-era bridge was validated rather than assumed. 82,342 identifiers appear in both numbering systems; event date agreed on 33.3% of them against 0.0% at a chance baseline, and date, sex and age jointly agreed on 26.0% against 0.0%.

Near-duplicate eligibility requires event date, age, drug set and PT set, rather than a count of populated fields. An initial "any 4 of 6" rule removed 14.5% of all cases with a largest collision group of 9,270, driven by sparse records agreeing on missingness.

### 4.4 Ingredient resolution

The `prod_ai` (active ingredient) field exists only from 2014Q3 onward, with 97.8% coverage after that boundary and 0% before. We used the modern era as an FDA-curated `drugname → ingredient` lookup applied backwards, resolving 90.1% of LAERS rows; a relaxed pass stripping dose and packaging detail added approximately six points, for **98.0% of 73,960,283 rows**. Salt and hydrate forms are stripped, while element-headed compounds such as calcium carbonate and ferrous sulfate are protected from that stripping.

Coverage is not accuracy. No manual validation of resolution correctness against external ground truth was performed; a bound is given in Section 7.9 and the limitation is stated in Section 9.

### 4.5 Event definition

The event comprises 23 MedDRA Preferred Terms across 10 concepts, curated against the 25,047 PT strings actually present in the data rather than against a current MedDRA release. Two renamings occur within the concept area, both clean instantaneous switches: `BLOOD CREATINE PHOSPHOKINASE INCREASED` → `CREATINE KINASE INCREASED` at 2026Q2 (part of a vocabulary-wide event in which 1,907 PT strings make their last appearance in 2026Q1), and `IMMUNE-MEDIATED NECROTISING MYOPATHY` → `IMMUNE-MEDIATED MYOSITIS` at 2019Q4. The latter is *not* meaning-preserving — the successor carries roughly five times the per-quarter volume — so both terms are held out of the primary tier.

### 4.6 The positive control set and its verification

The control set comprises 16 pairs assembled from FDA product labelling: seven simvastatin pairs, two lovastatin, two atorvastatin, two rosuvastatin and three colchicine, against eight perpetrator drugs.

Every pair was checked against label text rather than asserted. An earlier version of this work carried `citation_status: to_verify` on all sixteen rows of the control file — a field created with the intention of checking them, never filled in. The check asks whether either drug's label names the other, whether a myotoxicity term appears within 600 characters of that mention, and whether the mention sits in contraindication or dose-limiting language.

**Table 2.** Verification of the 16 positive controls against cached FDA label text.

| Status | Pairs |
|---|---:|
| Named, myotoxicity-relevant, **and** contraindicated or dose-limited | 14 |
| Named and myotoxicity-relevant | 2 |
| Named only, or not found | 0 |

All 16 are confirmed. Two — colchicine + cyclosporine and colchicine + atorvastatin — carry a myotoxicity warning without explicit dose restriction, and colchicine + atorvastatin is additionally the one pair sourced from case reports rather than labelling and graded *probable* rather than *established*. It is retained and flagged rather than dropped, since removing a control because it scored poorly would itself be selection on the evaluation set.

Critically, **the 16 are not 16 independent trials**: they comprise five victim drugs, and simvastatin appears in seven of them. Recovery intervals are therefore computed by resampling the victim drug (Section 7.3) rather than by a binomial on the pair count.

### 4.7 Independent interaction reference

Because the investigators wrote both the positive control set and the list defining "known pair", a second annotation was constructed that they did not author. For each screened ingredient we retrieved the most recent FDA product label via openFDA and recorded which other screened ingredients are named in its DRUG INTERACTIONS, CONTRAINDICATIONS or WARNINGS AND PRECAUTIONS sections. A pair is `label_documented` when either drug's label names the other. Labels are cached, fixing the reference against future label revisions.

This annotation is independent of the authors but **not** of FAERS. Labelling is informed by post-marketing surveillance, so it cannot establish that a signal was found independently of the data; it establishes only that the annotation was not written by us, which is the circularity at issue. Labels also warn by class ("strong CYP3A4 inhibitors") as often as by name, so the reference is under-sensitive, biasing measured enrichment downward.

That is the conservative direction for a claim that enrichment *exists*, and the **anti**-conservative direction for this paper's actual claim, which is that it does not. Attenuating a ratio toward unity moves it toward our own conclusion, so under-sensitivity cannot be offered as a safeguard here. Section 7.5 therefore reports the analysis restricted to pairs whose two labels both exist, removing the portion of the insensitivity that is structural rather than editorial.

### 4.8 Statistical measures

**Ω (multiplicative null).** Fitted exactly by iterative proportional fitting rather than by the published closed-form approximation, which we measured at up to 237% error once pairwise log-odds reach 2 — enough to produce Ω < −1 on tables with no synergy.

**$\Omega_{\mathrm{add}}$ (additive null), primary.** Expected joint risk $P(Z \mid A) + P(Z \mid B) - P(Z)$, floored at $\max(P(Z \mid A), P(Z \mid B))$, with identical gamma-posterior shrinkage.

**Shrinkage constant.** α = 0.5 is conventional and could not be verified against the primary source. It is therefore varied across a 20-fold range as a sensitivity analysis (Section 7.8) rather than assumed.

**Intervals and tests.** All proportions carry Jeffreys 95% intervals; ratios carry log-scale intervals. Binomial tests are **not** used for inference: with 200 drugs, each drug sits in 199 pairs, so pair outcomes are strongly dependent. Significance is assessed by a permutation test that holds the pair graph and the observed signal pattern fixed while randomising which drugs are annotated as implicated (10,000 permutations). Interval estimates for quantities aggregated over pairs use a cluster bootstrap resampling *drugs*.

**Design.** The unit of analysis is the case. The denominator is the deduplicated set less the polypharmacy exclusion, retaining cases with no resolved drug as background. Drug roles are primary and secondary suspect plus interacting.

---

## 5. System architecture

The pipeline is a six-stage directed acyclic flow from remote archives to a single canonical results file. Each stage writes a durable artefact, so any stage can be re-run independently, and every reported number derives from one file.

**Figure 1.** *System architecture and data flow.* [TODO: architecture diagram; the flow is described below and is not currently rendered as a figure]

1. **Acquire.** 90 quarterly ZIP archives with a SHA-256 manifest.
2. **Audit.** Every column header in every table in every quarter, producing a schema map that drives parsing. This stage is authoritative where it disagrees with the configured expectation.
3. **Parse.** ASCII to Parquet under a schema adapter, validated by referential integrity.
4. **Reduce.** Deduplication, ingredient resolution, event flagging, producing the case-level analysis tables in DuckDB.
5. **Analyse.** Tier A (positive controls), Tier B (negative controls and threshold calibration), Tier C (screen), plus sensitivity, generalisation and audit stages.
6. **Report.** Figures and tables generated from the canonical file; the manuscript asserted against it by automated tests.

Order matters at one point: Tier B calibrates the threshold that Tier C applies, so the threshold is computed and persisted before the screen runs.

**Computational environment.** A single workstation, macOS on Apple silicon; Python 3.14.6, DuckDB 1.5.5, pandas 3.0.5, PyArrow 25.0.0, NumPy 2.5.1, SciPy 1.18.0, matplotlib, with exact pinned versions in `requirements.txt`. Downloading the 90 archives takes approximately 30 minutes on a domestic connection; parsing 328M rows to Parquet takes approximately 3 minutes at 4 processes; the full analysis takes approximately 12 minutes. Peak memory is bounded by a 10 GB DuckDB limit. No GPU is used. Total on-disk footprint is 157 GB, of which 3.55 GB is the irreducible source archive set.

**Reproducibility.** The pipeline is deterministic: two full runs produce byte-identical output. Every figure quoted in the Abstract and Results is generated into `results/canonical_numbers.json` by a single deterministic run and asserted against this text by `tests/test_canonical_numbers.py`; pipeline statistics quoted in Methods are persisted under `audit.provenance` in the same file and asserted alongside them. Figures drawn from cited work are attributed and not regenerated.

---

## 6. Experimental setup

### 6.1 Evaluation tiers

**Tier A — positive controls.** The 16 verified pairs of Section 4.6, scored under both nulls at the same threshold ($\Omega_{025}$ > 0). A pair with fewer than 50 co-reports is treated as inadequately powered and reported separately.

**Tier B — negative controls and calibration.** Drug pairs are generated by excluding known positive pairs and any pair in which *both* drugs appear on a myotoxicity-implicated list, then frequency-matching to the positive controls' co-report distribution. The pool is stratified into an *easy* stratum (neither drug individually associated with the event, RR < 2) and a *hard* stratum (at least one drug associated, RR ≥ 2, but no known interaction). The hard stratum is the realistic case. The entire eligible pool of 16,138 pairs is used rather than a sample: sampling 2,000 left the calibrated threshold at the mercy of the draw, moving it by more than a factor of four across legitimate runs.

**Tier C — the screen.** The top 200 ingredients by co-reporting with the event, yielding 17,375 pairs with at least 3 co-reports. Pairs are annotated into four bands defined in advance:

- `positive_control` — one of the 16;
- `known_pair` — both drugs on the author-curated implicated list;
- `plausible` — one implicated drug plus an unimplicated partner, designated in advance as where a novel interaction would appear;
- `unsupported` — neither drug implicated.

### 6.2 The specification grid

Two binary design choices were available: the **event tier** (`core`, specific; `broad`, inclusive of the two non-meaning-preserving MedDRA concepts) and the **drug role policy** (`primary`, suspect roles only; `sensitivity`, wider, admitting concomitant drugs with no suspected causal role). The combination `core`/`primary` is pre-specified in configuration and is the arm reported throughout. All four arms were computed and all four are reported (Section 7.3).

### 6.3 Pre-specification and post-hoc analyses

Two claims were specified before any result was seen: the comparison of nulls on positive controls (Section 7.1), and the polypharmacy leverage analysis (Section 7.4). Every analysis in Section 7.9 is post-hoc, added in response to a specific objection raised during internal review; several changed the paper's conclusions. Counting all review rounds, this work reports the outcome of roughly fifty distinct analyses. **No multiplicity correction has been applied across them, and the intervals in Section 7.9 are therefore nominal.**

---

## 7. Results

### 7.1 Ω fails, and both nulls mispredict in the same direction

Ω recovered **4/16** positive controls at $\Omega_{025}$ > 0, against **12/16** for the additive null at the same threshold and an almost identical false-positive rate (6.4% versus 6.7%, Section 7.3). That matched comparison is the paper's primary evidence and does not depend on anything else in this section.

Simvastatin + amiodarone, named in advance as the pair that must work, scored Ω = **−0.385** ($\Omega_{025}$ = −0.630): 145 events among 649 co-reports against 189.5 expected under the multiplicative null.

The drugs of interest are the dominant reported causes of the outcome, with marginal relative risks of 3–19 against a 0.207% background, so the multiplicative null predicts very high joint rates.

**Table 3.** Observed and expected joint event rates for three positive controls.

| Pair | Observed | Multiplicative | Additive |
|---|---:|---:|---:|
| Gemfibrozil + simvastatin | 55.1% | 72.9% | 27.9% |
| Atorvastatin + gemfibrozil | 14.5% | 71.8% | 22.9% |
| Amiodarone + simvastatin | 15.1% | 25.1% | 10.9% |

Fifty-five percent of gemfibrozil + simvastatin co-reports carry rhabdomyolysis, and the pair still scores as protective.

**Figure 2.** *Null comparison on positive controls* (`figure1_null_comparison.png`). Observed proportion of co-reports carrying myotoxicity (red circles) against the proportion expected under the multiplicative null (bars) and the additive null (blue squares), for the 14 positive controls with ≥ 50 co-reports, ordered by co-report count. The multiplicative null expects more events than are observed for most established interactions, which is why Ω scores them as protective.

**The marginal-strength gradient is real, but it is not diagnostic of the multiplicative null.** Ω correlates with $\log_2(RR_A \times RR_B)$ at *r* = −0.63 (*n* = 16, 95% CI −0.86 to −0.19, *p* = 0.009). Because $\Omega = \log_2((O + \alpha)/(E + \alpha))$ and $E$ is an increasing function of the same marginals that form the x-axis, part of any such correlation is induced by the construction — regressing a ratio on a proxy for its own denominator. We measured how much: drawing the triple count from each null's own expectation and recomputing the statistic 10,000 times gives an induced correlation centred on zero (median +0.03, 95% interval −0.23 to +0.26 for Ω). The observed −0.63 lies outside that interval, so the gradient is **not** an artefact of the estimator.

It is, however, **not specific to the multiplicative null**. The additive null — this paper's remedy — shows the same gradient, slightly stronger.

**Table 4.** Correlation of each quantity with $\log_2(RR_A \times RR_B)$ across the 16 positive controls.

| Quantity | *r* (95% CI) | *p* |
|---|---|---:|
| **Observed event rate among co-reports** | **+0.12 (−0.40 to +0.58)** | **0.67** |
| Expected rate, multiplicative null | +0.94 | — |
| Expected rate, additive null | +0.94 | — |
| Ω (multiplicative) | −0.63 (−0.86 to −0.19) | 0.009 |
| **$\Omega_{\mathrm{add}}$ (additive)** | **−0.65 (−0.86 to −0.22)** | **0.007** |

**The observed joint event rate does not rise with marginal strength at all.** Both nulls predict that it should, and steeply. Both are therefore wrong in the same direction, and the gradient in Ω reflects a property of the data — joint risk saturates as the individual risks grow — rather than a defect peculiar to multiplicativity. It will appear in any statistic that divides an observed rate by a marginal-driven expectation.

> An earlier version of this manuscript reported this correlation for Ω alone and read it as evidence that the multiplicative null is uniquely broken. That reading was incorrect. The correlation survives the artefact check, but it does not separate the two nulls, and it is reported here for both.

What *does* separate them is **level, not slope**: the multiplicative expectation is far larger at every point (72.9% versus 27.9% for gemfibrozil + simvastatin), so the same saturation drives Ω below zero while leaving $\Omega_{\mathrm{add}}$ above it. Departure from additivity is the standard criterion for clinically meaningful interaction (Rothman, 1976; VanderWeele and Knol, 2014); departure from multiplicativity is a stricter and different question, and on a drug-dominant event it is a question almost nothing passes.

**Figure 3.** *Ω against marginal strength* (`figure2_omega_correlation.png`). Ω for each positive control against $\log_2(RR_A \times RR_B)$, the combined strength of the two drugs' individual associations with the event. The line is ordinary least squares.

### 7.2 The estimand switch does not inflate sensitivity

The additive null was adopted because it recovered more controls, and control recovery is then reported as validation — selection on the evaluation set. The selection decision is binary and was therefore cross-validated: the additive null wins in **16/16 leave-one-out folds**, and held-out recovery equals in-sample recovery (12/16, optimism 0.000).

**The optimism figure carries less information than it appears to.** When the same null wins in every fold, the held-out score for each control is by definition its in-sample score, so optimism is *identically* zero and cannot take another value. It is a consequence of the selection being stable, not independent evidence for it, and an earlier version of this manuscript presented it in the abstract as though it were a measurement. What leave-one-out does establish is the stability itself: the choice between the two nulls does not depend on any single control.

It does not address the deeper issue that these 16 controls were chosen by the investigators. That is addressed in Section 7.10 with a control set drawn by FDA labelling, and that is where the sensitivity estimate degrades.

### 7.3 Recovery, calibration and the specification grid

Under the additive null, **12/16 controls signal (12/14 powered)**. Six of seven simvastatin pairs and three of three colchicine pairs recover; both lovastatin pairs have co-report counts of 19 and 1 and are unmeasurable.

**The interval must respect the control set's clustering.** The 16 controls comprise five victim drugs, with simvastatin in seven of them (Section 4.6), so they are not 16 independent trials.

**Table 5.** Recovery intervals under two dependence assumptions.

| Estimate | Naive binomial | **Cluster bootstrap (victim drug)** |
|---|---|---|
| 12/14 powered = 86% | 62–97% | **50–100%** |
| 12/16 all = 75% | 51–91% | **30–96%** |

The naive interval is roughly 40% too narrow. We report the clustered one. This is the same correction already applied to screen enrichment, where pairs share drugs; applying it there and not here was two standards for one dependence structure.

**The full specification grid.** All four tier × role-policy arms were computed, and an earlier version of this manuscript reported the pre-specified arm without disclosing that the others existed.

**Table 6.** Positive-control recovery across all four design arms.

| Tier | Role policy | Additive | Multiplicative | Additive advantage |
|---|---|---:|---:|---:|
| **core** | **primary** *(pre-specified)* | **12/16** | **4/16** | **+8** |
| core | sensitivity | 12/16 | 4/16 | +8 |
| broad | primary | 11/16 | 4/16 | +7 |
| **broad** | **sensitivity** | **6/16** | **6/16** | **0** |

**Under the widest event definition combined with the widest role policy, the additive null's advantage disappears entirely.** The contrast holds in three of four arms and is null in the fourth. Any reader weighing the headline result should weigh that: the result is robust to either widening alone, but not to both together. The broad tier deliberately includes the two MedDRA concepts held out for not being meaning-preserving (Section 4.5), and the sensitivity policy admits concomitant drugs with no suspected causal role, so the fourth arm is the least specific analysis available — but it is not unreasonable, and it is on the record.

**False-positive rate.** Against the full pool of 16,138 negative controls, the false-positive rate at $\Omega_{025}$ > 0 was **6.7%** (easy stratum 4.0%, hard stratum 8.5%) against a nominal 2.5%. The multiplicative null's rate at the same threshold is **6.4%**, so the recovery comparison in Section 7.1 is made at an essentially identical false-positive rate rather than by moving the operating point.

**Out-of-sample calibration.** A quantile of the pool whose false-positive rate is then reported returns the target by construction, so a nominal 5% would be definitional rather than measured. Splitting the pool 500 times — calibrating on one half, measuring on the other — gives a held-out threshold of **+0.429** and a held-out false-positive rate of **5.03% (95% CI 4.37–5.74%)** against the in-sample **+0.436**. The in-sample calibration is therefore very nearly unbiased, but the rate is now a measurement. Downstream, the pairs expected by chance among the 17,375 screened become **874 (95% CI 759–997)**.

Sensitivity is quoted at $\Omega_{025}$ > 0 throughout, not at the calibrated threshold; at +0.436 recovery is 11/15 of the controls that enter the screen. The two operating points are reported separately and should not be combined.

### 7.4 Polypharmacy leverage

The strongest apparent false positive was alirocumab + ipratropium: 88 co-reports, 88 events. Those 88 cases share 5 distinct event dates and 1 distinct age, each listing 31–40 drugs — residual near-duplicates that the exact-set fingerprint could not merge.

A case listing 40 drugs contributes 780 pairs. **19,005 cases (0.09% of the database) contribute 34.7% of all drug pairs at a 4× enriched event rate.** Capping at 20 drugs per case improved sensitivity (11 → 12/16) and the false-positive rate (6.9% → 6.7%) simultaneously, and the multiplicative null improves from 2/16 to 4/16, so the headline contrast in Section 7.1 is *understated* by the cap rather than produced by it. Nothing in the positive controls could have revealed the leverage problem; it is visible only from the false-positive side. The cap *value*, however, was chosen by looking at control recovery, and Section 7.9 reports the full sweep.

**Figure 4.** *Polypharmacy leverage* (`figure5_polypharmacy_leverage.png`). Percentage of all drug pairs contributed by cases in each drugs-per-case band (bars, left axis) and the myotoxicity event rate within that band (line, right axis). The dotted line marks the adopted cap at 20 drugs.

### 7.5 The screen shows no demonstrable enrichment for genuine interactions

Of 17,375 pairs tested, **1,022** exceeded threshold, against **874 (95% CI 759–997)** expected by chance at the held-out false-positive rate.

**Multiplicity.** $\Omega_{\mathrm{add},025}$ is a shrinkage bound, not a *p*-value, and carries no family-wise or false-discovery guarantee; the calibrated threshold stands in for one. As an independent check, a one-sided Poisson test of each triple count against its additive expectation, with Benjamini–Hochberg control at *q* = 0.05, yields **1,147 discoveries**, and every one of the 1,022 shrinkage signals is among them. The shrinkage threshold is the more conservative of the two rules, so no conclusion below depends on the absence of a formal correction.

**Table 7.** Signal rate by pre-specified support band.

| Band | Signalled | Rate | Enrichment (95% CI) |
|---|---|---:|---|
| Positive control | 11/15 | 73.3% | 12.16 (8.89–16.63) |
| Known pair | 66/543 | 12.2% | 2.02 (1.59–2.55) |
| **Plausible** | 228/4,930 | 4.6% | **0.77 (0.66–0.89)** |
| Unsupported | 717/11,887 | 6.0% | 1.00 (0.90–1.11) |

A drug-level permutation test gives pooled enrichment 2.29× (*p* = 0.0012) under the **author-curated** annotation, so that pooled effect is not an artefact of pair dependence alone. **Under the independent FDA-labelling annotation the same test is not significant** (2.80×, *p* = 0.14). The distinction matters, and an earlier version reported only the first: dependence-aware significance is present for the annotation the investigators wrote and absent for the one they did not.

**The annotation is not independent of the control set.** All 12 positive-control drugs are among the 64 drugs defining "known pair", and that list was written by the same investigators. Restricting to pairs containing no positive-control drug reduces enrichment to **1.12× (95% CI 0.69–1.81)** against the unsupported reference of 1.00 — indistinguishable from unity. The pooled 2.02× is essentially entirely attributable to pairs containing a drug the investigators had already nominated.

**Confirmation against an independent reference.** The FDA-labelling annotation yields 6,106 pairs in which one drug's label names the other, capturing 16/16 positive controls. Two corrections were required before it could be used.

First, a label documents that two drugs interact, not that the interaction causes *this* event: 82% of name-matched pairs are documented for an unrelated endpoint, and omeprazole + warfarin — a real CYP2C19 interaction affecting INR — was being counted as a hit in a myotoxicity screen. The endpoint-specific reference additionally requires a myotoxicity term within 600 characters of the partner drug's name, giving 709 pairs that still capture 16/16 positive controls.

Second, documented pairs are co-reported about three times more often than undocumented ones (median co-report count 202 versus 69, Mann–Whitney *p* = 2 × 10⁻⁷⁵), and co-report count drives statistical power directly, so the crude comparison confounds "documented" with "well powered". Results are therefore also reported stratified on co-report count decile by the Mantel–Haenszel method.

**Table 8.** Enrichment under every annotation scheme.

| Annotation | Scope | Signalled | Enrichment (95% CI) | Stratified |
|---|---|---|---|---|
| Author-curated | Pooled | 66/543 | 2.02 (1.59–2.55) | — |
| Author-curated | No control drug | 16/237 | **1.12 (0.69–1.81)** | — |
| FDA labelling, any endpoint | Pooled | 110/1,339 | 1.44 (1.19–1.75) | 1.24 |
| FDA labelling, any endpoint | No control drug | 57/1,069 | 0.92 (0.71–1.20) | 0.75 |
| **FDA labelling, myotoxicity** | Pooled | 48/240 | 3.52 (2.71–4.56) | 3.08 |
| **FDA labelling, myotoxicity** | **No control drug** | 10/142 | **1.23 (0.67–2.24)** | **1.045** |

**Figure 5.** *Band enrichment under two annotations* (`figure3_band_enrichment.png`). Signal enrichment relative to unsupported pairs, log scale, with 95% intervals, under the author-curated annotation and the independent FDA-labelling annotation. Points left of each divider are pooled; points right of it exclude pairs containing a positive-control drug.

**The reference is structurally blind to part of the screen.** 138 of the 800 screened ingredients (**17.2%**) have no FDA label in openFDA at all, so no pair containing one can ever be `label_documented`: **1,712 of 17,375 pairs (9.8%)** are undocumentable by construction and fall into the denominator. The blindness is not random — it is concentrated on drugs without a current US marketing authorisation, among them **cerivastatin, bezafibrate, ciprofibrate** and **telithromycin**, members of the classes that define this endpoint, plus **fusidic acid** (Section 7.7). Restricting to non-control pairs where both labels exist, so that "undocumented" means the label is silent rather than absent, gives enrichment **1.24 (0.68–2.26)** crude and **1.067 (0.292–1.972)** stratified, on 142 documented pairs. **The negative result is unchanged by the correction**, but the reference's coverage is a property of US marketing status rather than of pharmacology and should be read as such.

**Power.** This comparison rests on 142 documented non-control pairs. At the observed baseline signal rate it has 83% power to detect a true enrichment of 2.5×, but only 57% at 2.0× and 23% at 1.5×. The correct reading is therefore "no enrichment above roughly 2.24×" — the upper confidence bound — rather than "no enrichment". A real but modest enrichment would very likely be missed.

**The plausible band.** The band designated in advance as where a novel interaction would appear has enrichment **0.77 (0.66–0.89)**, significantly *below* unity. Because Section 7.1 establishes that the expected count rises steeply with marginal strength, and the bands are not exchangeable on it (median $\log_2(RR_A \times RR_B)$ of 2.85 unsupported, 4.16 plausible, 5.32 known pair, 8.15 positive control), this comparison requires adjustment for that covariate as well.

**Table 9.** Band enrichment adjusted for marginal strength.

| Band | Crude | Stratified on marginal strength (95% CI) |
|---|---:|---|
| Plausible | 0.767 | **0.749 (0.567–0.973)** — still below unity |
| Known pair | 2.015 | 1.835 (0.99–2.989) — now includes unity |

The confound is real but small, and does not run in the direction one might guess: signal rate by marginal-strength quintile is weak and non-monotone (3.7%, 7.2%, 6.6%, 5.2%, 6.7%). **The plausible band's deficit survives adjustment.** The known-pair band's apparent 2× does not survive intact — the dependence-respecting interval now touches unity — which is consistent with the circularity argument above rather than an additional finding.

### 7.6 Temporal stability: composition, not count

Requiring the signal in all three eras reduces 1,022 pairs to **19** (170 pairs signal in two eras, 778 in one).

**What this filter is.** Each era bin is scored against the *same* threshold (+0.436), calibrated on the full 22 years. A bin holds roughly a third of the cases, so the shrinkage bound is systematically lower in every bin, and the filter is far stricter than "the signal is present in each era": it is "the signal clears a full-data threshold three times on third-power data." It therefore selects on co-report count as much as on temporal consistency. This does not affect the count comparison below, because the identical filter is applied to the negative controls, but era-stability is not a pure measure of temporal persistence and should not be read as one.

Of the 19, nine carry prior support. But the same filter applied to the 6,471 negative controls that also enter the screen admits **6 of them (0.093%, 95% CI 0.039–0.191%)**, implying **16.1 era-stable pairs by chance (95% CI 6.8–33.2) against 19 observed**.

**The number of era-stable pairs is not distinguishable from chance.** An earlier version of this analysis reported this filter as the paper's principal contribution, on the basis of an enrichment figure computed without ever applying the filter to negative controls. That was wrong.

**Figure 6.** *Era-stability against chance* (`figure4_era_stability.png`). Number of era-stable pairs observed (red diamond) against the number expected by chance (bar, with 95% interval), computed by applying the same filter to the negative controls. The observed count lies inside the interval.

What appeared to survive was a composition-based claim: among the era-stable pairs, 10 of 1,339 label-documented pairs signal against 9 of 16,036 undocumented ones — enrichment 13.31× (95% CI 5.42–32.69), interval excluding unity. That figure does not withstand the two corrections applied to every other enrichment in this paper: it uses the any-endpoint reference shown above to be 82% endpoint-irrelevant, and it is unstratified on co-report count.

**Table 10.** Era-stable composition under each reference and scope.

| Reference | Scope | Documented signalled | Crude (95% CI) | Stratified (95% CI) |
|---|---|---|---|---|
| Any endpoint | All pairs | 10/1,339 | 13.31 (5.42–32.69) | — |
| Any endpoint | No control drug | 2/1,069 | 4.45 (0.90–22.0) | — |
| Endpoint-specific | All pairs | 8/240 | 51.9 (21.1–127.9) | 32.6 (0.0–173.8) |
| **Endpoint-specific** | **No control drug** | **0/142** | — | **0.0** |

**Once the reference is made endpoint-specific and control drugs are removed, not one era-stable pair is documented.** The composition claim therefore rests entirely on pairs containing a drug the investigators had already nominated — the same circularity identified in Section 7.5, which an earlier draft asserted this analysis had escaped. It had not. Neither how many pairs survive the era filter nor which ones is distinguishable from the null.

### 7.7 Confounding, and the pairs it does not explain

The 19 era-stable pairs comprise 5 positive controls, 4 known pairs, 2 plausible and 8 unsupported. Both of the last two groups are examined here; an earlier version examined only the eight.

**The eight unsupported pairs are statin proxies.** Most carry a statin, fibrate or colchicine on **88–100%** of their event cases against a 40.5% background — paroxetine + valsartan, levothyroxine + valsartan, aspirin + metoprolol and aspirin + ramipril at exactly 100%. These are markers for "cardiovascular patient taking a statin": the statin is the cause and the pair is a proxy.

**Adjusting for inpatient status.** Two adjustments were attempted and only the second is adequate. Excluding cases containing any of 30 hand-picked procedural or critical-care agents (neuromuscular blockers, anaesthetics, vasopressors, IV fluids) **removes 275,205 cases — 1.4% of the analysis population** — and leaves every band enrichment essentially unchanged (plausible 0.76 → 0.75). An earlier version reported this as evidence that inpatient confounding does not drive the result. **It is not evidence of that**: perturbing 1.4% of the data cannot exclude a confounder, and a null was near-guaranteed before the analysis ran. FAERS records the outcome directly, and stratification on `outc_cod = 'HO'` — 5,709,555 reports, already parsed but previously unused — is the adequate instrument; it is reported in Section 7.9.

What the drug-list exclusion did show is that removing one confounder reveals the next: the replacement top hits were naloxone + zopiclone, which carries an overdose or impaired-consciousness term on 64.9% of its event cases against a 13.2% background. Rhabdomyolysis has many non-interaction causes, each with its own drug signature.

**The same test does not dispose of the two plausible pairs**, which occupy the band designated in advance as where a novel interaction would appear.

**Table 11.** The two era-stable pairs in the plausible band.

| Pair | Co-reports | Events | Rate | $\Omega_{\mathrm{add},025}$ | Event cases carrying a *third* implicated drug |
|---|---:|---:|---:|---:|---:|
| **Atorvastatin + fusidic acid** | 185 | 155 | **83.8%** | 1.02 | **13/155 (8.4%)** vs 48.7% background |
| Ciprofloxacin + simvastatin | 377 | 152 | 40.3% | 1.66 | 68/152 (44.7%) vs 48.7% background |

Atorvastatin + fusidic acid is the **highest-event-rate pair in the entire screen** — above every one of the 16 positive controls, the best of which (cyclosporine + simvastatin) reaches 71.0% — is era-stable across all three eras, exceeds its additive expectation, and is *under*-represented for third-drug polypharmacy rather than over-represented. It is also a real and serious interaction: systemic fusidic acid with a statin is contraindicated.

It appears in the plausible band because **neither reference contains it**. Fusidic acid is not approved for systemic use in the United States, so openFDA returns no label for it and no fusidic acid pair can ever be `label_documented`; it is also absent from the investigators' own implicated-drug list. The screen ranked a genuine contraindicated interaction first, and both evaluation references were blind to it.

No pair identified by this screen constitutes a *novel* pharmacokinetic interaction — atorvastatin + fusidic acid is documented, not novel. But the earlier claim that every era-stable pair traces to confounding was too strong. The top of the ranking is a genuine severe interaction that the references could not see, which is a statement about the references at least as much as about the method.

### 7.8 Conclusions do not depend on the unverified shrinkage constant

α = 0.5 could not be verified against the primary source. Varying it over a 20-fold range, recalibrating the threshold on the full negative-control pool at each value:

**Table 12.** Sensitivity to the shrinkage constant.

| α | Calibrated threshold | Positive controls recovered | Pairs signalled |
|---:|---:|---:|---:|
| 0.1 | +0.635 | 10/15 | 998 |
| 0.25 | +0.544 | 10/15 | 1,011 |
| 0.5 | +0.436 | 11/15 | 1,022 |
| 1.0 | +0.303 | 12/15 | 1,041 |
| 2.0 | +0.156 | 12/15 | 1,069 |

Control recovery varies by two pairs and the signal count by 7% across the range. No conclusion in this paper turns on the value of α; the constant remains unverified against the primary source but is no longer a live dependency.

**Figure 7.** *Sensitivity to α* (`figure6_alpha_sensitivity.png`). Positive controls recovered (left axis) and pairs signalled (right axis) as α varies over a 20-fold range, with the threshold recalibrated on the full negative pool at each value. The dotted line marks the adopted α = 0.5.

### 7.9 Sensitivity analyses

> Every analysis in this section is post-hoc; see Section 6.3. Intervals are nominal.

**Screen size and the power of the negative result.** The negative result at top-200 rested on 142 documented non-control pairs. Extending the label reference to 800 drugs and widening the screen raises this to 444.

**Table 13.** Enrichment among non-control pairs at three screen sizes.

| Screen | Pairs | Documented non-control | Crude enrichment | Stratified (cluster bootstrap) |
|---|---:|---:|---|---|
| Top-200 | 17,375 | 142 | 1.23 (0.67–2.24) | 1.045 (0.32–2.034) |
| Top-400 | 53,229 | 321 | 1.77 (1.18–2.65) | 1.311 (0.599–2.117) |
| Top-800 | 131,888 | 444 | 2.05 (1.39–3.04) | 1.265 (0.601–1.988) |

The crude interval excludes unity at top-400 and top-800; the **cluster bootstrap, which resamples drugs rather than pairs, does not** at any size. With each drug appearing in hundreds of pairs, the pairwise interval is anticonservative, and the dependence-respecting interval is the one to read. **The negative result survives the power increase.**

**Figure 8.** *Screen size and power* (`figure7_screen_size_power.png`). Enrichment among non-control pairs at three screen sizes, under the pairwise interval (red, anticonservative because pairs share drugs) and the drug-level cluster bootstrap (blue).

**Selection on the outcome.** Screened drugs are chosen by co-reporting with the event. Reselecting the same number by total report volume gives stratified enrichment 0.368 (0.0–1.839) against 1.045 (0.32–2.034) for the primary selection. Both include unity, but **this check is close to uninformative and should not be read as reassurance**: volume-based selection leaves only 38 documented non-control pairs, of which one signals, and the crude interval runs 0.14–6.49. The honest statement is that this analysis has too little power to detect whether outcome-based selection manufactures the result, not that it does not.

**Era bin definitions.** The three-bin split was fixed by hand. Varying it gives 84 era-stable pairs at two bins, 19 at three, 6 at four and 3 at five. The count is almost entirely a function of how many bins are demanded — a further reason not to treat it as a finding.

**Ingredient resolution accuracy.** Across 32,655 verbatim drug names carrying FDA's own `prod_ai` annotation on at least 20 rows, **98.99%** of rows agree with the modal ingredient for that name and **95.9%** of names are annotated unanimously. Level-2 backfill copies that annotation, so this bounds its reliability.

**The polypharmacy cap was chosen on the evaluation set.** The 20-drug cap was adopted because it improved control recovery *and* the false-positive rate — a decision made by looking at the controls, not previously disclosed as such.

**Table 14.** Polypharmacy cap sweep.

| Cap | Analysis cases | Additive | Multiplicative | FPR at $\Omega_{025}$ > 0 |
|---:|---:|---:|---:|---:|
| 10 | 20,202,853 | **13/16** | 4/16 | **6.0%** |
| 15 | 20,259,682 | 12/16 | 4/16 | 6.0% |
| **20 (adopted)** | 20,274,416 | 12/16 | 4/16 | 6.7% |
| 30 | 20,284,277 | 12/16 | 2/16 | 7.8% |
| 40 | 20,288,002 | 12/16 | 2/16 | 7.6% |
| None | 20,293,421 | 11/16 | 2/16 | 6.9% |

Capping is justified — every capped arm beats the uncapped one on recovery, and the multiplicative null degrades from 4/16 to 2/16 without a cap, so the headline contrast is *understated* at cap 20. But **20 is not the optimum**: a cap of 10 is better on both axes (13/16 at 6.0%). The adopted value is a round number that was not tuned further, and the conclusion is flat across 15–40.

**Inpatient status, using the reported outcome code.** Stratifying the whole screen on `outc_cod = 'HO'` splits the population into two large, comparable halves.

**Table 15.** Screen results stratified on reported hospitalisation.

| Stratum | Cases | Event cases | Event rate | Plausible | Known pair |
|---|---:|---:|---:|---:|---:|
| Hospitalised | 4,274,465 | 28,610 | 0.669% | **0.639** | 1.839 |
| Not hospitalised | 15,999,951 | 13,279 | 0.083% | **0.825** | 1.885 |

Hospitalisation is strongly associated with myotoxicity reporting — an **8-fold** difference in event rate — so it is a genuine confounder, unlike the 1.4% drug proxy which could not have detected one. **Both strata reproduce the result**: the plausible band sits below unity in each, and known-pair enrichment is essentially identical across them. The negative discovery result is not an artefact of inpatient case mix.

**Demographic strata.** Myotoxicity is reported at 2.4× the rate in male as in female reports (0.327% across 6,998,836 male cases versus 0.136% across 10,686,771 female cases), consistent with the known epidemiology of rhabdomyolysis. Stratified enrichment is 1.723 (0.534–3.447) in female and 0.542 (0.0–1.459) in male reports. Both intervals overlap unity and each other; these subgroups are underpowered and no subgroup claim is made. Age and country were not stratified.

### 7.10 Recovery on controls the investigators did not choose

Leave-one-out (Section 7.2) bounds optimism only in the choice of *estimand*, not of controls. A second control set was therefore drawn by FDA labelling: every label-documented myotoxicity pair with at least 50 co-reports that is not among the 16. Both nulls are scored at the same threshold; an earlier version of this table compared the multiplicative null at $\Omega_{025}$ > 0 against the additive null at the calibrated +0.436, an asymmetry that ran *against* the additive null but was not a like-for-like comparison.

**Table 16.** Recovery on author-selected and label-selected control sets.

| Control set | *n* | Threshold | Multiplicative | Additive |
|---|---:|---|---:|---:|
| Author-selected | 14 powered | $\Omega_{025}$ > 0 | 4/16 | **12/14 (86%)** |
| Label-selected | 349 | $\Omega_{025}$ > 0 | 29 (8.3%) | **55 (15.8%)** |
| Label-selected | 349 | Calibrated +0.436 | 15 (4.3%) | **42 (12.0%)** |

The direction replicates at both operating points — the additive null recovers 1.9× as many pairs at threshold 0 and 2.8× at the calibrated threshold — but the recovery *rate* collapses from 86% to 12–16%.

**The gap is not statistical power.** Co-report counts are statistically indistinguishable between the two sets (median 420 versus 321, Mann–Whitney *p* = 0.45). Recovery in the label-selected set *falls* as co-reporting rises — 19%, 17%, 10%, 2%, 0% across quartiles and the top decile — the opposite of a power effect.

The mechanism is the event rate among co-reports: 29.2% for author-selected pairs (141.4× the database baseline), 0.72% for label-selected pairs (3.5×), and 0.12% for the top decile of label-selected pairs by co-reporting (**0.57×**, below baseline). The most heavily co-reported label-documented pairs show no elevation of the event rate at all. These are common co-prescriptions whose labels carry a *class* warning ("use with caution with CYP3A4 inhibitors") rather than a pair-specific one. There is nothing in the data for any method to detect.

**Neither figure is the sensitivity of the method.** 86% is an upper bound contaminated by selection for famous, well-reported interactions; 12% is a lower bound contaminated by a reference containing pairs with no detectable signal. They bracket the true value. Pinning it down requires a severity-graded reference distinguishing pair-specific interactions from class warnings.

### 7.11 Generalisation to other events

The paper's claim is conditional: Ω fails *when the drugs under study are the leading reported causes*. One event demonstrates the phenomenon, not the condition. Two further events were analysed.

The torsade PT list is curated to the same standard as the primary event — repolarisation-specific terms only. An earlier version also counted `CARDIAC ARREST`, `VENTRICULAR TACHYCARDIA` and `VENTRICULAR FIBRILLATION`, non-specific terminal events with many non-QT causes, which tripled the event rate and made the replication a looser test than the analysis it was replicating. Both lists are reported.

**Table 17.** Recovery and marginal-strength gradient across events.

| Event | Event rate | Median marginal RR | Multiplicative | Additive | Ω vs $\log_2(RR_A \times RR_B)$ | $\Omega_{\mathrm{add}}$ vs same |
|---|---:|---:|---:|---:|---|---|
| Rhabdomyolysis (primary) | 0.207% | — | 4/16 | 12/16 | *r* = −0.63, *p* = 0.009 | *r* = −0.65, *p* = 0.007 |
| **Torsade / QT (curated PTs)** | 0.199% | 19.3 | **0/10** | **9/10** | ***r* = −0.81, *p* = 0.005** | *r* = −0.79, *p* = 0.006 |
| Torsade / QT (broad PTs) | 0.659% | 11.2 | 1/10 | 7/10 | *r* = −0.76, *p* = 0.011 | *r* = −0.72, *p* = 0.020 |
| Anaphylaxis | 0.410% | 5.2 | 1/4 | 1/4 | *n* = 4, uninformative | *n* = 4, uninformative |

**The failure replicates on torsade de pointes**, an independent drug-dominant event with its own control set and, under the curated PT list, an event rate within 4% of the primary event's. Ω recovers **0/10** against 9/10 for the additive null. Amiodarone + sotalol, two of the most strongly QT-prolonging agents in use, scores Ω = −1.63. The marginal-strength gradient reproduces (*r* = −0.81, *p* = 0.005) and, as in Section 7.1, is not specific to the multiplicative null: $\Omega_{\mathrm{add}}$ shows *r* = −0.79 (*p* = 0.006) on the same pairs. The replication is of the *recovery failure*, which is unambiguous, and of the shared over-prediction — not of a gradient peculiar to Ω.

**The anaphylaxis arm is invalid by construction, not underpowered**, and we report it as a failed design rather than a weak result. It was intended to supply the negative case: an event with diffuse marginals where Ω should perform comparatively well. But anaphylaxis is overwhelmingly single-agent, and there is no established drug pair whose *interaction* causes it. The pairs used are common co-exposures among agents that each cause anaphylaxis independently, which is a different thing entirely. **There is no interaction present for either null to detect, so no additional data would make this arm informative.** Two entries in the first version were worse than weak and have been removed: amoxicillin + clavulanate potassium is a fixed-dose combination product, not a drug–drug interaction at all, and contrast media + iohexol pairs a class with a member of that class.

The phenomenon therefore generalises to a second event; the condition has no valid negative case and remains a hypothesis.

---

## 8. Discussion

The pipeline recovers known pharmacology on the investigators' own control set and has a characterised false-positive rate. What it does not do is provide evidence of enriching for genuine interactions beyond the drugs already nominated. The central claim of an earlier version of this work — that temporal stability is a powerful discriminator — did not survive the validation it had not been given.

### 8.1 The multiplicative null is inappropriate for drug-dominant events

Ω recovers 4/16 known interactions against 12/16 for an additive null at a matched false-positive rate, and 0/10 against 9/10 on a second such event. This is precisely the situation for the best-characterised interaction classes, which is where a DDI method is most likely to be validated, so the failure mode is one that a method could pass into routine use without ever encountering.

The condition is checkable in advance: compute the marginal relative risks before choosing the null. That is a practical recommendation with essentially no cost.

The mechanism is narrower than we initially claimed. Observed joint event rates are **flat** in marginal strength (*r* = +0.12) while both nulls predict them to rise steeply (*r* ≈ +0.94). Joint risk saturates, and both models miss it; the multiplicative null fails much harder only because its expectation is larger at every point. We initially read the Ω-versus-marginals correlation as diagnostic of multiplicativity. It is not, since the additive null shows the same gradient. What is diagnostic is the recovery comparison at matched error rates.

### 8.2 Polypharmacy leverage as a design constraint

A tenth of a percent of cases supplied a third of all pair evidence at an enriched event rate. This is invisible from positive controls and appears only from the false-positive side, which has a practical consequence for how such systems should be validated: a screen validated exclusively on known-positive recovery will not detect it. Any pairwise screen over spontaneous reports should cap drugs per case, and should report the cap and its sensitivity.

### 8.3 Circular evaluation

An evaluation whose annotation is written by the same investigators as the control set will show enrichment whether or not the method works. The gap between 2.02× and 1.12× here is entirely that circularity. Screens of this kind reporting enrichment against author-curated reference lists should be read accordingly, and reviewers should ask whether the annotation and the control set share authorship.

### 8.4 Trade-offs and deployment considerations

The additive null is more permissive than the multiplicative one at any fixed threshold, which is why the two must be compared at matched false-positive rates rather than at a common nominal cut. In a deployed surveillance setting the operating point should be calibrated against an explicit negative-control pool, held out from the calibration sample, and re-calibrated whenever the underlying database or event definition changes; the 6.7% observed rate against a 2.5% nominal rate shows how far a nominal threshold can drift from its intended meaning.

Computationally the approach is undemanding. The full history fits on one workstation, and the analysis completes in minutes, so the constraint on deploying this class of screen is not compute but reference quality and curation effort.

### 8.5 Generalisation

Two findings generalise beyond the primary event: the failure of the multiplicative null under drug dominance, replicated on torsade de pointes, and polypharmacy leverage, which is a property of pairwise combinatorics rather than of any particular endpoint. The conditional claim — that drug dominance *causes* the failure — does not yet generalise, because the negative case required to establish it could not be constructed.

Conclusions may also be FAERS-specific. Two pipeline components are externally benchmarked (deduplication against AEOLUS, 8% apart; ingredient resolution against DiAna, 98.0% versus 98.94%), and the central finding replicates on a second event within FAERS, but no external reporting system has been used.

---

## 9. Limitations

**Reference quality is the binding constraint.** The independent reference is FDA labelling, not a curated DDI database, and its coverage tracks US marketing status rather than pharmacology. DrugBank is licensed and unavailable; the ONC list is available but class-level and excludes the canonical myotoxicity pair (Section 2.5). Labelling is independent of the investigators and captures 16/16 positive controls, but it is informed by FAERS itself, warns by class as well as by name, and is **absent entirely for 17.2% of screened ingredients — 9.8% of pairs** — among them cerivastatin, the fibrates and fusidic acid. Section 7.5 reports the analysis restricted to label-covered pairs and the conclusion is unchanged, but the residual insensitivity biases enrichment *toward* this paper's own conclusion. The measured false-positive rate remains an upper bound.

**The screen's top-ranked pair is a documented interaction no reference contained.** Atorvastatin + fusidic acid has the highest event rate in the screen, is era-stable, and is contraindicated in practice, yet is absent from both the investigators' list and openFDA. It is not a novel discovery, but its presence means the negative discovery result measures the references at least as much as the method, and the size of that effect is unknown.

**The positive controls are author-selected and clustered.** They are the only evaluation set, and leave-one-out addresses optimism in estimand choice only. They comprise five victim drugs rather than sixteen independent trials — simvastatin appears in seven — so recovery intervals are computed by resampling the victim drug and are correspondingly wide (50–100% on the powered subset).

**The headline contrast is not robust to widening both design choices at once.** Of the four arms in Table 6, three show the additive null recovering 7–8 more controls and the fourth shows no difference. The pre-specified arm is one of the three, but a reader is entitled to weigh the fourth.

**Ingredient resolution accuracy is bounded, not directly measured.** FDA's own annotation of a given verbatim name is 98.99% self-consistent, which bounds the level-2 backfill, but no manual audit against external ground truth was performed.

**The PT list had a single curator.** A second human reader was not available. A mechanical second annotation flags 119 terms against the 23 curated, agreeing on 21; the mechanical pass is deliberately over-inclusive (capturing cardiomyopathy, fibromyalgia and muscle spasms, all excluded on clinical grounds), so the low Jaccard index (0.174) reflects that over-inclusion rather than disagreement about the curated terms. This is a coverage check, **not** an inter-rater statistic.

**Era bin boundaries are a researcher degree of freedom.** The era-stable count runs from 84 to 3 depending purely on how many bins are demanded.

**The near-duplicate rule uses exact set matching** and provably misses the clusters documented in Section 7.4. The residual is bounded: blocking on date, age, sex and country and comparing drug sets by Jaccard similarity finds 421 further pairs above 0.8 that the exact rule did not merge, affecting **226 cases (1.17% of event cases)**. A fuzzy rule was not adopted, since a Jaccard threshold is itself an unvalidated parameter.

**No external validation on another reporting system, and the public interfaces cannot supply one.** VigiAccess, the free public window onto VigiBase, groups results by active ingredient and continental region and does not expose individual case records; it therefore returns single-drug adverse-reaction counts only and has **no facility for drug pairs**, so it cannot validate a drug-interaction result at all. Pair-level VigiBase access requires a research agreement with the Uppsala Monitoring Centre, and EudraVigilance likewise publishes single-substance report counts.

**Demographic subgroups are underpowered**, and age and country were not stratified.

**α = 0.5 is corroborated by secondary sources, not by the primary.** Section 7.8 shows no conclusion depends on α across a 20-fold range, but the primary source remains paywalled and unread by the authors.

**Spontaneous reporting has no exposure denominator.** Nothing here estimates risk, only reporting disproportionality.

**The negative result is bounded, not absolute.** At the widest screen it rests on 444 documented non-control pairs, with approximately 70% power at a true enrichment of 2.0 and 30% at 1.5. It excludes enrichment above roughly 1.988× on the dependence-respecting interval. A real but modest enrichment would still be missed.

**Screened drugs are selected on the outcome**, which is selection on the dependent variable. Reselecting by total report volume does not change the conclusion, but the negative controls are drawn from the same selected universe and share any induced bias.

**The conditional claim is not established, and the intended negative case was invalid rather than underpowered** (Section 7.11).

---

## 10. Future work

**A severity-graded, ingredient-level reference** is the single change that would most improve this evaluation. It would collapse the 12–86% sensitivity bracket into a point estimate by distinguishing pair-specific interactions from class warnings, and would remove the structural blindness that currently excludes 9.8% of screened pairs. Obtaining one requires a DrugBank licence or equivalent curated compendium.

**A valid negative case for the conditional claim.** Establishing that drug dominance *causes* the multiplicative null's failure requires an event with weak marginal associations *and* genuinely documented interacting pairs. The anaphylaxis arm failed on the second requirement. Identifying a suitable event is a literature task, not a computational one.

**External replication on a second reporting system.** Pair-level access to VigiBase under a UMC research agreement, or to EudraVigilance case-level data, would test whether the findings are FAERS-specific. The public interfaces cannot support this.

**A second independent curator for the event definition**, enabling a genuine inter-rater statistic in place of the mechanical coverage check reported here.

**Extension of the screen beyond the top 200 drugs.** Section 7.9 shows the negative result survives to top-800; extending further would tighten the bound, at a cost that is combinatorial rather than linear.

**A pre-registered replication** of the null comparison on a third drug-dominant event, with the specification grid and operating point fixed in advance, would remove the post-hoc character of much of Section 7.9.

---

## 11. Conclusion

A reproducible pipeline over the complete public history of FAERS recovers known rhabdomyolysis interactions on a verified control set with a measured false-positive rate, and finds no evidence of novel interaction discovery.

The robust methodological contributions are two. First, the multiplicative null underlying the standard DDI disproportionality measure is unusable when the drugs under study are the dominant reported causes of the outcome: it recovers 4/16 established interactions where an additive null recovers 12 at a matched false-positive rate, and 0/10 against 9/10 on a second such event. The mechanism is that observed joint risk saturates while both nulls predict it to rise with marginal strength, so the two differ in the level of their expectation rather than its gradient. Second, high-polypharmacy reports exert leverage far out of proportion to their number: 0.09% of cases contribute 34.7% of all drug pairs at a 4× enriched event rate, and must be capped in any pairwise screen.

The temporal-stability filter promoted in an earlier version of this work does not survive validation against negative controls and is reported here as a negative result. Claims that this class of screen discovers novel interactions should be treated with scepticism until the annotation used to evaluate them is demonstrably independent of the control set used to build them.

---

## Data and code availability

All code, configuration and result tables are available in the accompanying repository [TODO: repository URL / DOI]. Every figure quoted in the Abstract and Results is generated into `results/canonical_numbers.json` by a single deterministic run and asserted against this text by `tests/test_canonical_numbers.py`; pipeline statistics quoted in Methods are persisted under `audit.provenance` in the same file and asserted alongside them. Figures drawn from cited work are attributed and not regenerated. The pipeline is deterministic: two full runs produce byte-identical output. A SHA-256 hash is recorded for each of the 90 source archives. Per-phase development records, including errors made and corrected, are retained in the repository.

**This is research code and a research result. It is not clinical guidance.**

## Acknowledgements

[TODO]

## Funding

[TODO]

## Conflicts of interest

[TODO]

---

## References

1. Bate A, Lindquist M, Edwards IR, Olsson S, Orre R, et al. A Bayesian neural network method for adverse drug reaction signal generation. *Eur J Clin Pharmacol.* 1998;54(4):315–321. doi:10.1007/s002280050466
2. Banda JM, Evans L, Vanguri RS, Tatonetti NP, Ryan PB, Shah NH. A curated and standardized adverse drug event resource to accelerate drug safety research. *Sci Data.* 2016. PMID 27193236. Data: doi:10.5061/dryad.8q0s4
3. DuMouchel W. Bayesian data mining in large frequency tables, with an application to the FDA spontaneous reporting system. *Am Stat.* 1999;53(3):177–190. doi:10.1080/00031305.1999.10474456
4. Evans SJW, Waller PC, Davis S. Use of proportional reporting ratios (PRRs) for signal generation from spontaneous adverse drug reaction reports. *Pharmacoepidemiol Drug Saf.* 2001;10(6):483–486. doi:10.1002/pds.677
5. Fusaroli M, et al. Enhancing transparency in defining studied drugs: the open-source living DiAna dictionary for standardizing drug names in the FAERS. *Drug Saf.* 2024;47:271–284.
6. Norén GN, Sundberg R, Bate A, Edwards IR. A statistical methodology for drug–drug interaction surveillance. *Stat Med.* 2008 Jul 20;27(16):3057–3070. PMID 18344185. doi:10.1002/sim.3247
7. Phansalkar S, et al. High-priority drug–drug interactions for use in electronic health records. *J Am Med Inform Assoc.* 2012;19(5):735–743. PMID 22539083. doi:10.1136/amiajnl-2011-000612
8. Rothman KJ. Causes. *Am J Epidemiol.* 1976;104(6):587–592.
9. Tatonetti NP, Ye PP, Daneshjou R, Altman RB. Data-driven prediction of drug effects and interactions. *Sci Transl Med.* 2012. PMID 22422992. doi:10.1126/scitranslmed.3003377
10. Thakrar BT, Grundschober SB, Doessegger L. Detecting signals of drug–drug interactions in a spontaneous reports database. *Br J Clin Pharmacol.* 2007;64(4):489–495.
11. VanderWeele TJ, Knol MJ. A tutorial on interaction. *Epidemiol Methods.* 2014;3(1):33–72. doi:10.1515/em-2013-0005

**Secondary corroboration for the Ω definition** (Section 2): a peer-reviewed review of DDI statistical methodologies (*Front Pharmacol.* 2019;10:1319) and Uppsala Monitoring Centre operational documentation on drug–drug interaction signalling. The primary Norén et al. paper is paywalled and unread by the authors.
