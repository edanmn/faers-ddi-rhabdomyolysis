# FAERS drug–drug interaction project — working context

Handoff document. Read this first in a new session. It carries the state, the
conventions, and the mistakes this project has already made so they are not
repeated.

---

## 1. What this is

A disproportionality analysis of drug–drug interaction (DDI) signals for
rhabdomyolysis/myotoxicity over the **complete public history of FAERS**
(2004Q1–2026Q2, 90 quarterly archives, 328,476,258 rows). It began from a
short PDF guide (`Using FAERS for Drug Interaction Research.pdf`) and grew into
a validated pipeline plus a single full-length manuscript (two conference
papers were split out and, in round 18, merged back in).

**The deliverable is one document** (§4). **The research is finished** —
the analysis is not expected to change. What remains is clerical (§7).

### Headline results (all from `results/canonical_numbers.json`)

| | value |
|---|---|
| Analysis population | 20,274,416 cases, 41,889 myotoxicity events (0.207%) |
| Tier A recovery, threshold Ω₀₂₅ > 0 | additive **12/16**, multiplicative **4/16** |
| Tier A interval (cluster bootstrap on victim drug) | **50–100%** (naive binomial 62–97% is too narrow) |
| Tier B calibrated threshold | **+0.436**, held-out FPR 5.03% (4.37–5.74%) |
| Pooled FPR at Ω₀₂₅ > 0 | additive 6.67%, multiplicative 6.44% |
| **In-regime FPR** (2,345 pairs, 478 drugs) | **additive 9.3% (CI 7.29–11.32%), multiplicative 2.2% (CI 1.24–3.34%)** vs nominal 2.5%, cluster bootstrap over drugs (r23). The multiplicative interval **covers** 2.5%; the additive one excludes it — the miscalibration is one-sided |
| **Recovery gap at matched in-regime FPR** | **1–2 pairs** (8 at the conventional threshold) |
| Torsade in-regime additive FPR | **42.8%** — the 9/10-vs-0/10 result is an operating-point artefact |
| Screen | 1,022 of 17,375 signalled; **1,212** expected by chance strength-matched (872 pooled) |
| Enrichment, control drugs removed | **1.12× (0.69–1.81)** — indistinguishable from unity |

### The manuscript's two claims, as they now stand

- **Calibration.** Neither null is usable at its conventional
  operating point for drug-dominant events, **but they fail in different
  currencies** (r17). Only the additive null is miscalibrated on error rate
  (9.3% against a nominal 2.5%; 42.8% on torsade). Ω runs at 2.2% and 2.0% —
  *at* nominal — and is disqualified by power instead: it is systematically
  negative in this regime and buys its rate by almost never firing. The additive
  null's apparent superiority is mostly an operating-point effect: 8 pairs → 1–2
  at matched error rates, and **zero** on the torsade replication. What survives
  is mechanistic — observed joint risk rises far more shallowly in marginal
  strength (*r* = +0.12, CI −0.40 to +0.58) than either null predicts
  (*r* ≈ +0.94).
- **Evaluation.** A DDI screen shows no enrichment for genuine
  interactions once the annotation is independent of the control set (2.02× →
  1.12×). Reference quality, not method sensitivity, is the binding constraint:
  the screen's top-ranked pair by event rate — **atorvastatin + fusidic acid**,
  155 events in 185 co-reports, contraindicated in practice — is absent from
  every available reference.

---

## 2. How to run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Everything below needs `PYTHONPATH=src` (the package is not installed).
**Order matters** — `run_analysis` rewrites `canonical_numbers.json` wholesale
and drops the downstream blocks:

```bash
python -m faers_ddi.verify_controls --write   # check the 16 controls vs FDA labels
python -m faers_ddi.run_analysis              # writes results/canonical_numbers.json
python -m faers_ddi.sensitivity               # design-choice sensitivity analyses
python -m faers_ddi.generalization            # torsade / anaphylaxis
python -m faers_ddi.audit                     # provenance, coverage, FDR, cap sweep
python -m faers_ddi.regime                    # in-regime error rates, matched recovery
python -m faers_ddi.figures                   # 7 figures
python -m pytest                              # 346 tests
python paper/build.py                         # manuscript.md -> .tex -> .pdf
python paper/build.py --check                 # non-zero if any .tex is stale
```

A `stages` key in the canonical file records which ran;
`test_all_pipeline_stages_have_run` fails on a partial pipeline. Full chain is
roughly 40 minutes. `regime` and `audit` are the slow ones.

