"""Phase 2 validation -- structural checks on the parsed Parquet.

The trailing-delimiter bug that shifted every column left by one was caught only
because REAC's second column happens to hold text, so the id cast failed. In
DRUG the same shift moves `drug_seq` into `report_id`; both are integers, every
type check passes, and the pipeline runs to completion attributing every drug to
the wrong report.

Referential integrity does not depend on that luck. Every row in a child table
carries the report id of a row in DEMO for the same quarter. Under a column
shift, `report_id` holds something else entirely and essentially no child row
resolves -- whatever the dtypes look like.

Checks:
  1. DEMO's report_id is unique within each quarter.
  2. Child-table report_ids resolve to a DEMO row in the same quarter.
  3. Parsed row counts agree with the parse manifest.
  4. Deleted case ids look like FAERS case ids.

Writes results/tables/parse_validation.csv and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys

import duckdb

from faers_ddi import config as cfg

log = logging.getLogger("validate_parse")

CHILD_TABLES = ("drug", "reac", "indi", "ther", "outc", "rpsr")
# Zero, measured rather than assumed. This was originally 2%, on the theory that
# FDA ships some child rows whose parent was withdrawn. It does not: across all
# 328M rows the observed orphan count is exactly 0. The loose threshold nearly
# passed 2018Q1, whose DEMO table was missing entirely -- its 100% orphan rate
# averaged out to 2.0% across the table and sat just inside the limit.
ORPHAN_RATE_LIMIT = 0.0


def _glob(table: str) -> str:
    return str(cfg.path("parquet") / table / "*.parquet")


def run_checks() -> tuple[list[dict], bool]:
    con = duckdb.connect()
    findings: list[dict] = []
    ok = True

    # 1. DEMO report_id uniqueness within a quarter.
    duplicates = con.execute(f"""
        SELECT quarter, count(*) AS rows, count(DISTINCT report_id) AS distinct_ids
        FROM read_parquet('{_glob("demo")}')
        GROUP BY quarter
        HAVING count(*) <> count(DISTINCT report_id)
        ORDER BY quarter
    """).fetchall()
    for quarter, rows, distinct_ids in duplicates:
        findings.append({
            "check": "demo_report_id_unique", "scope": quarter,
            "value": rows - distinct_ids, "denominator": rows,
            "rate": (rows - distinct_ids) / rows if rows else 0,
            "status": "WARN",
            "detail": f"{rows - distinct_ids:,} duplicate report_ids in DEMO",
        })
    if not duplicates:
        findings.append({
            "check": "demo_report_id_unique", "scope": "all", "value": 0,
            "denominator": 0, "rate": 0.0, "status": "PASS",
            "detail": "report_id unique within every quarter",
        })

    # 2. Referential integrity, per child table.
    for table in CHILD_TABLES:
        total, orphans = con.execute(f"""
            WITH parents AS (
                SELECT DISTINCT quarter, report_id
                FROM read_parquet('{_glob("demo")}')
            ), child AS (
                SELECT quarter, report_id FROM read_parquet('{_glob(table)}')
            )
            SELECT
                (SELECT count(*) FROM child),
                (SELECT count(*) FROM child c
                 WHERE NOT EXISTS (
                     SELECT 1 FROM parents p
                     WHERE p.quarter = c.quarter AND p.report_id = c.report_id))
        """).fetchone()
        rate = orphans / total if total else 0.0
        status = "PASS" if rate <= ORPHAN_RATE_LIMIT else "FAIL"
        ok &= status == "PASS"
        findings.append({
            "check": "child_resolves_to_demo", "scope": table,
            "value": orphans, "denominator": total, "rate": rate,
            "status": status,
            "detail": f"{orphans:,}/{total:,} rows have no DEMO row in their quarter",
        })

    # 3. Row counts agree with the manifest.
    manifest_path = cfg.path("tables") / "parse_manifest.csv"
    if manifest_path.exists():
        expected: dict[str, int] = {}
        with manifest_path.open() as fh:
            for row in csv.DictReader(fh):
                expected[row["table"]] = expected.get(row["table"], 0) + int(row["rows_parsed"])
        for table, want in sorted(expected.items()):
            got = con.execute(
                f"SELECT count(*) FROM read_parquet('{_glob(table)}')"
            ).fetchone()[0]
            status = "PASS" if got == want else "FAIL"
            ok &= status == "PASS"
            findings.append({
                "check": "rowcount_matches_manifest", "scope": table,
                "value": got - want, "denominator": want,
                "rate": abs(got - want) / want if want else 0,
                "status": status,
                "detail": f"parquet {got:,} vs manifest {want:,}",
            })

    # 4. Deleted case ids are plausible FAERS case ids.
    deleted_path = cfg.path("parquet").parent / "deleted_cases.parquet"
    if deleted_path.exists():
        count, low, high = con.execute(
            f"SELECT count(*), min(case_id), max(case_id) FROM read_parquet('{deleted_path}')"
        ).fetchone()
        status = "PASS" if count and low > 0 else "FAIL"
        ok &= status == "PASS"
        findings.append({
            "check": "deleted_cases_loaded", "scope": "all",
            "value": count, "denominator": count, "rate": 0.0, "status": status,
            "detail": f"{count:,} unique case ids, range {low:,}-{high:,}",
        })

        matched, = con.execute(f"""
            SELECT count(DISTINCT d.case_id)
            FROM read_parquet('{deleted_path}') d
            WHERE EXISTS (
                SELECT 1 FROM read_parquet('{_glob("demo")}') m
                WHERE m.case_id = d.case_id AND m.era <> 'laers')
        """).fetchone()
        rate = matched / count if count else 0.0
        # Not all deleted ids need be present -- a case deleted before it was
        # ever published never appears. But near-zero overlap would mean the
        # lists are keyed on something other than caseid.
        status = "PASS" if rate > 0.10 else "FAIL"
        ok &= status == "PASS"
        findings.append({
            "check": "deleted_cases_match_demo", "scope": "all",
            "value": matched, "denominator": count, "rate": rate, "status": status,
            "detail": f"{matched:,}/{count:,} deleted case ids appear in DEMO",
        })

    return findings, ok


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)], force=True,
    )

    findings, ok = run_checks()

    out = cfg.path("tables") / "parse_validation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["check", "scope", "status", "value", "denominator", "rate", "detail"],
        )
        writer.writeheader()
        writer.writerows(findings)

    for finding in findings:
        level = log.info if finding["status"] == "PASS" else log.warning
        level("%-6s %-28s %-8s %s",
              finding["status"], finding["check"], finding["scope"], finding["detail"])
    log.info("validation -> %s", out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
