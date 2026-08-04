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
a validated pipeline plus two conference papers.

**The deliverables are three documents** (§4). **The research is finished** —
the analysis is not expected to change. What remains is clerical (§7).

### Headline results (all from `results/canonical_numbers.json`)

| | value |
|---|---|
| Analysis population | 20,274,416 cases, 41,889 myotoxicity events (0.207%) |
| Tier A recovery, threshold Ω₀₂₅ > 0 | additive **12/16**, multiplicative **4/16** |
| Tier A interval (cluster bootstrap on victim drug) | **50–100%** (naive binomial 62–97% is too narrow) |
| Tier B calibrated threshold | **+0.436**, held-out FPR 5.03% (4.37–5.74%) |
| Pooled FPR at Ω₀₂₅ > 0 | additive 6.67%, multiplicative 6.44% |
| **In-regime FPR** (2,345 strongly-associated non-interacting pairs) | **additive 9.3%, multiplicative 2.2%** (nominal 2.5%) — see r17: only the additive figure is a miscalibration |
| **Recovery gap at matched in-regime FPR** | **1–2 pairs** (8 at the conventional threshold) |
| Torsade in-regime additive FPR | **42.8%** — the 9/10-vs-0/10 result is an operating-point artefact |
| Screen | 1,022 of 17,375 signalled; **1,212** expected by chance strength-matched (872 pooled) |
| Enrichment, control drugs removed | **1.12× (0.69–1.81)** — indistinguishable from unity |

### The two papers' claims, as they now stand

- **Paper A (calibration).** Neither null is usable at its conventional
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
- **Paper B (evaluation).** A DDI screen shows no enrichment for genuine
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
python -m pytest                              # 330 tests
python paper/build.py                         # all three documents -> .tex -> .pdf
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
(330 tests) asserts the prose against it.

`paper/build.py` generates `.tex` from `.md` via pandoc + tectonic. **Never edit
a `.tex` by hand** — it is regenerated. Two-column documents declare a body-page
cap; the builder reads the references label's page from the `.aux` and **exits
non-zero if the body exceeds it**.

---

## 4. The three maintained documents

| file | what | size |
|---|---|---|
| `paper/manuscript.md` | full-detail version / preprint | 30 pages |
| `paper/paper_a.md` | **calibration** — error rates in the drug-dominant regime | 8 body pages (cap 8) — **zero slack** |
| `paper/paper_b.md` | **evaluation** — annotation independence, reference coverage | 8 body pages (cap 8) — **zero slack** since r17 |

`paper/archive/paper.md` is **retired** — a pre-split restructuring, superseded,
carries a banner saying so, excluded from the build. Do not revive it.

Paper B cites Paper A as a companion but no longer depends on it for its
foundation (it carries the specification grid itself). **Submit A first.**

---

## 5. Read this before writing any test

This project has been through **seventeen adversarial review rounds**. The
consistent failure has not been in the analysis — it has been in the guards.
**Five times a test written to catch a specific defect was too weak to catch
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
   defeated by a **synonym**.

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

**330 passing means the stated numbers match the computed ones. It does not mean
the right quantity was computed, nor that the sentence built on a correct
number says what the number means** (r17). Round 11 overturned the central claim while
every test passed, before and after.

---

## 6. Corrections already made — do not reintroduce

Detail in `results/PHASE*_FINDINGS.md` (16 files). The ones that bite:

| claim | status |
|---|---|
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

1. **Two `[TODO]` blocks** in the two conference papers — authors/affiliations,
   one each. `manuscript.md` has none. The availability TODO is closed: all
   three documents cite <https://github.com/edanmn/faers-ddi-rhabdomyolysis>.
   The Acknowledgements sections were **removed by author decision**, not left
   unfinished — do not reinstate them. Their removal leaves three statements
   with no home, all of which most venues expect: **generative-AI disclosure**
   (this project's code, prose and internal review rounds were LLM-assisted and
   no document says so anywhere), funding, and competing interests. The natural
   home for all three is the existing "Data and code availability" section or
   Methods. Unresolved, and the AI disclosure is the one with real
   consequences if a venue asks after acceptance.
   `test_papers_mark_missing_information` requires `[TODO` to remain present in
   both papers, so it will fail once the last one is filled — that is the guard
   against submitting an incomplete paper, and it should be **deleted, not
   weakened**, when the papers are genuinely complete.
2. **Four round-17 findings need pipeline runs and are NOT fixed.** The prose
   corrections landed; these did not, and each is a live reviewer objection:
   - **No interval on either headline in-regime rate.** `regime.high_marginal_
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

3. **AMIA's numeric page limit is unverified.** Their call states the limit
   *includes* references; the 8-page cap here excludes them. Paper A is 9 total
   pages, Paper B is now 9 too (it gained a page in r17). Both papers are at
   **zero body-page slack** — any addition now requires a compensating cut, and
   r17 spent four build cycles discovering this. Check the live CFP before final
   formatting.
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