**Determinism is real and verified** — two full runs produce byte-identical
output. Every stochastic step is seeded.

### Version control

Public at <https://github.com/edanmn/faers-ddi-rhabdomyolysis>. The repository
root is **this project directory**, not the home directory — `/Users/ravik` is
itself a stale `git init` with no commits, so a `git` command run from a
directory without its own repo will resolve to it and can stage `~/.ssh`,
`~/.claude.json` and the 159 GB `data/` tree. Check `git rev-parse
--show-toplevel` before staging anything.

`data/reference/openfda_labels/` (800 JSONs, 8.7 MB) **is** tracked, because
openFDA drifts and `verify_controls` depends on it. Raw archives are not, and
are reproducible from the FDA source. The instructional PDF the project started
from is third-party and deliberately gitignored — do not commit it.

---

## 3. Architecture

`src/faers_ddi/` — 23 modules. The ones that matter:

| module | role |
|---|---|
| `download`, `column_audit`, `parse` | acquisition; schema audit drives parsing |
| `dedup`, `normalize_drugs`, `define_event` | 6-stage dedup, ingredient resolution, PT curation |
| `omega` | both nulls; IPF fit, gamma-Poisson shrinkage |
| `contingency`, `screen` | case×drug tables, pair counts, band annotation |
| `tier_a` / `tier_b` / `run_analysis` | positive controls / negative controls + calibration / the screen |
| `statistics` | Jeffreys, cluster bootstrap, Mantel–Haenszel, permutation, LOO |
| `sensitivity`, `generalization`, `audit`, `regime`, `verify_controls` | the analyses added by review rounds |
| `figures` | 7 figures, all from the canonical file |

**`results/canonical_numbers.json` is the single source of truth.** Nothing is
quoted anywhere that does not come from it. `tests/test_canonical_numbers.py`
(346 tests) asserts the prose against it.

`paper/build.py` generates `.tex` from `.md` via pandoc + tectonic. **Never edit
a `.tex` by hand** — it is regenerated. Two-column documents declare a body-page
cap; the builder reads the references label's page from the `.aux` and **exits
non-zero if the body exceeds it**.

---

## 4. The maintained document

| file | what | size |
|---|---|---|
| `paper/manuscript.md` | **the single maintained document** — calibration and evaluation | 31 pages |

**Round 18 merged the two conference papers back in.** `paper_a.md`
(calibration) and `paper_b.md` (evaluation) were a split of this manuscript;
they are now in `paper/archive/` with banners, alongside `paper.md` retired in
round 11. `RETIRED` in the test module is the registry, and
`test_retired_documents_are_not_built_and_are_labelled` asserts across it — it
checks the build directory, stale `.tex`/`.pdf`, the banner, and `build.py`.
**Do not revive any of the three.**

Merging was content-preserving by construction: every guard that had been
scoped to `paper_a`/`paper_b` was **rescoped to the manuscript, not deleted**,
and six of them failed on first run. Each failure was a claim the conference
papers made that the manuscript did not — including the vocabulary-hygiene
disclosure, which existed only in `paper_b`, and a genuine denominator bug
(`12/14` powered against `4/16`). All were fixed by adding to the manuscript.
If a document is ever retired again, do it this way round.

One consequence to know: there is no longer a conference-format document, so
**no page cap is enforced anywhere**. `DOCUMENTS` in `build.py` maps the
manuscript to a cap of `None`. If a conference submission is ever wanted, it is
a new derivation from this manuscript, not a revival of the archived pair.

---

## 5. Read this before writing any test

This project has been through **thirty adversarial review rounds**. The
consistent failure has not been in the analysis — it has been in the guards.
**Seven times a test written to catch a specific defect was too weak to catch
it:**

1. a `6/16` check satisfied by the substring inside `16/16`;
2. a guard requiring only the phrase `"companion paper"`, which passed while the
   document made the unqualified claim it was meant to prevent;
3. guards scoped to whichever document was open, so a correction landed in two
   of four documents and the suite stayed green;
4. a withdrawn-phrase check defeated by a **line break** in the prose;
5. (r17) the round-11 withdrawal registered as `"essentially identical
   false-positive rate"`, while `manuscript.md` carried **`"almost identical
   false-positive rate (6.4% vs 6.7%)"`** in its abstract for six rounds —
   defeated by a **synonym**;
7. (r20) a *structural* guard written to close the whole category was
   **decorative on its first draft**: membership in a corpus of every value in
   the canonical file plus every shipped CSV. That corpus renders 470,526
   strings and covers **100% of all one-decimal numbers 0.0–99.9**, so it could
   not fail for any percentage — it passed both mutations. Measured, discarded,
   replaced with declared per-table provenance. **Mutation-test before
   believing a guard, including your own.**
