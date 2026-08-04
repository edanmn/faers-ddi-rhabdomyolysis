"""Phase 3 -- reduce 24.8M report rows to one record per distinct case.

Five stages, each logged to results/tables/attrition.csv:

  1. within-LAERS      keep the highest `isr` per case -- follow-ups get a new
                       isr, so the highest is the current version
  2. within-FAERS      keep the highest `caseversion` per caseid
  3. cross-era bridge  LAERS `case` and FAERS `caseid` are the SAME id space
                       (verified, see below), so a case reported before 2012Q4
                       and revised after appears in both. Keep the FAERS record.
  4. deleted cases     drop the 229,233 case ids FDA has withdrawn
  5. near-duplicates   drop distinct case ids that are evidently the same report
                       submitted through two channels

Why stage 3 is applied
----------------------
The plan treated the shared id space as an assumption to verify rather than a
fact. 82,342 case ids appear in both eras -- 2.7% of LAERS cases, which is
consistent either with a shared numbering where few cases span the boundary, or
with two independent numberings that happen to occupy overlapping ranges.

Comparing demographics on those overlapping ids against a chance baseline
settles it:

                    event_dt   sex     age    all three
    matched ids       33.3%   85.2%   54.2%     26.0%
    chance baseline    0.0%   38.8%    0.5%      0.0%

Agreement far above chance on fields that would be unrelated under independent
numbering. (It is not 100% because follow-up versions revise these fields and
many LAERS records leave event_dt blank -- but 33% against 0% is unambiguous.)
So the id spaces are shared and stage 3 is required; skipping it would double
count 82,342 cases.

Near-duplicate rule
-------------------
FDA deduplicates on caseid only, so the same patient reported independently by a
manufacturer and a physician remains two cases with two ids. The fingerprint is
event date, sex, age in years, country, the set of verbatim drug names, and the
set of reported PTs. Verbatim drug names are deliberate: two submissions of the
same report carry the same strings, and normalising first would merge cases that
differ only in how a drug was spelled.

Eligibility is by required fields, not by a count of populated ones. The first
attempt used "any 4 of 6 populated" and removed 14.5% of all cases, with a
largest group of 9,270 -- a collision among sparse records, not a report
submitted 9,270 times. A count treats country as evidence equal to event date,
and country is nearly constant, so records missing event_dt and age collapsed
wholesale. Every one of the largest groups sat exactly at the threshold.

    rule                  eligible   removed   rate  max group  cases in >100
    any 4 of 6          18,903,267 2,980,676  14.5%      9,270        762,456
    any 5 of 6          13,226,932   914,924   4.4%        775         32,716
    all 6                8,052,665   288,951   1.4%         36              0
    event+drug+pt       10,349,201   486,373   2.4%        775         25,829
    event+age+drug+pt    8,334,929   294,307   1.4%         36              0

The primary rule requires event_dt, age, the drug set and the PT set. It covers
more cases than demanding all six fields while producing the same maximum group
size and no group above 100. The looser event+drug+pt rule is reported as a
sensitivity analysis.

Cases that are not eligible are KEPT. Duplicates inflate exactly the counts a
DDI signal rests on, so failing to remove them is not harmless -- but a false
merge destroys a real report, and 12M cases simply lack the fields needed to
judge. The conservative direction is to keep.

Set membership is compared by order-independent hashes (xor and sum of per-value
hashes, plus the element count) rather than sorted concatenated strings.
string_agg(DISTINCT ... ORDER BY ...) over 100M drug rows exhausted a 10GB
budget; the hashes identify the same set without materialising it.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys

import duckdb

from faers_ddi import config as cfg

log = logging.getLogger("dedup")

# FAERS age_cod -> years. Blank is treated as years, which is the dominant
# convention in the files and matters only for fingerprinting.
AGE_FACTORS = {
    "DEC": 10.0, "YR": 1.0, "MON": 1.0 / 12, "WK": 1.0 / 52.1775,
    "DY": 1.0 / 365.25, "HR": 1.0 / 8766.0,
}


def _glob(table: str) -> str:
    return str(cfg.path("parquet") / table / "*.parquet")


def _age_case_sql(column_age: str, column_cod: str) -> str:
    branches = " ".join(
        f"WHEN upper(trim({column_cod})) = '{code}' THEN {factor}"
        for code, factor in AGE_FACTORS.items()
    )
    return (
        f"CASE WHEN try_cast({column_age} AS DOUBLE) IS NULL THEN NULL "
        f"ELSE round(try_cast({column_age} AS DOUBLE) * "
        # A searched CASE takes boolean branches, so the blank/missing code has
        # to be an explicit predicate rather than a bare '' literal.
        f"(CASE {branches} "
        f"WHEN coalesce(trim({column_cod}), '') = '' THEN 1.0 "
        f"ELSE NULL END), 1) END"
    )


def build(con: duckdb.DuckDBPyConnection) -> list[dict]:
    attrition: list[dict] = []

    def record(stage: str, remaining: int, removed: int, note: str) -> None:
        attrition.append({
            "stage": stage, "cases_remaining": remaining,
            "removed": removed, "note": note,
        })
        log.info("%-22s remaining=%-12s removed=%-10s %s",
                 stage, f"{remaining:,}", f"{removed:,}", note)

    demo_glob = _glob("demo")
    con.execute(f"""
        CREATE OR REPLACE VIEW demo_raw AS
        SELECT * FROM read_parquet('{demo_glob}', union_by_name=true)
    """)

    total_rows = con.execute("SELECT count(*) FROM demo_raw").fetchone()[0]
    record("0_demo_rows", total_rows, 0, "raw DEMO rows across 90 quarters")

    age_expr = _age_case_sql("age", "age_cod")
    # occr_country is FAERS-era; reporter_country appears in LAERS from 2005Q3.
    # Neither exists everywhere, so coalesce and accept blanks.
    country = "coalesce(nullif(trim(occr_country), ''), nullif(trim(reporter_country), ''), '')"

    # Stage 1+2: one winner per (era, case_id).
    con.execute(f"""
        CREATE OR REPLACE TABLE era_cases AS
        WITH ranked AS (
            SELECT
                case_id, report_id, era, quarter,
                try_cast(caseversion AS BIGINT) AS caseversion,
                trim(event_dt) AS event_dt,
                trim(sex) AS sex,
                {age_expr} AS age_years,
                {country} AS country,
                CASE WHEN era = 'laers' THEN 'laers' ELSE 'faers' END AS era_group,
                row_number() OVER (
                    -- Partition on the era GROUP, not on `era`. There are three
                    -- eras but only two id spaces: faers_early and faers_modern
                    -- share the caseid space, so partitioning by `era` dedupes
                    -- them separately and leaves ~98k cases counted twice for
                    -- stage 3 to mop up -- which works, but makes the stage
                    -- counts mean something other than what they claim.
                    PARTITION BY CASE WHEN era = 'laers' THEN 'laers' ELSE 'faers' END,
                                 case_id
                    ORDER BY
                        -- LAERS has no caseversion; the highest isr is current.
                        -- FAERS ranks on caseversion first, then primaryid, then
                        -- the quarter it was last seen in.
                        CASE WHEN era = 'laers' THEN NULL
                             ELSE try_cast(caseversion AS BIGINT) END DESC NULLS LAST,
                        report_id DESC,
                        quarter DESC
                ) AS rn
            FROM demo_raw
            WHERE case_id IS NOT NULL
        )
        SELECT * EXCLUDE (rn) FROM ranked WHERE rn = 1
    """)

    laers_before, faers_before = con.execute("""
        SELECT count(*) FILTER (WHERE era = 'laers'),
               count(*) FILTER (WHERE era <> 'laers') FROM demo_raw WHERE case_id IS NOT NULL
    """).fetchone()
    laers_after, faers_after = con.execute("""
        SELECT count(*) FILTER (WHERE era_group = 'laers'),
               count(*) FILTER (WHERE era_group = 'faers') FROM era_cases
    """).fetchone()
    record("1_within_laers", laers_after, laers_before - laers_after,
           "kept highest isr per case")
    record("2_within_faers", faers_after, faers_before - faers_after,
           "kept highest caseversion per caseid")

    # Stage 3: collapse the shared id space, preferring the FAERS record.
    con.execute("""
        CREATE OR REPLACE TABLE cases AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY case_id
                ORDER BY CASE WHEN era = 'laers' THEN 1 ELSE 0 END, quarter DESC
            ) AS rn
            FROM era_cases
        ) WHERE rn = 1
    """)
    after_bridge = con.execute("SELECT count(*) FROM cases").fetchone()[0]
    record("3_cross_era_bridge", after_bridge, (laers_after + faers_after) - after_bridge,
           "ids present in both eras collapsed; FAERS record kept")

    # Stage 4: FDA-withdrawn cases.
    deleted_path = cfg.path("parquet").parent / "deleted_cases.parquet"
    if deleted_path.exists():
        con.execute(f"""
            CREATE OR REPLACE TABLE cases AS
            SELECT c.* FROM cases c
            WHERE NOT EXISTS (
                SELECT 1 FROM read_parquet('{deleted_path}') d WHERE d.case_id = c.case_id)
        """)
        after_deleted = con.execute("SELECT count(*) FROM cases").fetchone()[0]
        record("4_deleted_cases", after_deleted, after_bridge - after_deleted,
               "FDA-withdrawn case ids removed")
    else:
        after_deleted = after_bridge
        record("4_deleted_cases", after_deleted, 0, "SKIPPED -- deleted_cases.parquet missing")

    # Stage 5: near-duplicates across distinct case ids.
    conf = cfg.load_config()["dedup"]
    con.execute(f"""
        CREATE OR REPLACE TABLE drug_sets AS
        WITH v AS (
            SELECT DISTINCT era, report_id, upper(trim(drugname)) AS value
            FROM read_parquet('{_glob("drug")}') WHERE trim(drugname) <> ''
        )
        SELECT era, report_id, count(*) AS n,
               bit_xor(hash(value)) AS x, sum(hash(value)) AS s
        FROM v GROUP BY 1, 2
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE reac_sets AS
        WITH v AS (
            SELECT DISTINCT era, report_id, upper(trim(pt)) AS value
            FROM read_parquet('{_glob("reac")}') WHERE trim(pt) <> ''
        )
        SELECT era, report_id, count(*) AS n,
               bit_xor(hash(value)) AS x, sum(hash(value)) AS s
        FROM v GROUP BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE fingerprints AS
        SELECT
            c.case_id, c.era, c.report_id,
            c.event_dt <> ''          AS has_event_dt,
            c.sex <> ''               AS has_sex,
            c.age_years IS NOT NULL   AS has_age_years,
            c.country <> ''           AS has_country,
            d.n IS NOT NULL           AS has_drug_set,
            r.n IS NOT NULL           AS has_pt_set,
            md5(concat_ws('~', c.event_dt, c.sex,
                          coalesce(cast(c.age_years AS VARCHAR), ''), c.country,
                          coalesce(cast(d.n AS VARCHAR), ''), coalesce(cast(d.x AS VARCHAR), ''),
                          coalesce(cast(d.s AS VARCHAR), ''),
                          coalesce(cast(r.n AS VARCHAR), ''), coalesce(cast(r.x AS VARCHAR), ''),
                          coalesce(cast(r.s AS VARCHAR), ''))) AS fingerprint
        FROM cases c
        LEFT JOIN drug_sets d ON d.era = c.era AND d.report_id = c.report_id
        LEFT JOIN reac_sets r ON r.era = c.era AND r.report_id = c.report_id
    """)

    def eligibility(fields: list[str]) -> str:
        return " AND ".join(f"has_{f}" for f in fields)

    primary = eligibility(conf["fingerprint_required"])
    con.execute(f"""
        CREATE OR REPLACE TABLE cases_deduped AS
        SELECT c.* FROM cases c
        JOIN (
            SELECT case_id FROM (
                SELECT case_id, row_number() OVER (
                    -- Ineligible cases are partitioned alone, so they always
                    -- survive rather than being merged on a sparse fingerprint.
                    PARTITION BY CASE WHEN {primary} THEN fingerprint
                                      ELSE 'keep:' || cast(case_id AS VARCHAR) END
                    ORDER BY case_id
                ) AS rn
                FROM fingerprints
            ) WHERE rn = 1
        ) keep USING (case_id)
    """)

    final = con.execute("SELECT count(*) FROM cases_deduped").fetchone()[0]
    record("5_near_duplicates", final, after_deleted - final,
           "fingerprint match, requires " + "+".join(conf["fingerprint_required"]))

    # Stage 6: one case per report. Downstream stages join DRUG and REAC on
    # (era, report_id), so two surviving cases sharing a report_id would have
    # the same drug and reaction rows counted twice -- inflating exactly the
    # co-occurrence counts a DDI signal is computed from. 769 LAERS reports
    # appear in consecutive quarters under a reassigned case number (same isr,
    # same patient, different `case`). Keep the later quarter's record, which
    # carries the corrected case number.
    con.execute("""
        CREATE OR REPLACE TABLE cases_deduped AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY era, report_id ORDER BY quarter DESC, case_id DESC
            ) AS rn
            FROM cases_deduped
        ) WHERE rn = 1
    """)
    after_reports = con.execute("SELECT count(*) FROM cases_deduped").fetchone()[0]
    record("6_one_case_per_report", after_reports, final - after_reports,
           "reports appearing under two case numbers; later quarter kept")

    # Sensitivity: how much does the eligibility rule move the final count?
    sensitivity = eligibility(conf["fingerprint_required_sensitivity"])
    alt_removed = con.execute(f"""
        WITH g AS (SELECT fingerprint, count(*) AS n FROM fingerprints
                   WHERE {sensitivity} GROUP BY 1)
        SELECT coalesce(sum(n) - count(*), 0), coalesce(max(n), 0) FROM g
    """).fetchone()
    attrition.append({
        "stage": "5b_near_duplicates_sensitivity",
        "cases_remaining": after_deleted - alt_removed[0],
        "removed": alt_removed[0],
        "note": ("SENSITIVITY ONLY, not applied: requires "
                 + "+".join(conf["fingerprint_required_sensitivity"])
                 + f"; largest group {alt_removed[1]:,}"),
    })
    log.info("%-22s remaining=%-12s removed=%-10s %s",
             "5b_sensitivity", f"{after_deleted - alt_removed[0]:,}",
             f"{alt_removed[0]:,}", "not applied; reported for comparison")
    return attrition


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="8GB")
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "dedup.log"),
                  logging.StreamHandler(sys.stdout)],
        force=True,
    )

    db_path = cfg.path("duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute(f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'")

    attrition = build(con)

    out = cfg.path("tables") / "attrition.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["stage", "cases_remaining", "removed", "note"])
        writer.writeheader()
        writer.writerows(attrition)
    log.info("attrition -> %s", out)

    export = cfg.path("parquet").parent / "cases_deduped.parquet"
    con.execute(f"COPY cases_deduped TO '{export}' (FORMAT parquet, COMPRESSION zstd)")
    log.info("deduplicated cases -> %s", export)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
