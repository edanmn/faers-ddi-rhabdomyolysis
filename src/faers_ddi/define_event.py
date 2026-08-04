"""Phase 5 -- define the myotoxicity case set from observed MedDRA PTs.

The PT list is curated against the 25,047 distinct PT strings that actually occur
in REAC across all 90 quarters, not written from a current MedDRA release. Around
40 MedDRA versions span 2004-2026 and terms are added, renamed and retired
throughout; a list built from today's vocabulary silently truncates the series.

Two renames inside this concept area, both clean instantaneous switches:

  2019q3 -> 2019q4   IMMUNE-MEDIATED NECROTISING MYOPATHY (45 -> 0)
                     IMMUNE-MEDIATED MYOSITIS             (0 -> 49)
  2026q1 -> 2026q2   BLOOD CREATINE PHOSPHOKINASE INCREASED (308 -> 0)
                     CREATINE KINASE INCREASED              (0 -> 404)

The second is part of a mass renaming: 1,907 PT strings make their last
appearance in 2026q1 and 335 appear for the first time in 2026q2.

PTs are therefore grouped into CONCEPTS, and all analysis is done at concept
level. Without that grouping, CK-increased counts fall off a cliff in the final
quarter and immune myopathy vanishes for six years -- artefacts of vocabulary
maintenance that the era-stratified analysis would read as real change.

Not every rename is meaning-preserving
--------------------------------------
CPK -> CK is a pure relabel: same concept, comparable volume. The immune myopathy
rename is NOT. The successor term carries roughly five times the per-quarter
volume of the term it replaced, so it is broader -- probably absorbing
checkpoint-inhibitor myositis. Treating the two as one concept therefore injects
a step change at 2019q4.

Both are kept in the BROAD tier and out of CORE for that reason. CORE is the
primary analysis and must be stable across the whole window; a concept whose
definition widens mid-series does not belong in it.

Tiers
-----
core    Muscle destruction, specific enough to be hard to report for any other
        reason: rhabdomyolysis, myoglobin release, muscle necrosis.
broad   Adds general myotoxicity and the CK enzyme markers. Far more powerful and
        far more confounded -- MYALGIA alone has 163,419 reports and is reported
        against almost everything. Sensitivity analysis only.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys

import duckdb

from faers_ddi import config as cfg

log = logging.getLogger("define_event")

# A concept that dies mid-series and is not picked up by a synonym is a
# vocabulary artefact, not an epidemiological finding. Flag a quarter with zero
# reports when the preceding year averaged at least this many.
CONTINUITY_MIN_BASELINE = 10


def load_pt_list() -> list[dict]:
    path = cfg.resolve(cfg.load_config()["event"]["pt_set_file"])
    with path.open() as fh:
        rows = [r for r in csv.DictReader(fh) if r["pt"].strip()]
    for row in rows:
        row["pt"] = row["pt"].strip().upper()
        row["tier"] = row["tier"].strip().lower()
        row["concept"] = row["concept"].strip().lower()
    return rows


def verify_terms_exist(con: duckdb.DuckDBPyConnection, pt_rows: list[dict]) -> list[dict]:
    """Every curated PT must occur in the data.

    This is what catches a term written from memory rather than from the
    vocabulary. The seed list contained "Toxic myopathy"; the actual FAERS term
    is MYOPATHY TOXIC, so the seed entry would have matched zero rows and
    quietly contributed nothing.
    """
    findings = []
    for row in pt_rows:
        hit = con.execute(
            "SELECT reports, first_q, last_q, n_quarters FROM pt_vocab WHERE pt = ?",
            [row["pt"]],
        ).fetchone()
        findings.append({
            "pt": row["pt"], "tier": row["tier"], "concept": row["concept"],
            "reports": hit[0] if hit else 0,
            "first_quarter": hit[1] if hit else "",
            "last_quarter": hit[2] if hit else "",
            "n_quarters": hit[3] if hit else 0,
            "status": "OK" if hit else "NOT_FOUND",
        })
    return findings


def build(con: duckdb.DuckDBPyConnection, pt_rows: list[dict]) -> None:
    con.execute("CREATE OR REPLACE TABLE event_pts (pt VARCHAR, tier VARCHAR, concept VARCHAR)")
    con.executemany(
        "INSERT INTO event_pts VALUES (?, ?, ?)",
        [(r["pt"], r["tier"], r["concept"]) for r in pt_rows],
    )

    reac = str(cfg.path("parquet") / "reac" / "*.parquet")
    # broad is a superset of core: a core PT qualifies under both tiers.
    con.execute(f"""
        CREATE OR REPLACE TABLE case_event_pts AS
        SELECT c.case_id, c.era, c.report_id, c.quarter,
               e.pt, e.concept, e.tier
        FROM read_parquet('{reac}') r
        JOIN cases_deduped c ON c.era = r.era AND c.report_id = r.report_id
        JOIN event_pts e ON e.pt = upper(trim(r.pt))
    """)
    con.execute("""
        CREATE OR REPLACE TABLE case_events AS
        SELECT case_id, era, report_id, quarter,
               max(CASE WHEN tier = 'core' THEN 1 ELSE 0 END) = 1 AS is_core,
               true AS is_broad,
               list(DISTINCT concept) AS concepts
        FROM case_event_pts
        GROUP BY 1, 2, 3, 4
    """)


def continuity_report(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Per-concept quarterly series, flagging structural breaks."""
    series = con.execute("""
        SELECT concept, quarter, count(DISTINCT case_id) AS reports
        FROM case_event_pts GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()

    by_concept: dict[str, dict[str, int]] = {}
    for concept, quarter, reports in series:
        by_concept.setdefault(concept, {})[quarter] = reports

    quarters = cfg.all_quarters()
    findings: list[dict] = []
    for concept, counts in sorted(by_concept.items()):
        present = [q for q in quarters if counts.get(q, 0) > 0]
        if not present:
            continue
        start = quarters.index(present[0])
        breaks = []
        # Scan to the end of the STUDY window, not to the concept's own last
        # non-zero quarter. Bounding the scan by the term's own presence makes
        # the check vacuous for exactly the case that matters most: a term
        # retired at the end of the window. BLOOD CREATINE PHOSPHOKINASE
        # INCREASED stops dead at 2026q1 after averaging ~350 reports a quarter,
        # and the original loop never examined 2026q2, so it reported PASS.
        for i in range(start + 4, len(quarters)):
            baseline = [counts.get(q, 0) for q in quarters[i - 4:i]]
            if counts.get(quarters[i], 0) == 0 and sum(baseline) / 4 >= CONTINUITY_MIN_BASELINE:
                breaks.append(quarters[i])
        findings.append({
            "concept": concept,
            "first_quarter": present[0],
            "last_quarter": present[-1],
            "quarters_present": len(present),
            "total_reports": sum(counts.values()),
            "break_quarters": ";".join(breaks),
            "status": "PASS" if not breaks else "BREAK",
        })
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "define_event.log"),
                  logging.StreamHandler(sys.stdout)],
        force=True,
    )

    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    pt_rows = load_pt_list()
    log.info("curated PT list: %d terms across %d concepts",
             len(pt_rows), len({r["concept"] for r in pt_rows}))

    verification = verify_terms_exist(con, pt_rows)
    missing = [v for v in verification if v["status"] == "NOT_FOUND"]
    out_dir = cfg.path("tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "event_pt_verification.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(verification[0]))
        writer.writeheader()
        writer.writerows(verification)
    if missing:
        for row in missing:
            log.error("PT not present in any quarter: %r", row["pt"])
        return 1
    log.info("all %d curated PTs verified present in the data", len(verification))

    build(con, pt_rows)

    core, broad = con.execute("""
        SELECT count(*) FILTER (WHERE is_core), count(*) FROM case_events
    """).fetchone()
    total = con.execute("SELECT count(*) FROM cases_deduped").fetchone()[0]
    log.info("event cases: core=%s (%.3f%% of all cases), broad=%s (%.3f%%)",
             f"{core:,}", 100 * core / total, f"{broad:,}", 100 * broad / total)

    breaks = continuity_report(con)
    with (out_dir / "event_concept_continuity.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(breaks[0]))
        writer.writeheader()
        writer.writerows(breaks)
    for row in breaks:
        level = log.info if row["status"] == "PASS" else log.warning
        level("  %-18s %-8s %s-%s  %s quarters, %s reports%s",
              row["concept"], row["status"], row["first_quarter"], row["last_quarter"],
              row["quarters_present"], f"{row['total_reports']:,}",
              f"  BREAKS: {row['break_quarters']}" if row["break_quarters"] else "")

    with (out_dir / "event_case_counts.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["scope", "group", "core_cases", "broad_cases"])
        for era, c, b in con.execute("""
            SELECT era, count(*) FILTER (WHERE is_core), count(*)
            FROM case_events GROUP BY 1 ORDER BY 1
        """).fetchall():
            writer.writerow(["era", era, c, b])
        for year, c, b in con.execute("""
            SELECT substr(quarter, 1, 4) AS yr, count(*) FILTER (WHERE is_core), count(*)
            FROM case_events GROUP BY 1 ORDER BY 1
        """).fetchall():
            writer.writerow(["year", year, c, b])

    failed = [row for row in breaks if row["status"] == "BREAK"]
    con.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