6. (r19) two guards checked that a qualifying phrase appeared **anywhere in the
   document**. It did — in §4.5 — while the Abstract *and* Limitations each
   carried the round-10 withdrawn claim, one of them asserting the 800-drug
   cache figure of the *screened* set outright (17.2% where it is 5.5%).
   Defeated by **distance**: the qualifier sat 700 lines from the claim. Both
   guards now bind claim to qualification **per sentence**.

Note what each of these has in common: the registry matches *surface strings*,
so it only ever catches the exact phrasing whoever wrote the entry had in front
of them. When retiring a claim, register the phrasings you did **not** write.

Each was written by whoever had just fixed the defect. **A test written that way
encodes where you were looking, not what must be true.**

Standing practice, non-negotiable:

- **Mutation-test every new guard.** Reintroduce the defect, watch the test
  fail, restore. If it does not fail, the guard is decorative.
- **Scope document assertions to the document *set***, never one file.
  `MAINTAINED` in the test module is the registry.
- **Normalise whitespace before matching prose.**
- **Withdrawn claims go in the registry** in
  `test_no_maintained_document_carries_a_withdrawn_claim`, tagged with the round
  that retracted them.

**346 passing means the stated numbers match the computed ones. It does not mean
the right quantity was computed, nor that the sentence built on a correct
number says what the number means** (r17). Round 11 overturned the central claim while
every test passed, before and after.

---

## 6. Corrections already made — do not reintroduce

Detail in `results/PHASE*_FINDINGS.md` (16 files). The ones that bite:

