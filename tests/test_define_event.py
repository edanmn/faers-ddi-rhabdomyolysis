"""Tests for the event definition and its MedDRA-drift safeguards.

Two safeguards carry the weight:

  verify_terms_exist    every curated PT must occur in the data. The seed list
                        contained "Toxic myopathy"; the real FAERS term is
                        MYOPATHY TOXIC, so that entry would have matched nothing
                        and silently contributed zero reports.

  continuity_report     a concept whose quarterly series drops to zero and stays
                        there is a vocabulary artefact, not a finding. The first
                        version of this check scanned only between a concept's
                        own first and last non-zero quarter, which made it
                        vacuous for a term retired at the END of the window --
                        the case that matters most, and the one that actually
                        occurred at 2026q2.
"""

from __future__ import annotations

import csv

import duckdb
import pytest

from faers_ddi import config as cfg
from faers_ddi.define_event import (
    CONTINUITY_MIN_BASELINE,
    continuity_report,
    load_pt_list,
    verify_terms_exist,
)


QUARTERS = cfg.all_quarters()


def _con_with_series(series: dict[str, dict[str, int]]) -> duckdb.DuckDBPyConnection:
    """Build a case_event_pts table with prescribed per-concept quarterly counts."""
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE case_event_pts (
            case_id BIGINT, era VARCHAR, report_id BIGINT,
            quarter VARCHAR, pt VARCHAR, concept VARCHAR, tier VARCHAR)
    """)
    rows, case_id = [], 0
    for concept, counts in series.items():
        for quarter, n in counts.items():
            for _ in range(n):
                case_id += 1
                rows.append((case_id, "faers_modern", case_id, quarter,
                             concept.upper(), concept, "core"))
    con.executemany("INSERT INTO case_event_pts VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return con


# --- the retired-at-the-end case -------------------------------------------


def test_term_retired_at_the_end_of_the_window_is_flagged():
    """The real 2026q2 case: healthy volume, then nothing, at the series end."""
    baseline = CONTINUITY_MIN_BASELINE * 3
    counts = {q: baseline for q in QUARTERS[:-1]}
    counts[QUARTERS[-1]] = 0
    findings = continuity_report(_con_with_series({"retired": counts}))
    assert findings[0]["status"] == "BREAK"
    assert QUARTERS[-1] in findings[0]["break_quarters"]


def test_term_retired_mid_window_is_flagged():
    """The 2019q4 case: the term dies and its successor is a separate concept."""
    baseline = CONTINUITY_MIN_BASELINE * 3
    cut = QUARTERS.index("2019q4")
    counts = {q: baseline for q in QUARTERS[:cut]}
    findings = continuity_report(_con_with_series({"retired": counts}))
    assert findings[0]["status"] == "BREAK"
    assert findings[0]["break_quarters"].split(";")[0] == "2019q4"


def test_grouping_a_rename_into_one_concept_repairs_the_break():
    """Old and new term under one concept must produce a continuous series."""
    baseline = CONTINUITY_MIN_BASELINE * 3
    cut = QUARTERS.index("2019q4")
    old = {q: baseline for q in QUARTERS[:cut]}
    new = {q: baseline for q in QUARTERS[cut:]}
    merged = dict(old)
    merged.update(new)
    assert continuity_report(_con_with_series({"merged": merged}))[0]["status"] == "PASS"


def test_continuous_series_passes():
    counts = {q: CONTINUITY_MIN_BASELINE * 3 for q in QUARTERS}
    assert continuity_report(_con_with_series({"steady": counts}))[0]["status"] == "PASS"


def test_term_introduced_late_is_not_a_break():
    """EXERTIONAL RHABDOMYOLYSIS starts in 2024q2. Starting late is legitimate."""
    cut = QUARTERS.index("2024q2")
    counts = {q: CONTINUITY_MIN_BASELINE * 3 for q in QUARTERS[cut:]}
    assert continuity_report(_con_with_series({"new_term": counts}))[0]["status"] == "PASS"


def test_low_volume_gaps_are_not_flagged():
    """A rare term missing a quarter is noise, not a vocabulary change."""
    counts = {q: 1 for q in QUARTERS}
    counts[QUARTERS[40]] = 0
    assert continuity_report(_con_with_series({"rare": counts}))[0]["status"] == "PASS"


# --- the curated list ------------------------------------------------------


def test_pt_list_loads_and_is_well_formed():
    rows = load_pt_list()
    assert rows, "curated PT list must not be empty"
    for row in rows:
        assert row["tier"] in {"core", "broad"}
        assert row["concept"], f"{row['pt']} has no concept"
        assert row["pt"] == row["pt"].upper().strip()
    assert len({r["pt"] for r in rows}) == len(rows), "duplicate PT entries"


def test_both_sides_of_every_known_rename_are_present():
    """Dropping either half reopens the break the concept grouping closed."""
    pts = {r["pt"] for r in load_pt_list()}
    for old, new in [
        ("BLOOD CREATINE PHOSPHOKINASE INCREASED", "CREATINE KINASE INCREASED"),
        ("BLOOD CREATINE PHOSPHOKINASE ABNORMAL", "CREATINE KINASE ABNORMAL"),
        ("IMMUNE-MEDIATED NECROTISING MYOPATHY", "IMMUNE-MEDIATED MYOSITIS"),
    ]:
        assert old in pts and new in pts, f"{old} / {new}"


def test_renamed_terms_share_a_concept():
    by_pt = {r["pt"]: r["concept"] for r in load_pt_list()}
    assert by_pt["BLOOD CREATINE PHOSPHOKINASE INCREASED"] == by_pt["CREATINE KINASE INCREASED"]
    assert by_pt["BLOOD CREATINE PHOSPHOKINASE ABNORMAL"] == by_pt["CREATINE KINASE ABNORMAL"]
    assert by_pt["IMMUNE-MEDIATED NECROTISING MYOPATHY"] == by_pt["IMMUNE-MEDIATED MYOSITIS"]


def test_immune_myopathy_is_excluded_from_core():
    """The successor term carries ~5x the per-quarter volume of the one it
    replaced, so the rename broadened the concept. A concept whose definition
    widens mid-series cannot sit in the primary analysis."""
    for row in load_pt_list():
        if row["concept"] == "immune_myopathy":
            assert row["tier"] == "broad"


def test_the_seed_lists_wrong_word_order_is_not_reintroduced():
    pts = {r["pt"] for r in load_pt_list()}
    assert "MYOPATHY TOXIC" in pts
    assert "TOXIC MYOPATHY" not in pts


def test_core_is_restricted_to_muscle_destruction_concepts():
    core = {r["concept"] for r in load_pt_list() if r["tier"] == "core"}
    assert core == {"rhabdomyolysis", "myoglobin_release", "muscle_necrosis"}


def test_nonspecific_terms_are_not_in_core():
    """MYALGIA has 163,419 reports and is reported against almost everything."""
    for row in load_pt_list():
        if row["pt"] in {"MYALGIA", "MUSCULAR WEAKNESS", "MUSCLE DISORDER"}:
            assert row["tier"] == "broad"


@pytest.mark.parametrize(
    "excluded",
    ["CARDIOMYOPATHY", "DERMATOMYOSITIS", "POLYMYOSITIS", "FIBROMYALGIA",
     "POLYMYALGIA RHEUMATICA", "MUSCLE SPASMS", "MUSCULOSKELETAL PAIN",
     "MITOCHONDRIAL MYOPATHY", "MUSCULAR DYSTROPHY", "PYOMYOSITIS",
     "BLOOD CREATINE PHOSPHOKINASE DECREASED"],
)
def test_confounded_or_unrelated_terms_stay_out(excluded):
    """Cardiac, genetic, infectious and idiopathic muscle disease are separate
    entities; a decreased enzyme is the wrong direction."""
    assert excluded not in {r["pt"] for r in load_pt_list()}


def test_every_pt_row_carries_a_provenance_note():
    path = cfg.resolve(cfg.load_config()["event"]["pt_set_file"])
    with path.open() as fh:
        for row in csv.DictReader(fh):
            if row["pt"].strip():
                assert row["note"].strip(), f"{row['pt']} has no note"
