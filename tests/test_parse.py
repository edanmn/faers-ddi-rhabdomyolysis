"""Tests for header harmonisation and delimiter handling.

The regression test that matters is `test_trailing_delimiter_does_not_shift_columns`.
Every data line in every FAERS table ends with a trailing delimiter its header
does not declare. Given more fields than names, pandas promotes the surplus
leading column to the index and shifts every column left by one -- silently, with
no bad-line report and no exception.

That shift is undetectable in most tables. In DRUG it would move `drug_seq` into
`report_id`; both are integers, so a type check passes and the pipeline runs to
completion on data where every drug is attributed to the wrong report. It was
caught only because REAC has a text second column. These tests remove the
reliance on that luck.
"""

from __future__ import annotations

import io
import unittest.mock as mock
import zipfile

import pytest

from faers_ddi import config as cfg
from faers_ddi.column_audit import classify_member
from faers_ddi.parse import harmonised_columns, parse_member


DELIMITER = "$"


def _zip_with(member: str, content: str) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(member, content)
    return zipfile.ZipFile(buffer)


# --- header harmonisation --------------------------------------------------


def test_bom_is_stripped_from_the_first_column():
    """DRUG12Q4.txt begins with a UTF-8 BOM welded to `primaryid`."""
    columns = harmonised_columns("﻿primaryid$caseid$drug_seq", "2012q4", DELIMITER)
    assert columns[0] == "report_id"
    assert not any(c.startswith("﻿") for c in columns)


@pytest.mark.parametrize(
    "quarter,raw,expected",
    [
        ("2012q4", "primaryid$caseid$outc_code", "outc_cod"),   # 2012q4 only
        ("2012q4", "primaryid$caseid$lot_nbr", "lot_num"),      # 2012q4 only
        ("2004q1", "ISR$CASE$GNDR_COD", "sex"),                 # legacy -> modern
        ("2013q1", "primaryid$caseid$i_f_code", "i_f_cod"),
    ],
)
def test_one_quarter_spelling_anomalies_are_renamed(quarter, raw, expected):
    assert expected in harmonised_columns(raw, quarter, DELIMITER)


@pytest.mark.parametrize(
    "quarter,raw",
    [
        ("2004q1", "ISR$CASE$I_F_COD"),        # legacy identity columns
        ("2020q1", "primaryid$caseid$sex"),    # modern identity columns
    ],
)
def test_identity_columns_get_era_neutral_names(quarter, raw):
    columns = harmonised_columns(raw, quarter, DELIMITER)
    assert columns[0] == "report_id"
    assert columns[1] == "case_id"
    assert "isr" not in columns and "primaryid" not in columns


def test_headers_are_lowercased():
    assert harmonised_columns("ISR$PT", "2004q1", DELIMITER) == ["report_id", "pt"]


def test_duplicate_columns_after_harmonisation_are_rejected():
    # gndr_cod -> sex would collide with an existing sex column.
    with pytest.raises(ValueError, match="duplicate"):
        harmonised_columns("primaryid$sex$gndr_cod", "2004q1", DELIMITER)


# --- the trailing-delimiter regression -------------------------------------


def test_trailing_delimiter_does_not_shift_columns():
    """Two declared columns, three fields per row. Must not shift."""
    content = (
        "ISR$PT\r\n"
        "4204616$ABDOMINAL PAIN$\r\n"
        "4204616$NAUSEA$\r\n"
        "4204617$PYREXIA$\r\n"
    )
    zf = _zip_with("ascii/REAC04Q1.TXT", content)
    frame, stats = parse_member(zf, "ascii/REAC04Q1.TXT", "reac", "2004q1", DELIMITER)

    assert list(frame.columns[:2]) == ["report_id", "pt"]
    assert frame["report_id"].tolist() == [4204616, 4204616, 4204617]
    assert frame["pt"].tolist() == ["ABDOMINAL PAIN", "NAUSEA", "PYREXIA"]
    assert stats["rows_parsed"] == 3
    assert stats["rows_skipped"] == 0
    assert stats["id_nulls"] == 0
    assert stats["rows_with_trailing_field"] == 3
    assert stats["surplus_values"] == 0, "the trailing field must be empty"


def test_trailing_delimiter_does_not_shift_an_all_integer_table():
    """The case a type check cannot catch.

    In DRUG a left shift moves drug_seq into report_id. Both are integers, so
    nothing about the dtypes looks wrong -- every drug is simply attributed to
    the wrong report. Assert on values, not types.
    """
    content = (
        "ISR$DRUG_SEQ$ROLE_COD$DRUGNAME\r\n"
        "4204616$1004278786$PS$MIFEPRISTONE$\r\n"
        "4204616$1004278787$SS$IBUPROFEN$\r\n"
    )
    zf = _zip_with("ascii/DRUG04Q1.TXT", content)
    frame, _ = parse_member(zf, "ascii/DRUG04Q1.TXT", "drug", "2004q1", DELIMITER)

    assert frame["report_id"].tolist() == [4204616, 4204616]
    assert frame["drug_seq"].tolist() == ["1004278786", "1004278787"]
    assert frame["drugname"].tolist() == ["MIFEPRISTONE", "IBUPROFEN"]


def test_surplus_values_beyond_the_header_are_reported_not_dropped():
    """A genuinely undeclared value must be counted, not silently discarded."""
    content = "ISR$PT\r\n4204616$NAUSEA$UNEXPECTED\r\n"
    zf = _zip_with("ascii/REAC04Q1.TXT", content)
    _, stats = parse_member(zf, "ascii/REAC04Q1.TXT", "reac", "2004q1", DELIMITER)
    assert stats["surplus_values"] == 1