| claim | status |
|---|---|
| Abstract citing §4.6 for the in-regime rates | **wrong r28** — they are derived in §4.3; §4.6 is era stability. Second time a *semantically* wrong reference passed the r19 existence check. Now a registry, `CROSS_REFERENCE_BINDINGS` |
| demographic table showing only the clustered interval | **completed r28** — the crude female enrichment **2.13 (1.20–3.78)** excludes unity and is the only such non-control figure in the paper. It is now shown, as an instance of the anticonservatism the paper argues for, not hidden by it |
| generalization table "median marginal RR" blank for the primary event | **filled r27** — **24.3**, on the same definition the other rows use. The column now orders the events: rhabdo 24.3 > torsade 19.3 > broad 11.2 ≫ anaphylaxis 5.2, which is the paper's conditional made quantitative |
| in-regime pool and Table 2 marginals unexported | **shipped r27** — `in_regime_pool.csv` (19,826 rows, 2,345 flagged) and `rr_a`/`rr_b` in `tier_a_results.csv`. Bounds at 6 dp, not 3: at 3 dp the file gave 9.30% vs 9.34%, one pair in 2,345. **This closes the last of the four r17 findings** |
| "0 orphans across all 328,476,258 rows" | **overstated r26** — the orphan check covers the **six child tables, 303,663,833 rows**; DEMO is the parent and cannot orphan itself. The manifest check covers all seven (328,476,258) and is separate evidence |
| 104,186 vs 98,102 withdrawn cases | **reconciled r26** — not a contradiction: 104,186 match in either era (what stage 4 removes), 98,102 in FAERS-era DEMO. `validate_parse` filtered `era <> laers` without saying so. The 6,084 LAERS-only ids are **evidence for** the shared id space |
| "the broad tier includes the two MedDRA concepts held out…" | **wrong r25** — broad adds **13 PTs in 7 concepts**, including MYALGIA (163,419 reports). Fixing the event definition in r24 left this characterisation behind, so the paper stated two compositions for one tier |
| "the event was defined by 23 PTs in 10 concepts" | **wrong r24** — that is the whole curation. Every primary result uses the **core** tier: **10 PTs in 3 concepts**. core admits 42,058 event cases, broad 339,063 — **8×**. Stated now, and guarded from the config outward |
| `tier_b_pairs.csv` shipping 2,000 rows | **wrong r24** — the analysis uses **16,138**. The shipped file was a balanced sample from the retired `n_pairs: 2000` regime, and recomputed the threshold at +1.273 vs +0.436. Regenerated; config key set to null |
| Figure 5's band data | **hardcoded r22** — fourteen literals in `figures.py`, not pipeline output. Every value was **exactly right** (verified against the DB), but unverifiable, while the paper claimed every figure comes from the canonical file. Now `audit.polypharmacy_bands`, exported to `results/tables/polypharmacy_bands.csv` |
| "34.7% of pairs at a 4× enriched event rate" | **incomplete r22** — 4.3×, and the aggregate hides a reversal: the 51+ band is the largest pair contributor (18%) at **0.03%**, ~7× *below* background. Disclosed |
| Figure 2 title "the better established the interaction…" | **wrong r22** — the x-axis is marginal strength; all 16 controls are equally established |
| Figure 3's era-stable point (13.31×) | **removed r21** — §4.6 retracts the value; plotting it beside the surviving results showed a reader the artefact the paper exists to warn about. Guarded by `test_figures_do_not_plot_retracted_quantities` |
| Table 1 of §4.1 (observed / multiplicative / additive joint rates) | **stale r20** — the nine values matched no arm, were absent from canonical, were asserted by no test, and contradicted both the adjacent prose and Figure 1. Correct: 56.2/73.9/28.3, 14.9/72.6/23.1, 22.3/29.2/11.0 |
| lovastatin pairs "n_ab of 19 and 1" | **wrong r20** — core/primary gives **13 and 1**; no arm yields 19 |
| alirocumab + ipratropium 88/88 | **unverifiable r20** — in no shipped table; now attributed in-text to the uncapped run |
| "17.2% of screened ingredients have no label", cerivastatin/fibrates as evidence | **withdrawn r10, found live again r19** in the Abstract and Limitations. The screened figure is **5.5%** (11/200); 17.2% is the 800-drug cache. The four extra drugs were never screened |
| "9.8% of pairs undocumentable" | **wrong r19** — 1712/17375 = 9.853% → **9.9%**. The value was stored pre-rounded to 4dp and re-rounded for display, and the guard re-derived it from the same rounded intermediate |
| era-stable "expected by chance" read off `expected_era_stable_by_chance` | **trap r19** — that key held the **upper confidence limit** (33.2), not the expectation (16.1). Renamed; a point estimate is now emitted beside it |
| "(95% CI 6.8–33.2)" on the era-stable expectation | **wrong r19** — exact Jeffreys gives 6.73 → **6.7** |
| "**both** nulls are severely miscalibrated" | **withdrawn r17** — 2.2% is 52/2345; its Jeffreys interval covers 2.5% and exact binomial *p* = 0.43. Torsade is 3/152, *p* = 1.00. Only the **additive** null is miscalibrated on error rate; Ω fails on **power** |
| "Ω is about twice as conservative as advertised" | **wrong r17** — 2.5/2.2 = 1.13×, never computed. The additive "four times too permissive" (3.7×) was right |
| "the observed joint event rate does not rise with marginal strength at all" | **overclaimed r17** — CI −0.40 to +0.58 admits a moderate rise; say "far shallower than either null predicts" |
| "almost identical false-positive rate (6.4% vs 6.7%)" | **withdrawn r17** — the r11 withdrawal, surviving in `manuscript.md` behind a synonym |
| "essentially identical false-positive rate (6.4% vs 6.7%)" | **withdrawn** r11 — in-regime rates are 2.2% vs 9.3% |
| torsade "0/10 vs 9/10" as a successful replication | **withdrawn** r11 — vanishes at matched rates |
| "138 of the 800 screened ingredients (17.2%)" | **wrong** r10 — the screen covers 200; it is 11/200 = 5.5% |
| cerivastatin/fibrates/telithromycin as evidence the *screen* is blind | **wrong** r10 — never screened; only fusidic acid was |
| "137.8× baseline" | **stale** r9 — recomputes to 141.4× |
| "189.2 expected" (simvastatin+amiodarone) | **stale** r9 — 189.54 |
| Ω = −0.973 for simvastatin+amiodarone | **stale** r7 — −0.385 |
| era-stability as a discriminator | **negative result** — 19 observed vs 16.1 by chance |
| Ω-vs-marginals correlation as diagnostic of multiplicativity | **wrong** r7 — both nulls show it |
| titles that assert conclusions | **banned** — `test_no_document_title_asserts_a_conclusion` |

Other things established and worth not relitigating: the trailing-delimiter
parse bug (validated by 0 orphans / 328M rows); `prod_ai` applied backwards
resolves 98.0%; deduplication benchmarked against AEOLUS (8% apart); the
polypharmacy cap of 20 was chosen on the evaluation set and cap 10 is better on
both axes; the anaphylaxis arm is **design-invalid**, not underpowered; four
screened "ingredients" are non-drug placeholders (immaterial, disclosed).

---

## 7. What is actually outstanding

