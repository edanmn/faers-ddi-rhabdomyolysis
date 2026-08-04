"""Tests for deduplication logic.

Built on a synthetic dataset small enough to reason about, written to Parquet in
the layout the real pipeline reads, so `dedup.build` is exercised end to end
rather than in pieces.

The cases encoded here are the ones that actually bit during development:
a case spanning the LAERS/FAERS boundary, a case present in both FAERS
sub-eras (which must NOT be double counted), a report appearing under two case
numbers, and sparse records that must survive rather than being merged on a
fingerprint made mostly of blanks.
"""

from __future__ import annotations

import unittest.mock as mock

import duckdb
import pandas as pd
import pytest

from faers_ddi import config as cfg
from faers_ddi import dedup


# --- age normalisation -----------------------------------------------------


@pytest.mark.parametrize(
    "age,code,expected",
    [
        ("50", "YR", 50.0),
        ("50", "", 50.0),        # blank code is treated as years
        ("24", "MON", 2.0),
        ("6", "DEC", 60.0),
        ("52", "WK", 1.0),
        ("365", "DY", 1.0),
        ("", "YR", None),        # nothing to convert
        ("abc", "YR", None),     # non-numeric must not raise
        ("50", "NONSENSE", None),
    ],
)
def test_age_is_converted_to_years(age, code, expected):
    sql = dedup._age_case_sql("age", "age_cod")
    con = duckdb.connect()
    result = con.execute(
        f"SELECT {sql} FROM (SELECT ? AS age, ? AS age_cod)", [age, code]
    ).fetchone()[0]
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected, abs=0.05)


# --- end-to-end on a synthetic dataset -------------------------------------


def _write(tmp_path, demo_rows, drug_rows, reac_rows, deleted=()):
    parquet = tmp_path / "parquet"
    for name, rows, columns in [
        ("demo", demo_rows, ["report_id", "case_id", "era", "quarter", "caseversion",
                             "event_dt", "sex", "age", "age_cod", "occr_country",
                             "reporter_country"]),
        ("drug", drug_rows, ["report_id", "era", "quarter", "drugname"]),
        ("reac", reac_rows, ["report_id", "era", "quarter", "pt"]),
    ]:
        directory = parquet / name
        directory.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(rows, columns=columns)
        frame.to_parquet(directory / f"{name}_synthetic.parquet", index=False)

    if deleted:
        pd.DataFrame({"case_id": list(deleted)}).to_parquet(
            parquet.parent / "deleted_cases.parquet", index=False)
    return parquet


def _run(tmp_path, demo_rows, drug_rows, reac_rows, deleted=()):
    parquet = _write(tmp_path, demo_rows, drug_rows, reac_rows, deleted)
    real_path = cfg.path

    def redirected(key: str):
        return parquet if key == "parquet" else real_path(key)

    con = duckdb.connect()
    with mock.patch.object(cfg, "path", side_effect=redirected):
        attrition = dedup.build(con)
    result = con.execute(
        "SELECT case_id, era, report_id, quarter FROM cases_deduped ORDER BY case_id"
    ).fetch_df()
    return result, {row["stage"]: row for row in attrition}


def _demo(report_id, case_id, era, quarter, version="", event="20100101",
          sex="M", age="50", age_cod="YR", country="US"):
    return [report_id, case_id, era, quarter, version, event, sex, age, age_cod,
            country, country]


def test_keeps_highest_caseversion_within_faers(tmp_path):
    demo = [
        _demo(1001, 500, "faers_modern", "2020q1", "1"),
        _demo(1002, 500, "faers_modern", "2020q2", "2"),
        _demo(1003, 500, "faers_modern", "2020q3", "3"),
    ]
    result, _ = _run(tmp_path, demo, [], [])
    assert len(result) == 1
    assert result.iloc[0]["report_id"] == 1003


def test_keeps_highest_isr_within_laers(tmp_path):
    """LAERS has no caseversion; follow-ups get a higher isr."""
    demo = [
        _demo(7001, 600, "laers", "2008q1"),
        _demo(7009, 600, "laers", "2008q2"),
        _demo(7005, 600, "laers", "2008q3"),
    ]
    result, _ = _run(tmp_path, demo, [], [])
    assert len(result) == 1
    assert result.iloc[0]["report_id"] == 7009


def test_case_spanning_the_era_boundary_is_counted_once(tmp_path):
    """LAERS `case` and FAERS `caseid` share an id space -- verified against a
    chance baseline. A case revised after 2012Q4 appears in both eras."""
    demo = [
        _demo(8001, 700, "laers", "2010q1"),
        _demo(9001, 700, "faers_modern", "2015q1", "2"),
    ]
    result, attrition = _run(tmp_path, demo, [], [])
    assert len(result) == 1
    assert result.iloc[0]["era"] == "faers_modern", "the FAERS record is the later one"
    assert attrition["3_cross_era_bridge"]["removed"] == 1


def test_case_in_both_faers_sub_eras_is_not_double_counted(tmp_path):
    """faers_early and faers_modern share one caseid space.

    Partitioning stage 2 by `era` rather than by era GROUP dedupes them
    separately, leaving the case for stage 3 to mop up -- which produces the
    right final count but makes the stage counts mean the wrong thing.
    """
    demo = [
        _demo(2001, 800, "faers_early", "2013q1", "1"),
        _demo(2002, 800, "faers_modern", "2016q1", "2"),
    ]
    result, attrition = _run(tmp_path, demo, [], [])
    assert len(result) == 1
    assert result.iloc[0]["report_id"] == 2002
    assert attrition["2_within_faers"]["removed"] == 1, "collapsed within FAERS..."
    assert attrition["3_cross_era_bridge"]["removed"] == 0, "...not by the era bridge"


