# Phase 1 / 1a findings — acquisition and schema audit

> **Phase-time record.** The figures below were correct when this phase ran.
> Later phases changed the pipeline (a polypharmacy cap, a floor on the additive
> expectation, a denominator fix), so where these numbers differ from
> `results/canonical_numbers.json` the canonical file is authoritative and the
> difference is itself part of the record. Only `run_analysis.py` writes it.

Audit of the FAERS/LAERS quarterly archives, 2004Q1–2026Q2. Every statement
below is derived from reading the actual archives, not from FDA documentation.

Generated tables: `column_audit_long.csv`, `column_presence_matrix.csv`,
`schema_changepoints.csv`, `audit_vs_config.csv`, `archive_members.csv`,
`download_manifest.csv`.

---

## 1. Window and file naming

| | |
|---|---|
| First quarter published | 2004Q1 (2003Q4 returns an error) |
| Last quarter published | 2026Q2 |
| Total | 90 quarters |
| `aers_ascii_*` (LAERS) | 2004Q1–2012Q3, 35 quarters |
| `faers_ascii_*` (FAERS) | 2012Q4–2026Q2, 55 quarters |

The prefix boundary was established by probing both spellings at the transition:
`aers_ascii_2012q3` and `faers_ascii_2012q4` exist; the opposite pairing does
not. Nonexistent quarters return HTTP 500 with an HTML body, not a 404, so
status code alone is not a validity check — the downloader verifies the zip
central directory instead.

**Acquired:** 90/90 archives, 3.55 GB compressed, 20.04 GB uncompressed across
the seven tables. All 90 sha256 digests are distinct. Per-table uncompressed
totals, which set the Phase 2 parse budget:

| table | GB | | table | GB |
|---|---|---|---|---|
| drug | 9.00 | | ther | 1.30 |
| demo | 3.44 | | outc | 0.39 |
| indi | 2.92 | | rpsr | 0.05 |
| reac | 2.92 | | stat | 0.00 |

### A client-side bug that looked exactly like server throttling

Downloads stalled indefinitely partway through, while `curl` fetched the same
byte ranges in ~2 s. The cause was `Accept-Encoding: gzip, deflate`, which
`requests` sends by default: asked to content-encode a zip, the FDA host hangs
mid-response instead of declining. Forcing `Accept-Encoding: identity` fixed it
outright — archives that had been stalled for hours completed in 2–4 s.

Worth recording because the symptom is indistinguishable from rate limiting, and
the wrong diagnosis (back off, reduce concurrency, wait) makes it worse rather
than better. Requesting gzip on an already-compressed archive gains nothing and
also muddies `Content-Length` and range semantics.

### One stray file

`2026Q1` ships `ASCII/Thumbs.db`, a Windows Explorer thumbnail cache. Harmless,
but it confirms the archives are assembled by hand and that member lists should
be classified rather than assumed.

## 2. Schema changepoints

21 changepoints across the 7 tables. The era model in the plan is broadly right,
but three findings would have corrupted results silently.

### 2.1 A UTF-8 BOM on one column of one table in one quarter

`DRUG12Q4.txt` begins `\xef\xbb\xbfprimaryid$caseid$...`. `DEMO12Q4.txt` does
not, and `DRUG13Q1.txt` does not. Parsed naively the column is named
`﻿primaryid`, so **every drug-to-demographics join for 2012Q4 matches zero
rows** — with no error raised. Handled by `harmonization.strip_bom`.

### 2.2 2012Q4 spells three columns differently from both neighbours

| column | 2012Q3 | 2012Q4 | 2013Q1 |
|---|---|---|---|
| outcome code | `outc_cod` | `outc_code` | `outc_cod` |
| lot number | `lot_num` | `lot_nbr` | `lot_num` |
| initial/follow-up | `i_f_cod` | `i_f_code` | `i_f_code` |

2012Q4 is the LAERS→FAERS transition quarter and evidently was not produced by
the same tooling as either side. Two of the three anomalies revert at 2013Q1;
`i_f_code` persists.

### 2.3 Everything else matches the expected era model

- **2012Q4**: `isr` → `primaryid`/`caseid`/`caseversion`; `occr_country` and
  `init_fda_dt` appear; `case`, `confid`, `death_dt`, `foll_seq`, `image` drop.
- **2014Q3**: `prod_ai` appears in DRUG; `gndr_cod` → `sex`; `age_grp`,
  `auth_num`, `lit_ref` appear in DEMO; `drug_rec_act` appears in REAC.
- **Legacy era is stable**: exactly one change in 35 quarters —
  `reporter_country` added to DEMO at **2005Q3**.
- **Modern era is stable from 2014Q3 onward**: no changepoints after it.
- `audit_vs_config.csv` is empty: the era model's identity columns, sex column,
  and `prod_ai` boundary all hold everywhere.

### 2.4 A legacy-only table

`STAT` exists 2004Q1–2012Q3 with an empty header line. Unused by this study;
listed in `harmonization.ignore_tables` so its absence is a decision on the
record rather than an oversight.

## 3. Deleted-case lists — five naming conventions, complete coverage

Deleted-case lists ship with **every quarter from 2019Q1 to 2026Q2** — 30
quarters, no gaps — under five different naming conventions:

| quarters | path convention |
|---|---|
| 2019Q1–2019Q4 | `deleted/ADR19QnDeletedCases.txt` |
| 2020Q1 | `DELETED/ADR20Q1DeletedCases.txt` |
| 2020Q2–2020Q3 | `Deleted/ADR20QnDeletedCases.txt` |
| 2020Q4–2021Q3 | `Deleted/nnQnDeletedCases.txt` (`ADR` prefix dropped) |
| 2021Q4–2026Q2 | `Deleted/DELETEnnQn.txt` (**no `deleted` in the basename**) |

**2019Q1 also ships `deleted/AllDeletedCases.txt`, a cumulative list of 83,845
case ids** covering everything deleted before that point. Combined with the
per-quarter files (2,856–7,984 cases each), coverage over the full study window
is complete. No era needs a stated exemption. Format is one case id per line,
after a single leading blank line that must be skipped.

### A near-miss worth recording

The first pass of this audit reported lists for only 11 quarters, and Phase 3
was about to carry a limitation stating that 19 quarters of deletions — in the
highest-volume era — could not be purged. That was wrong, and the cause was in
the audit rather than the data: `classify_member` tested the *basename* for the
substring `deleted`, so `Deleted/DELETE22Q1.txt` matched neither the deletion
rule nor any table rule and fell through to "documentation".

Two lessons carried into later stages. First, a classifier that silently routes
unmatched input to a benign default will manufacture exactly this kind of
finding; the catch here came from re-checking the raw member list against a
looser pattern rather than trusting the classified output. Second, an
inconvenient result about the *data* deserves the same scrutiny as a convenient
one — the coverage gap was plausible enough to have been written up as a
methodological limitation of FAERS itself.

## 4. Consequences for later phases

1. **Phase 2 parser** must be driven by observed headers with the harmonization
   map applied — BOM stripped, the four renames, identity columns mapped to
   era-neutral names. Positional parsing against a hardcoded layout is unsafe.
2. **`era` must be carried on every row.** Legacy `case` and modern `caseid` are
   distinct ID spaces until the Phase 3 bridge is empirically verified; merging
   them at parse time would foreclose that check.
3. **Phase 3 attrition table** must report deleted-case removal separately for
   the covered and uncovered spans rather than as one number.