1. **One `[TODO]` block** — authors/affiliations, in `manuscript.md`. Note it
   was **added** in round 18: the manuscript had no author line at all, so
   retiring the conference papers would have taken the submission tripwire with
   them and left an authorless document with nothing guarding it. The availability TODO is closed: all
   three documents cite <https://github.com/edanmn/faers-ddi-rhabdomyolysis>.
   The Acknowledgements sections were **removed by author decision**, not left
   unfinished — do not reinstate them. Their removal left three statements with
   no home — **generative-AI disclosure** (this project's code, prose and
   internal review rounds were LLM-assisted and no document says so anywhere),
   funding, and competing interests. This was raised with the author on
   2026-08-04 with a drafted one-sentence disclosure for the existing "Data and
   code availability" section; **the author's decision was not to pursue it**
   ("don't worry about it, it doesn't matter"). Recorded as decided, not
   pending — do not silently reopen it. Worth one line at submission time only
   because AMIA and ICMJE ask for the disclosure in the manuscript and a venue
   discovering it after acceptance treats it as an integrity matter rather than
   a formatting one. If the author revisits it, the draft text is in the
   2026-08-04 session log (§9).
   `test_papers_mark_missing_information` requires `[TODO` to remain present in
   both papers, so it will fail once the last one is filled — that is the guard
   against submitting an incomplete paper, and it should be **deleted, not
   weakened**, when the papers are genuinely complete.
2. **Four round-17 findings need pipeline runs and are NOT fixed.** The prose
   corrections landed; these did not, and each is a live reviewer objection:
   - ~~**No interval on either headline in-regime rate.**~~ **DONE r23** —
     `statistics.pair_cluster_proportion_ci` resamples drugs and keeps pairs
     whose both endpoints survive; `regime` emits it for both nulls on both
     pools. This was the oldest open finding in the project.
   - **(remaining)** `regime.high_marginal_
     pool.at_positive_control_strength` stores bare point estimates. Methods
     promise a cluster bootstrap over drugs for pair-aggregated quantities and
     it is not applied here — on the two numbers carrying Paper A's claim, over
     2,345 pairs drawn from 1,577 drugs. This is what makes r17's C1 provable;
     ship the interval.
   - **The purpose-built pool inherits a weaker form of the defect it fixes.**
     `regime.py:207` excludes both-implicated pairs — the configuration all 16
     positive controls have — so the pool matches on marginal strength but not
     on implication status. The exclusion also removes the pairs most likely to
     fire, pushing the measured rate **down**, which contradicts the "every rate
     is an upper bound" framing. Re-run with the exclusion disabled and report
     both. Stated in Paper A §7 as of r17; not measured.
   - **Paper B's strength-matched expectation is one number in disguise.**
     17,375 × 7.06% (top-quintile rate) = 1,227 against the reported 1,212 —
     98.8%. Every band's median strength (2.85/4.16/5.32/8.15) sits inside the
     top quintile's 2.80–8.95, and the rate is non-monotone there
     (8.71% → 7.06%). Disclosed in prose as of r17; the honest fix is to
     recompute the expectation on the purpose-built pool, which measures the
     high-strength rate directly instead of extrapolating to it.
   - **Shipped tables cannot reproduce two headline analyses.** `rr_a`/`rr_b`
     appear only in `tier_b_pairs.csv`, so Paper A Table 2's correlations and
     Paper B §4.4's stratification cannot be recomputed without the 159 GB
     database, and the 19,826-pair pool ships nowhere. Add the columns; export
     the pool.

   Also unfixed and prose-only: Paper A argues its mechanistic claim by
   comparing significance rather than testing the difference (Gelman–Stern). The
   correct test — Steiger for dependent overlapping correlations — **supports**
   it (*z* ≈ −4.2 to −4.8, *p* < 10⁻⁴, from an approximate reconstruction), so
   compute it in the pipeline and report it. It converts an objection into a
   strength.

