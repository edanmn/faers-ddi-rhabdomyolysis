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
| **In-regime FPR** (2,345 strongly-associated non-interacting pairs) | **additive 9.3%, multiplicative 2.2%** (nominal 2.5%) |
| **Recovery gap at matched in-regime FPR** | **1–2 pairs** (8 at the conventional threshold) |
| Torsade in-regime additive FPR | **42.8%** — the 9/10-vs-0/10 result is an operating-point artefact |
| Screen | 1,022 of 17,375 signalled; **1,212** expected by chance strength-matched (872 pooled) |
| Enrichment, control drugs removed | **1.12× (0.69–1.81)** — indistinguishable from unity |

### The two papers' claims, as they now stand

- **Paper A (calibration).** *Both* nulls are severely miscalibrated at their
  conventional operating point for drug-dominant events. The additive null's
  apparent superiority is mostly an operating-point effect: 8 pairs → 1–2 at
  matched error rates, and **zero** on the torsade replication. What survives is
  mechanistic — observed joint risk is flat in marginal strength (*r* = +0.12)
  while both nulls predict it to rise steeply (*r* ≈ +0.94).
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
python -m pytest                              # 329 tests
python paper/build.py                         # all three documents -> .tex -> .pdf
python paper/build.py --check                 # non-zero if any .tex is stale
```

A `stages` key in the canonical file records which ran;
`test_all_pipeline_stages_have_run` fails on a partial pipeline. Full chain is
roughly 40 minutes. `regime` and `audit` are the slow ones.

**Determinism is real and verified** — two full runs produce byte-identical
output. Every stochastic step is seeded.

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
(329 tests) asserts the prose against it.

`paper/build.py` generates `.tex` from `.md` via pandoc + tectonic. **Never edit
a `.tex` by hand** — it is regenerated. Two-column documents declare a body-page
cap; the builder reads the references label's page from the `.aux` and **exits
non-zero if the body exceeds it**.

---

## 4. The three maintained documents

| file | what | size |
|---|---|---|
| `paper/manuscript.md` | full-detail version / preprint | 30 pages |
| `paper/paper_a.md` | **calibration** — error rates in the drug-dominant regime | 8 body pages (cap 8) |
| `paper/paper_b.md` | **evaluation** — annotation independence, reference coverage | 7 body pages (cap 8) |

`paper/archive/paper.md` is **retired** — a pre-split restructuring, superseded,
carries a banner saying so, excluded from the build. Do not revive it.

Paper B cites Paper A as a companion but no longer depends on it for its
foundation (it carries the specification grid itself). **Submit A first.**

---

## 5. Read this before writing any test

This project has been through **twelve adversarial review rounds**. The
consistent failure has not been in the analysis — it has been in the guards.
**Four times a test written to catch a specific defect was too weak to catch
it:**

1. a `6/16` check satisfied by the substring inside `16/16`;
2. a guard requiring only the phrase `"companion paper"`, which passed while the
   document made the unqualified claim it was meant to prevent;
3. guards scoped to whichever document was open, so a correction landed in two
   of four documents and the suite stayed green;
4. a withdrawn-phrase check defeated by a **line break** in the prose.

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

**329 passing means the stated numbers match the computed ones. It does not mean
the right quantity was computed.** Round 11 overturned the central claim while
every test passed, before and after.

---

## 6. Corrections already made — do not reintroduce

Detail in `results/PHASE*_FINDINGS.md` (16 files). The ones that bite:

| claim | status |
|---|---|
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

1. **Six `[TODO]` blocks** in the two conference papers — authors, affiliations,
   funding, repository DOI. `manuscript.md` has none.
2. **AMIA's numeric page limit is unverified.** Their call states the limit
   *includes* references; the 8-page cap here excludes them. Paper A is 9 total
   pages, Paper B 8. Check the live CFP before final formatting.
3. **Resource-gated, not effort-gated:** a curated severity-graded DDI reference
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

**Assessment as of the last session:** no known unfixed defect. But rounds 9–12
each found something that changed what the papers say, and round 11 was the most
consequential of all. That is not the signature of convergence. Treat "no known
defects" as exactly that — not as "correct."
