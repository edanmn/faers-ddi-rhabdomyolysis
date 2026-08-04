"""Phase 11 -- triage panel for individual pairs.

A rank in the screen is not evidence. This attaches, for each pair, the three
diagnostics that actually separate pharmacology from artefact:

  era stability     Omega_add,025 computed separately in 2004-2012, 2013-2018 and
                    2019-2026. A genuine pharmacokinetic interaction does not
                    switch on and off with reporting fashion; a notoriety
                    artefact appears in one era only. This is the main reason
                    the study uses the full 22-year history rather than a recent
                    slice.

  overdose fraction Share of the pair's event cases carrying an overdose or
                    impaired-consciousness PT, against a 13.2% background.
                    Rhabdomyolysis after prolonged immobilisation from an
                    overdose is not a drug interaction. Established interactions
                    measured 0.03-0.7x background; the clearest artefact in the
                    Phase 9 screen measured 4.9x.

  top indications   What the drugs were being given for, from the INDI table.
                    Confounding by indication is invisible to every statistic in
                    this pipeline and visible here immediately -- a pair whose
                    event cases are all indicated for muscle symptoms is
                    describing its own denominator.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys

import duckdb
import numpy as np

from faers_ddi import config as cfg
from faers_ddi import contingency
from faers_ddi import omega as om
from faers_ddi.tier_a import load_positive_controls

log = logging.getLogger("triage")

OVERDOSE_PTS = [
    "OVERDOSE", "INTENTIONAL OVERDOSE", "ACCIDENTAL OVERDOSE", "DRUG TOXICITY",
    "TOXICITY TO VARIOUS AGENTS", "POISONING", "DRUG ABUSE", "COMPLETED SUICIDE",
    "SUICIDE ATTEMPT", "INTENTIONAL SELF-INJURY", "LOSS OF CONSCIOUSNESS",
    "COMA", "RESPIRATORY DEPRESSION", "UNRESPONSIVE TO STIMULI",
]


def prepare(con: duckdb.DuckDBPyConnection, tier: str) -> float:
    """Build the auxiliary tables and return the background overdose fraction."""
    reac = str(cfg.path("parquet") / "reac" / "*.parquet")
    indi = str(cfg.path("parquet") / "indi" / "*.parquet")
    pts = ", ".join(f"'{p}'" for p in OVERDOSE_PTS)

    con.execute(f"""
        CREATE OR REPLACE TABLE case_overdose AS
        SELECT c.case_id FROM cases_deduped c
        JOIN read_parquet('{reac}') r ON r.era = c.era AND r.report_id = c.report_id
        WHERE upper(trim(r.pt)) IN ({pts}) GROUP BY 1
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE case_indications AS
        SELECT c.case_id, upper(trim(i.indi_pt)) AS indication
        FROM cases_deduped c
        JOIN read_parquet('{indi}') i ON i.era = c.era AND i.report_id = c.report_id
        WHERE trim(i.indi_pt) <> '' GROUP BY 1, 2
    """)
    bins = cfg.load_config()["analysis"]["era_stratification"]
    cases = " UNION ALL ".join(
        f"SELECT case_id, '{b['name']}' AS era_bin FROM cases_deduped "
        f"WHERE quarter >= '{b['start']}' AND quarter <= '{b['end']}'"
        for b in bins
    )
    con.execute(f"CREATE OR REPLACE TABLE case_era_bin AS {cases}")

    return con.execute(f"""
        SELECT avg(CASE WHEN o.case_id IS NOT NULL THEN 1.0 ELSE 0 END)
        FROM case_events e LEFT JOIN case_overdose o USING (case_id)
        WHERE e.is_{tier}
    """).fetchone()[0]


def era_stability(con: duckdb.DuckDBPyConnection, a: str, b: str, tier: str) -> dict:
    """Omega_add,025 for one pair within each era bin."""
    out = {}
    for row in con.execute(f"""
        WITH pair AS (
            SELECT x.case_id FROM case_drugs x JOIN case_drugs y USING (case_id)
            WHERE x.ingredient = ? AND y.ingredient = ?
        )
        SELECT eb.era_bin,
               count(*) FILTER (WHERE k.case_id IS NOT NULL) AS n_ab,
               count(*) FILTER (WHERE k.case_id IS NOT NULL AND f.is_{tier}) AS n_abz,
               count(*) AS n_total,
               count(*) FILTER (WHERE f.is_{tier}) AS n_event,
               count(*) FILTER (WHERE da.case_id IS NOT NULL) AS n_a,
               count(*) FILTER (WHERE da.case_id IS NOT NULL AND f.is_{tier}) AS n_az,
               count(*) FILTER (WHERE db.case_id IS NOT NULL) AS n_b,
               count(*) FILTER (WHERE db.case_id IS NOT NULL AND f.is_{tier}) AS n_bz
        FROM case_flags f
        JOIN case_era_bin eb USING (case_id)
        LEFT JOIN pair k USING (case_id)
        LEFT JOIN (SELECT case_id FROM case_drugs WHERE ingredient = ?) da USING (case_id)
        LEFT JOIN (SELECT case_id FROM case_drugs WHERE ingredient = ?) db USING (case_id)
        GROUP BY 1
    """, [a, b, a, b]).fetchall():
        era_bin, n_ab, n_abz, n_total, n_event, n_a, n_az, n_b, n_bz = row
        if not (n_ab and n_a and n_b and n_event):
            out[era_bin] = None
            continue
        t = om.Triple(n_abz, n_ab, n_az, n_bz, n_a, n_b, n_event, n_total)
        out[era_bin] = {
            "n_ab": n_ab, "n_abz": n_abz,
            "omega_add_lower": round(om.omega_additive_quantile(t), 3),
        }
    return out


def panel(con: duckdb.DuckDBPyConnection, pairs: list[tuple], tier: str,
          baseline_overdose: float) -> list[dict]:
    rows = []
    bin_names = [b["name"] for b in cfg.load_config()["analysis"]["era_stratification"]]
    for a, b in pairs:
        overdose = con.execute(f"""
            WITH pair AS (
                SELECT x.case_id FROM case_drugs x JOIN case_drugs y USING (case_id)
                WHERE x.ingredient = ? AND y.ingredient = ?
            )
            SELECT count(*), avg(CASE WHEN o.case_id IS NOT NULL THEN 1.0 ELSE 0 END)
            FROM pair p JOIN case_events e USING (case_id)
            LEFT JOIN case_overdose o USING (case_id)
            WHERE e.is_{tier}
        """, [a, b]).fetchone()
        indications = con.execute(f"""
            WITH pair AS (
                SELECT x.case_id FROM case_drugs x JOIN case_drugs y USING (case_id)
                WHERE x.ingredient = ? AND y.ingredient = ?
            )
            SELECT i.indication, count(*) AS n
            FROM pair p JOIN case_events e USING (case_id)
            JOIN case_indications i USING (case_id)
            WHERE e.is_{tier}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 3
        """, [a, b]).fetchall()

        eras = era_stability(con, a, b, tier)
        present = [n for n in bin_names
                   if eras.get(n) and eras[n]["omega_add_lower"] > 0]
        row = {
            "drug_a": a, "drug_b": b,
            "event_cases": overdose[0],
            "overdose_fraction": round(overdose[1], 4) if overdose[0] else None,
            "overdose_vs_background": (round(overdose[1] / baseline_overdose, 2)
                                       if overdose[0] and baseline_overdose else None),
            "eras_with_signal": len(present),
            "eras_signalled": ";".join(present),
            "top_indications": ";".join(f"{i}({n})" for i, n in indications),
        }
        for name in bin_names:
            row[f"om025_{name}"] = eras.get(name, {}).get("omega_add_lower") if eras.get(name) else None
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(cfg.path("logs") / "triage.log"),
                  logging.StreamHandler(sys.stdout)], force=True)

    conf = cfg.load_config()
    tier = conf["event"]["primary_tier"]
    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    contingency.build_case_drugs(con, "primary")
    contingency.drug_marginals(con, tier)
    baseline = prepare(con, tier)
    log.info("background overdose fraction among %s event cases: %.1f%%",
             tier, 100 * baseline)

    with (cfg.path("tables") / "screen_results.csv").open() as fh:
        screened = sorted(csv.DictReader(fh),
                          key=lambda r: -float(r["omega_add_lower"]))
    pairs = [(r["drug_a"], r["drug_b"]) for r in screened[:args.top]]
    controls = [(min(c["drug_a"].upper(), c["drug_b"].upper()),
                 max(c["drug_a"].upper(), c["drug_b"].upper()))
                for c in load_positive_controls()]
    seen, ordered = set(), []
    for pair in pairs + controls:
        if pair not in seen:
            seen.add(pair)
            ordered.append(pair)

    rows = panel(con, ordered, tier, baseline)
    support = {(r["drug_a"], r["drug_b"]): r["support"] for r in screened}
    for row in rows:
        row["support"] = support.get((row["drug_a"], row["drug_b"]), "not_screened")

    out = cfg.path("tables") / "triage_panel.csv"
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    log.info("%-34s %6s %8s %7s  %s", "pair", "cases", "OD/base", "eras", "support")
    for row in sorted(rows, key=lambda r: (-r["eras_with_signal"],
                                           r["overdose_vs_background"] or 99)):
        log.info("%-34s %6s %8s %4d/3  %s",
                 f"{row['drug_a'][:16]}+{row['drug_b'][:16]}",
                 row["event_cases"],
                 f"{row['overdose_vs_background']:.2f}x" if row["overdose_vs_background"] else "-",
                 row["eras_with_signal"], row["support"])
    log.info("triage panel -> %s", out)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