3. **AMIA's numeric page limit is unverified — deprioritised by the author.**
   Their call states the limit *includes* references; the 8-page cap here
   excludes them. Paper A is 9 total pages, Paper B is now 9 too (it gained a
   page in r17). Offered three times on 2026-08-04 and declined ("doesn't
   matter"), so it is **not** an open task — but it is the item most likely to
   force real work late, because if the limit is 8 inclusive then both papers
   are over by a page and both are at **zero body-page slack**: any addition
   now requires a compensating cut elsewhere. r17 spent four build cycles
   learning that. Check the live CFP before final formatting.
4. **Resource-gated, not effort-gated:** a curated severity-graded DDI reference
   (DrugBank licence) — the single largest limitation; a second human PT curator;
   pair-level VigiBase (UMC research agreement); a valid negative case for the
   conditional claim (needs an event with weak marginals *and* documented
   interacting pairs — looked for, not found).

### Venue

Pharmacovigilance has almost no full-paper conferences — ICPE, ISoP and OHDSI
are abstract-driven, and the archival venue is journals. The realistic
full-paper targets are **AMIA Annual Symposium** (best fit), AMIA Informatics
Summit, and MEDINFO. Journals: *Drug Safety* (Paper A), *Pharmacoepidemiology
and Drug Safety* (Paper B), or JAMIA. Recommended: submit both to AMIA,
preprint the manuscript on medRxiv, and send an ICPE/ISoP abstract regardless.

---

## 8. How to work on this

- The user drives with short directives ("fix all 5", "do what you think is
  best"). They want the work done, not options enumerated.
- **Verify, don't assert.** Every review round that found something real found
  it by running a query against the shipped pipeline, not by reading the prose.
- **Report findings that go against the work.** This project's credibility rests
  on having published its own corrections; round 11's rewrite came from an
  experiment that overturned the central claim, and that is stated in the papers.
- When a review is requested, the useful output is *new* findings, not a
  restatement of the template. Check what has not been checked.
- Say plainly when something is not done. The answer to "are the papers done?"
  has been "no" more often than "yes", and the honest version has been useful.

- **The tests cannot catch a wrong reading of a right number.** Every r17 finding
  but one was invisible to 330 passing tests, because the tests assert that
  stated numbers match computed ones. In r17's central case the pipeline computed
  2.2%, the prose reported 2.2%, the test verified 2.2%, and the sentence built
  on it said the opposite of what 2.2% means. When a number is quoted *as
  evidence for a claim*, check the inference, not just the digits.

**Assessment as of r17 (2026-08-04):** four findings remain unfixed, all needing
pipeline runs (§7.2), and one of them — no interval on the headline in-regime
rates — is what made r17's central correction provable in the first place.

The pattern to take seriously: rounds 9, 10, 11, 12 and now 17 each changed what
the papers say, and r17 overturned a title-level claim that had survived six
rounds *and* found a round-11 withdrawal still live in `manuscript.md`'s
abstract. Five rounds in a row is not the signature of convergence. Treat "no
known defects" as exactly that — not as "correct" — and assume the next round
finds something too.

---

## 9. Session log — 2026-08-17 (rounds 28–30): the novelty push

The author asked for the paper to be "more novel", clarified as *change the
methods*, not the framing. Recorded in full because two of its lessons are
about how this project can go wrong in a new way.

### 9.0 What was asked, and the line drawn

"Restructure so we have positive findings" is legitimate if it means surfacing
contributions buried under negative framing, and misconduct if it means
manufacturing them. The work done was the first: **no number changed, no
limitation was removed** (Limitations is still ~1,300 words and still carries
the fourth-arm failure, the invalid anaphylaxis arm, the bracketed 12–86%
sensitivity and the post-hoc disclosure). What changed is which sentences lead.

### 9.1 Four candidate novelties; one survived

| idea | outcome |
|---|---|
| **Conjunction of both nulls** | **Refuted.** Byte-identical to the multiplicative null alone (4/16, 2.22%) — which is what nesting predicts |
| **Nesting is a new result** | **Published already.** Jung & Jung, *PLOS ONE* 2024, state it. Corrected, cited as reference 13 |
| **OATP1B1 mechanism for abiraterone + rosuvastatin** | **Dropped.** The cached label documents CYP2D6/CYP2C8 only; rosuvastatin is not a CYP2C8 substrate. This was model recall, not evidence |
| **Strength-varying threshold** | **Works as designed, fails at the objective.** Flattens FPR spread 0.080→0.032 over 200 held-out halves; halves recovery 11.0→5.5/16 |

**Check novelty against the literature before claiming it.** The nesting claim
was written into the abstract, introduction, §4.2 and the conclusion as
contribution #1 before it was checked. It took one search to find it published.

### 9.2 What survived, and is in the paper

- **The nesting *condition*.** Jung & Jung state the implication
  unconditionally. It requires both marginals on the same side of unity, since
  the expectations differ by (RR_A−1)(RR_B−1). Verified: 163 of 16,138
  negative controls violate the unconditional form, **0** of the 6,163 with
  both marginals above 1. Remaining failures are both-*protective* pairs, where
  the floor at max(p_A,p_B) in E_add binds.
- **An operating characteristic** (§4.5). Recovering 12/16 known interactions
  costs ~7.5% in-regime FPR — three times nominal. The additive advantage is
  −1 to +2 pairs across eight operating points.
- **A third estimand** (§4.7), `omega.within_victim_excess`: anchor on each
  drug's own partner distribution, no global expectation. Recovers 15/15 at 15%
  FPR (additive 14, multiplicative 12) and is worst of the three at 2.5%.
  **No estimand dominates** — three principles, one conclusion.
- **`audit.top_ranked_pairs`**: the screen's top-5 with the §4.10 proxy test.
  The top three carry their own signal (8.4/16.7/19.5% third-drug) against
  64.7% and 100% for the two proxies below them.

### 9.3 The defect this session created

Inserting three sections into §4 without renumbering produced **two §4.2, two
§4.4 and two §4.5**. Every reference to those numbers then pointed at two
sections at once, and the round-28 existence guard passed throughout — the
numbers resolved, just not uniquely. Same defect as round 20's duplicate
tables, different medium.

Fixed by renumbering §4.1–4.14, remapping pre-existing references **by rule**
and the three new sections' references **by intent** (they were written against
the old numbering). `test_section_numbers_are_unique_and_sequential` now
requires uniqueness *and* no gaps.

### 9.4 State

- **346 tests**, build clean, manuscript **39 pages**, tree clean, pushed.
- Blocking submission: **authors/affiliations**. Nothing else.
- Unverifiable list is down to determinism and the two external benchmarks
  (AEOLUS, DiAna) — all inherently outside the artefact.

### 9.5 The honest read

Four novelty attempts, one survivor and one refinement. That ratio is the
signal: there is little undiscovered novelty left in this dataset. The
remaining headroom is access-limited, not analysis-limited — a severity-graded
reference to replace the label proxy, or pair-level VigiBase to test whether
any of this replicates outside FAERS.

**Do not attempt to raise novelty by rewriting.** It was tried, it produced a
false claim within one turn, and a literature check caught it. The paper's
contribution is a methodological warning plus the numbers to act on it, and
that is what it should be sold as.

---

## 9A. Session log — 2026-08-04

The session that took this project from "no version control at all" to r17.
Recorded because several of its decisions are not recoverable from the diff, and
because two of them were the author's calls rather than defaults.

### 9.1 Version control, from nothing

The project had **no commits**. `git rev-parse --show-toplevel` resolved to
`/Users/ravik` — the home directory is itself a `git init` with no commits, so
committing "here" would have staged `~/.ssh`, `~/.claude.json` (holds an OAuth
token), `~/.zsh_history` and the 159 GB `data/` tree. A project-local repo was
created instead. **The home-directory repo still exists and was deliberately not
touched** — deleting it is destructive and needs the author's say-so. Any other
project folder under `~/Desktop/` is probably in the same position.

Sequence, for anyone reconstructing the history:

1. Project-local `git init`; 900 files / 17 MB staged; scanned for credentials
   (the only hits were the word "SECRETIONS" in FDA label text).
2. First commit, pushed to a **private** repo.
3. Author confirmed the account: `gh auth status` displays **FieryKnight2010**
   but `gh api user` returns **edanmn** — a username change, old label cached in
   the keyring. `edanmn` is correct.
4. Author asked for public. Before flipping: the third-party seed PDF
   (`Using FAERS for Drug Interaction Research.pdf`) was untracked and
   gitignored — it is someone else's instructional handout, nothing in the
   pipeline reads it, and redistributing it publicly is a different matter from
   keeping it privately. It was already in commit 1, so history was rebuilt as a
   single clean commit and force-pushed rather than left reachable.
5. Repo made public.

**Residual, disclosed to the author:** GitHub retains unreachable objects for a
period, so the force-replaced commits may persist by SHA. Reaching them requires
the exact 40-character hash, which was never shared. Airtight would be
delete-and-recreate; the token lacks `delete_repo` scope. Also public now: the
commit email `rishik.kondadadi@gmail.com`, and `CLAUDE.md` plus the 17
`PHASE*_FINDINGS.md` files — the candid internal review record. Both were
flagged; neither was changed.

### 9.2 Decisions the author made

- **DOI: no Zenodo.** The bare GitHub URL goes in all three documents. Applied
  to `paper_a`, `paper_b`, and to `manuscript.md`, which had said "in this
  repository" — meaningless to someone reading the preprint on medRxiv.
- **No Acknowledgements section** in either conference paper. See §7.1.
- **Generative-AI disclosure: not pursued.** See §7.1. The drafted sentence, if
  it is ever wanted: *"Analysis code, internal review, and portions of the
  manuscript text were developed with assistance from a large language model
  (Anthropic Claude); the author specified the study design and every analysis,
  verified all reported quantities against the deterministic pipeline output,
  and takes responsibility for the content."* It needs the author's confirmation
  that it describes what actually happened before it goes in — it is a factual
  claim about their process, not a boilerplate.
- **AMIA page limit: deprioritised.** See §7.3.
- **Authors/affiliations:** the author will supply them. This is the last
  `[TODO]` in each paper and the only hard blocker on submission.

### 9.3 What r17 actually was

A full adversarial review, requested in the register of a top-tier reviewer, run
**against the shipped pipeline rather than the prose** — which is the only
method that has ever found anything here. Full write-up in
`results/PHASE17_FINDINGS.md`; the corrections are in §6 and the unfixed
remainder in §7.2.

The single most useful thing it did was recompute a number the papers already
quoted correctly, and check what that number *meant*. 2.2% against a nominal
2.5% is not a miscalibration; it is calibration. The paper asserted the opposite
in its title-level claim while conceding the truth in its Discussion, and 329
tests passed throughout because every one of them verified digits rather than
inferences.

Reviewer-template note for next time: the request arrived as a generic ML-paper
checklist (baselines, ablations, train/test splits, BLEU). Most of it does not
apply to a disproportionality study on spontaneous reports. Mapping the parts
that transfer — leakage, circularity, calibration, multiplicity, reproducibility
— and saying plainly which headings are category errors was more useful than
filling them in. Do not invent an ablation to satisfy a heading.

### 9.4 State at pause

- `main` at the r17 commit, pushed, working tree clean.
- **330 tests pass**; `paper/build.py --check` clean; all three PDFs current.
- `manuscript` 31 pages and the only maintained document as of r18; the two
  conference papers are archived. No page cap is enforced anywhere now.
- Pipeline was **not** re-run this session — no analysis number changed, only
  prose, guards and documentation. `canonical_numbers.json` is untouched since
  the last full run.

### 9.5 Round 18 — merged back into one document

The author's call: *"combine them back into one paper."* The combined paper
already existed — `manuscript.md` is what the two conference papers were split
*out of* — so the work was consolidation rather than writing.

Done in the order that matters:

1. **Ported first, retired second.** Five r17 corrections had landed in
   `paper_a`/`paper_b` and nowhere else. Retiring first would have dropped them
   silently, which is the round-16 failure exactly.
2. **Guards rescoped, never deleted.** All 18 tests bound to the conference
   papers were repointed at the manuscript. **Six failed**, and every failure
   was a real gap: the vocabulary-hygiene disclosure (719 placeholder pairs,
   0.766→0.752) existed only in `paper_b`; the three-annotations structure, the
   negative-control exclusion consequence, the 1.4%-proxy disavowal and the
   "was incorrect" correction were all missing; and one was a genuine bug —
   the manuscript compared **12/14 powered against 4/16**, mixing denominators
   in a single comparison, which is the precise defect that guard was written
   for in round 10. All fixed by adding to the manuscript.
3. **Two guards adjusted rather than the prose**, both narrowings that lose
   nothing: a bare `"essentially identical"` substring that was also matching an
   innocent sentence about hospitalisation strata (the full withdrawn phrase is
   in the registry), and a control-table check that pinned `paper_a`'s
   `"55/349"` notation rather than the invariant, which is that a count and its
   denominator appear on the same row.
4. **`test_retired_documents_are_not_built_and_are_labelled` generalised.** It
   was named for documents plural and hardcoded to `paper.md`, so it would have
   passed while the newly retired pair rotted in the build directory. It now
   iterates a `RETIRED` registry and also catches stale `.tex`/`.pdf`.
   Mutation-tested twice.

**Consequence to remember: no page cap is enforced anywhere now.** The
manuscript declares a cap of `None`. The zero-slack problem is gone, and so is
the guard that made it visible. A conference submission would be a fresh
derivation from the manuscript, not a revival of the archive.

### 9.6 Where to pick up

In order:

1. Nothing, until the author supplies authors/affiliations — now a single
   `[TODO]` in `manuscript.md` — or start §7.2, which is independent of them.
2. §7.2's four pipeline items. The interval on the in-regime rates is first:
   it is the evidence for r17's central correction, it is currently absent, and
   a reviewer who recomputes it will reach the same conclusion r17 did.
3. Assume r18 finds something. Five consecutive rounds have.
