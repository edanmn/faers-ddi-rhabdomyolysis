"""Tests for quarter arithmetic and URL construction.

The filename-prefix boundary and the endpoints of the study window were verified
against the live FDA server; these tests lock in that behaviour so a later edit
to config.yaml cannot silently break the download stage.
"""

import pytest

from faers_ddi import config as cfg


def test_window_endpoints_and_length():
    quarters = cfg.all_quarters()
    assert quarters[0] == "2004q1"
    assert quarters[-1] == "2026q2"
    assert len(quarters) == 90
    assert len(set(quarters)) == 90


def test_quarters_are_strictly_increasing():
    idx = [cfg.quarter_index(q) for q in cfg.all_quarters()]
    assert idx == sorted(idx)
    assert all(b - a == 1 for a, b in zip(idx, idx[1:]))


@pytest.mark.parametrize(
    "quarter,expected",
    [
        ("2004q1", "aers_ascii_2004q1.zip"),
        ("2012q3", "aers_ascii_2012q3.zip"),   # last LAERS quarter
        ("2012q4", "faers_ascii_2012q4.zip"),  # first FAERS quarter
        ("2026q2", "faers_ascii_2026q2.zip"),
    ],
)
def test_zip_name_prefix_boundary(quarter, expected):
    assert cfg.zip_name(quarter) == expected


def test_legacy_split_counts():
    quarters = cfg.all_quarters()
    legacy = [q for q in quarters if cfg.is_legacy(q)]
    modern = [q for q in quarters if not cfg.is_legacy(q)]
    assert len(legacy) == 35
    assert len(modern) == 55


@pytest.mark.parametrize(
    "quarter,era",
    [
        ("2004q1", "laers"),
        ("2012q3", "laers"),
        ("2012q4", "faers_early"),
        ("2014q2", "faers_early"),
        ("2014q3", "faers_modern"),
        ("2026q2", "faers_modern"),
    ],
)
def test_era_assignment(quarter, era):
    assert cfg.era_of(quarter) == era


def test_every_quarter_has_an_era():
    for q in cfg.all_quarters():
        cfg.era_of(q)  # raises if unassigned


def test_quarter_range_rejects_reversed_bounds():
    with pytest.raises(ValueError):
        cfg.quarter_range("2010q1", "2009q4")


def test_url_is_built_from_base():
    url = cfg.zip_url("2020q1")
    assert url == "https://fis.fda.gov/content/Exports/faers_ascii_2020q1.zip"