def test_misaligned_columns_raise_rather_than_write_bad_parquet():
    content = "ISR$PT\r\nNOT_AN_ID$NAUSEA$\r\nALSO_NOT$PYREXIA$\r\n"
    zf = _zip_with("ascii/REAC04Q1.TXT", content)
    with pytest.raises(ValueError, match="misaligned"):
        parse_member(zf, "ascii/REAC04Q1.TXT", "reac", "2004q1", DELIMITER)


def test_era_and_quarter_are_carried_on_every_row():
    """Phase 3 needs these: legacy `case` and modern `caseid` are distinct
    id spaces until the bridge is verified, so era cannot be inferred later."""
    content = "ISR$PT\r\n4204616$NAUSEA$\r\n"
    zf = _zip_with("ascii/REAC04Q1.TXT", content)
    frame, _ = parse_member(zf, "ascii/REAC04Q1.TXT", "reac", "2004q1", DELIMITER)
    assert frame["quarter"].unique().tolist() == ["2004q1"]
    assert frame["era"].unique().tolist() == ["laers"]


def test_values_are_whitespace_stripped():
    content = "ISR$PT\r\n4204616$  NAUSEA  $\r\n"
    zf = _zip_with("ascii/REAC04Q1.TXT", content)
    frame, _ = parse_member(zf, "ascii/REAC04Q1.TXT", "reac", "2004q1", DELIMITER)
    assert frame["pt"].tolist() == ["NAUSEA"]


def test_non_utf8_bytes_are_decoded_and_counted():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        # 0x92 is a cp1252 curly apostrophe and invalid UTF-8.
        zf.writestr("ascii/REAC04Q1.TXT", b"ISR$PT\r\n4204616$CROHN\x92S DISEASE$\r\n")
    frame, stats = parse_member(
        zipfile.ZipFile(buffer), "ascii/REAC04Q1.TXT", "reac", "2004q1", DELIMITER
    )
    assert len(frame) == 1
    assert stats["decode_errors"] == 0, "cp1252 decodes this cleanly"
    assert "S DISEASE" in frame["pt"].iloc[0]


# --- deleted-case member classification ------------------------------------


@pytest.mark.parametrize(
    "member",
    [
        "deleted/ADR19Q1DeletedCases.txt",
        "deleted/AllDeletedCases.txt",
        "DELETED/ADR20Q1DeletedCases.txt",
        "Deleted/ADR20Q3DeletedCases.txt",
        "Deleted/20Q4DeletedCases.txt",
        "Deleted/21Q3DeletedCases.txt",
        # From 2021q4 the basename contains "DELETE" but not "DELETED". Matching
        # the basename against "deleted" made 19 quarters look as though they
        # shipped no deletion list at all.
        "Deleted/DELETE22Q1.txt",
        "Deleted/DELETE26Q2.txt",
    ],
)
def test_every_deleted_case_naming_convention_is_recognised(member):
    _, kind = classify_member(member)
    assert kind == "deleted_cases"


@pytest.mark.parametrize(
    "member,expected_table",
    [
        ("ascii/DEMO04Q1.TXT", "demo"),
        ("ascii/DRUG14Q3.txt", "drug"),
        ("ASCII/REAC26Q2.txt", "reac"),
    ],
)
def test_table_members_are_still_classified_as_tables(member, expected_table):
    table, kind = classify_member(member)
    assert (table, kind) == (expected_table, "table")


def test_documentation_is_not_mistaken_for_data():
    for member in ("Readme.pdf", "ascii/ASC_NTS.pdf", "FAQs.doc"):
        _, kind = classify_member(member)
        assert kind == "documentation"


# --- irregular member names ------------------------------------------------


@pytest.mark.parametrize(
    "member,expected_table",
    [
        # FDA ships 2018Q1 demographics under this name. Anchoring the pattern
        # on "Q<digit>.TXT" classified it as documentation and silently dropped
        # a whole quarter of DEMO.
        ("ascii/DEMO18Q1_new.txt", "demo"),
        ("ascii/DEMO18Q1.txt", "demo"),
        ("ascii/DRUG21Q4.TXT", "drug"),
    ],
)
def test_irregular_table_filenames_are_still_recognised(member, expected_table):
    table, kind = classify_member(member)
    assert (table, kind) == (expected_table, "table")


def test_missing_table_raises_rather_than_producing_a_short_quarter(tmp_path):
    """A quarter yielding fewer tables than expected must fail, not proceed.

    Both the input archive and the Parquet output directory are redirected into
    tmp_path. `parse_quarter` writes each table as it goes and only checks for
    missing tables at the end, so without redirecting the output this test
    overwrites the real reac_2004q1.parquet with its one-row fixture -- which is
    exactly what happened, and was caught by the row-count validation.
    """
    from faers_ddi.parse import parse_quarter

    archive = tmp_path / "aers_ascii_2004q1.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ascii/REAC04Q1.TXT", "ISR$PT\r\n4204616$NAUSEA$\r\n")

    real_path = cfg.path

    def redirected(key: str):
        return tmp_path / "out" if key == "parquet" else real_path(key)

    with mock.patch.object(cfg, "zip_path", return_value=archive), \
         mock.patch.object(cfg, "path", side_effect=redirected):
        with pytest.raises(ValueError, match="no member matched"):
            parse_quarter("2004q1")

    # The partial write landed in tmp_path, not in the project's data tree.
    assert (tmp_path / "out" / "reac" / "reac_2004q1.parquet").exists()
