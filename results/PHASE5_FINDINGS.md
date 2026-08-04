# Phase 5 findings — event definition

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

**23 curated PTs across 10 concepts**, all verified present in the data.

| tier | cases | share of 20,293,421 |
|---|---:|---:|
| core | 42,058 | 0.207% |
| broad | 339,063 | 1.671% |

By era — core: laers 13,122 · faers_early 3,058 · faers_modern 25,878.

## The prediction, and what the search actually found

Phase 4 closed with a prediction: the seed list would match a substantial share
of rhabdomyolysis reports, but historical variants would be missing — and *if
fuzzy matching surfaced nothing beyond the seed terms, the search was too narrow
rather than the list complete*.

The search surfaced a great deal, including one outright error.

### The seed list contained a term that matches nothing

It listed **"Toxic myopathy"**. The actual FAERS term is **`MYOPATHY TOXIC`** —
573 reports across 85 quarters. Written from memory rather than from the
vocabulary, the seed entry would have contributed exactly zero reports while
appearing to cover the concept. `verify_terms_exist` now fails the run on any
curated PT absent from the data.

### Two MedDRA renames, both clean instantaneous switches

| concept | retired term | successor | switch |
|---|---|---|---|
| CK increased | `BLOOD CREATINE PHOSPHOKINASE INCREASED` 308 → **0** | `CREATINE KINASE INCREASED` **0** → 404 | 2026q1→q2 |
| CK abnormal | `BLOOD CREATINE PHOSPHOKINASE ABNORMAL` 10 → **0** | `CREATINE KINASE ABNORMAL` **0** → 16 | 2026q1→q2 |
| immune myopathy | `IMMUNE-MEDIATED NECROTISING MYOPATHY` 45 → **0** | `IMMUNE-MEDIATED MYOSITIS` **0** → 49 | 2019q3→q4 |

The 2026q2 switch is part of a mass renaming: **1,907 PT strings make their last
appearance in 2026q1** and 335 appear for the first time in 2026q2. A term list
written from the current MedDRA release would have lost the entire final quarter
of CK data without any error.

### Terms the seed list missed entirely

- `MYOGLOBIN BLOOD INCREASED` — **1,436 reports**, twelve times larger than the
  `MYOGLOBINAEMIA` the seed list did contain, and the same concept
- `MYOGLOBIN URINE PRESENT` (221), `MYOGLOBIN URINE` (33),
  `MYOGLOBIN BLOOD PRESENT` (25)
- `EXERTIONAL RHABDOMYOLYSIS` (30, introduced 2024q2)
- `BLOOD CREATINE PHOSPHOKINASE MM INCREASED` — the skeletal-muscle isoenzyme

## Not every rename preserves meaning

CPK → CK is a pure relabel: same concept, comparable volume across the boundary.

The immune myopathy rename is **not**. The successor carries roughly *five times*
the per-quarter volume of the term it replaced (~92/quarter vs ~19/quarter),
so the concept widened — most likely absorbing checkpoint-inhibitor myositis.
Grouping the two therefore injects a step change at 2019q4.

Both are kept in **broad** and out of **core** for that reason. Core is the
primary analysis and must be stable across the full window; a concept whose
definition widens mid-series does not belong in it. This matters directly for
the era-stratified analysis, which is built to read a signal present in one era
but not another as evidence of reporting artefact.

## The continuity check was vacuous, and the fix is demonstrated

The check flags a concept whose quarterly series drops to zero and stays there
while the preceding year averaged a healthy volume. On first run it reported
**0 breaks out of 23 PTs even ungrouped** — where the CPK term visibly dies at
2026q1.

The bug: it scanned only between each concept's own first and last non-zero
quarter. A term retired at the **end** of the window therefore fell outside its
own scan range and passed trivially. That is precisely the case that matters
most, since the most recent data is what a study most wants to trust, and it is
the case that actually occurred.

Scanning to the end of the study window instead:

| | PTs/concepts flagged BREAK |
|---|---|
| ungrouped, each PT its own concept | **3 of 23** — at 2026q2, 2026q2, 2019q4 |
| grouped into concepts | **0 of 10** |

The check now detects exactly the three renamed terms at exactly the right
quarters, and the concept grouping repairs all three. That contrast is the
evidence the grouping works; without it the PASS would have meant nothing.

## Tier composition

**core** — muscle destruction, specific enough to be hard to report for another
reason: `rhabdomyolysis`, `myoglobin_release`, `muscle_necrosis`.

**broad** — adds `myopathy`, `myositis`, `muscle_disorder`, `muscle_symptom`,
`ck_increased`, `ck_abnormal`, `immune_myopathy`. Far more powerful and far more
confounded: `MYALGIA` alone contributes 163,419 reports and is reported against
almost everything. Sensitivity analysis only.

**Excluded**, with reasons: cardiac (`CARDIOMYOPATHY` and variants, 14,437+),
idiopathic inflammatory myopathies (`DERMATOMYOSITIS`, `POLYMYOSITIS`),
genetic (`MITOCHONDRIAL MYOPATHY`, `MUSCULAR DYSTROPHY`), infectious
(`PYOMYOSITIS`, `VIRAL MYOSITIS`), mechanical and non-specific (`MUSCLE SPASMS`
at 177,779 reports, `MUSCULOSKELETAL PAIN`), distinct entities
(`INCLUSION BODY MYOSITIS`, `ORBITAL MYOSITIS`, `MYOSITIS OSSIFICANS`), and
`BLOOD CREATINE PHOSPHOKINASE DECREASED` as the wrong direction.

## Limitations

- **PT-level only.** MedDRA's hierarchy and Standardised MedDRA Queries require a
  licence, so the case definition is a hand-curated PT list rather than an SMQ.
  It is reproducible and fully documented in `config/pt_sets/rhabdomyolysis.csv`
  with a provenance note per term, but it is not the standard instrument.
- **The 2026q2 renaming affects far more than this concept area.** 1,907 retired
  strings is a vocabulary-wide event. Any future extension to a second adverse
  event must repeat this curation; the concept grouping here is specific to
  myotoxicity.
- **Core excludes immune-mediated myopathy**, which is a genuine and
  statin-associated form of muscle injury. That is a deliberate trade of
  sensitivity for temporal stability, and the broad tier recovers it.