def test_deleted_cases_are_removed(tmp_path):
    demo = [
        _demo(3001, 900, "faers_modern", "2020q1", "1"),
        _demo(3002, 901, "faers_modern", "2020q1", "1"),
    ]
    result, attrition = _run(tmp_path, demo, [], [], deleted=(900,))
    assert result["case_id"].tolist() == [901]
    assert attrition["4_deleted_cases"]["removed"] == 1


def test_identical_reports_under_different_case_ids_are_merged(tmp_path):
    """The manufacturer-plus-physician case: same report, two case numbers."""
    demo = [
        _demo(4001, 1000, "faers_modern", "2020q1", "1"),
        _demo(4002, 1001, "faers_modern", "2020q1", "1"),
    ]
    drug = [[4001, "faers_modern", "2020q1", "SIMVASTATIN"],
            [4002, "faers_modern", "2020q1", "simvastatin"]]  # case-insensitive
    reac = [[4001, "faers_modern", "2020q1", "RHABDOMYOLYSIS"],
            [4002, "faers_modern", "2020q1", "Rhabdomyolysis"]]
    result, attrition = _run(tmp_path, demo, drug, reac)
    assert len(result) == 1
    assert attrition["5_near_duplicates"]["removed"] == 1


def test_drug_set_order_does_not_affect_the_match(tmp_path):
    """Sets are compared by order-independent hashes, not sorted strings."""
    demo = [
        _demo(4101, 1100, "faers_modern", "2020q1", "1"),
        _demo(4102, 1101, "faers_modern", "2020q1", "1"),
    ]
    drug = [[4101, "faers_modern", "2020q1", "ASPIRIN"],
            [4101, "faers_modern", "2020q1", "WARFARIN"],
            [4102, "faers_modern", "2020q1", "WARFARIN"],
            [4102, "faers_modern", "2020q1", "ASPIRIN"]]
    reac = [[4101, "faers_modern", "2020q1", "HAEMORRHAGE"],
            [4102, "faers_modern", "2020q1", "HAEMORRHAGE"]]
    result, _ = _run(tmp_path, demo, drug, reac)
    assert len(result) == 1


def test_different_drug_sets_are_not_merged(tmp_path):
    demo = [
        _demo(4201, 1200, "faers_modern", "2020q1", "1"),
        _demo(4202, 1201, "faers_modern", "2020q1", "1"),
    ]
    drug = [[4201, "faers_modern", "2020q1", "ASPIRIN"],
            [4202, "faers_modern", "2020q1", "WARFARIN"]]
    reac = [[4201, "faers_modern", "2020q1", "HAEMORRHAGE"],
            [4202, "faers_modern", "2020q1", "HAEMORRHAGE"]]
    result, _ = _run(tmp_path, demo, drug, reac)
    assert len(result) == 2


def test_sparse_records_are_kept_not_merged(tmp_path):
    """The bug that removed 14.5% of all cases.

    Two different patients with no event date and no age, sharing a sex, a
    country, one drug and one PT. Under a "any 4 of 6 populated" rule these
    merge; under the required-field rule they are ineligible and both survive.
    """
    demo = [
        _demo(5001, 1300, "faers_modern", "2020q1", "1", event="", age="", age_cod=""),
        _demo(5002, 1301, "faers_modern", "2020q1", "1", event="", age="", age_cod=""),
    ]
    drug = [[5001, "faers_modern", "2020q1", "ASPIRIN"],
            [5002, "faers_modern", "2020q1", "ASPIRIN"]]
    reac = [[5001, "faers_modern", "2020q1", "NAUSEA"],
            [5002, "faers_modern", "2020q1", "NAUSEA"]]
    result, attrition = _run(tmp_path, demo, drug, reac)
    assert len(result) == 2, "sparse records must not be merged"
    assert attrition["5_near_duplicates"]["removed"] == 0


def test_one_case_per_report(tmp_path):
    """A report under two case numbers would double-attribute its drug rows."""
    demo = [
        _demo(6001, 1400, "laers", "2004q1", event="", age="", age_cod=""),
        _demo(6001, 1401, "laers", "2004q2", event="", age="", age_cod=""),
    ]
    result, attrition = _run(tmp_path, demo, [], [])
    assert len(result) == 1
    assert result.iloc[0]["quarter"] == "2004q2", "later quarter carries the fix"
    assert attrition["6_one_case_per_report"]["removed"] == 1


def test_final_keys_are_unique(tmp_path):
    """Both keys must be unique: case_id identifies the case, and
    (era, report_id) is what DRUG and REAC are joined on."""
    demo = [
        _demo(1001, 500, "faers_modern", "2020q1", "1"),
        _demo(1002, 500, "faers_modern", "2020q2", "2"),
        _demo(8001, 700, "laers", "2010q1"),
        _demo(9001, 700, "faers_modern", "2015q1", "2"),
        _demo(6001, 1400, "laers", "2004q1"),
        _demo(6001, 1401, "laers", "2004q2"),
    ]
    result, _ = _run(tmp_path, demo, [], [])
    assert result["case_id"].is_unique
    assert not result.duplicated(subset=["era", "report_id"]).any()
