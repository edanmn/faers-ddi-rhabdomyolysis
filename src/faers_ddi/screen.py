"""Tier C -- the screen.

All pairs among the drugs most co-reported with myotoxicity, scored against the
additive null and ranked by the calibrated lower bound.

This runs only because Tier A passed (12/16 controls, 12/14 with adequate power)
and Tier B measured the false-positive rate at 6.2%, calibrating the threshold to
+0.305 for a 5% rate.

Reading the output
------------------
This is a hypothesis generator, not a set of findings. With ~20,000 pairs tested
at a 5% false-positive rate, on the order of a thousand pairs are expected above
threshold *if none of them were real*. The ranking is what carries information;
membership in the list does not.

Each pair is annotated by how much prior support exists, which is what makes the
output triageable:

  positive_control   in the Tier A set
  known_pair         both drugs are on the curated myotoxicity list -- the
                     established interaction space
  plausible          exactly one drug is on that list; the usual shape of a real
                     but undocumented interaction, and also the usual shape of
                     confounding by indication
  unsupported        neither drug is implicated; most likely noise or a shared
                     indication, occasionally something new

The `plausible` band is where anything worth following up will be. The extremes
are uninformative in opposite directions: `known_pair` hits are rediscoveries,
and `unsupported` hits at this false-positive rate are dominated by chance.
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
from faers_ddi.tier_a import load_positive_controls
from faers_ddi.tier_b import MYOTOXICITY_IMPLICATED


log = logging.getLogger("screen")


def screen_drugs(con: duckdb.DuckDBPyConnection, top_n: int) -> list[str]:
    """Drugs ranked by how often they are co-reported with the event.

    Ranking on event co-reports rather than overall report volume keeps the
    screen focused: a very common drug that never appears with myotoxicity
    contributes nothing but pairs.
    """
    # The tie-break on `ingredient` is required, not cosmetic. Many drugs share
    # a low event count, so ordering on n_drug_event alone leaves the selection
    # at the mercy of scan order: two runs of the top-400 screen selected
    # different drug sets and produced 53,307 vs 53,535 pairs.
    return [r[0] for r in con.execute(f"""
        SELECT ingredient FROM drug_marginals
        WHERE n_drug_event > 0
        ORDER BY n_drug_event DESC, ingredient
        LIMIT {top_n}
    """).fetchall()]


def annotate(rows: list[dict], positive_keys: set) -> None:
    for row in rows:
        a, b = row["drug_a"], row["drug_b"]
        implicated = (a in MYOTOXICITY_IMPLICATED) + (b in MYOTOXICITY_IMPLICATED)
        if (a, b) in positive_keys:
            support = "positive_control"
        elif implicated == 2:
            support = "known_pair"
        elif implicated == 1:
            support = "plausible"
        else:
            support = "unsupported"
        row["support"] = support


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    parser.add_argument("--tier", default=None)
    parser.add_argument("--policy", default="primary")
    parser.add_argument("--top-n", type=int, default=None)
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "screen.log"),
                  logging.StreamHandler(sys.stdout)],
        force=True,
    )

    conf = cfg.load_config()
    analysis = conf["analysis"]
    tier = args.tier or conf["event"]["primary_tier"]
    top_n = args.top_n or analysis["screen"]["top_n_drugs"]
    threshold = analysis["omega"]["signal_threshold"]
    min_pair = analysis["min_co_reports"]

    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    contingency.build_case_drugs(con, args.policy)
    contingency.drug_marginals(con, tier)
    drugs = screen_drugs(con, top_n)
    log.info("screening %d drugs -> %d candidate pairs, tier=%s policy=%s",
             len(drugs), len(drugs) * (len(drugs) - 1) // 2, tier, args.policy)

    contingency.pair_counts(con, drugs, tier, min_pair=min_pair)
    rows = contingency.score(con, tier)
    log.info("%d pairs met the minimum of %d co-reports", len(rows), min_pair)

    positive_keys = {
        tuple(sorted((p["drug_a"].strip().upper(), p["drug_b"].strip().upper())))
        for p in load_positive_controls()
    }
    annotate(rows, positive_keys)
    rows.sort(key=lambda r: -r["omega_add_lower"])

    lower = np.array([r["omega_add_lower"] for r in rows], dtype=float)
    n_signal = int((lower > threshold).sum())
    log.info("=== %d pairs above the calibrated threshold (+%.3f), %.1f%% of tested ===",
             n_signal, threshold, 100 * n_signal / len(rows))
    # The screen's own false-positive expectation, from the Tier B rate. Stated
    # explicitly because "N pairs signalled" reads as a discovery count and is
    # not one.
    log.info("Tier B measured 5%% false positives at this threshold, so ~%d of "
             "these are expected by chance alone", int(round(0.05 * len(rows))))

    by_support: dict[str, list[dict]] = {}
    for row in rows:
        by_support.setdefault(row["support"], []).append(row)
    log.info("%-18s %8s %10s %9s", "support", "tested", "signalled", "rate")
    for support in ("positive_control", "known_pair", "plausible", "unsupported"):
        group = by_support.get(support, [])
        if not group:
            continue
        hits = sum(r["omega_add_lower"] > threshold for r in group)
        log.info("%-18s %8d %10d %8.1f%%",
                 support, len(group), hits, 100 * hits / len(group))

    out = cfg.path("tables") / "screen_results.csv"
    fields = ["drug_a", "drug_b", "support", "n_ab", "n_abz", "additive_expected",
              "omega_add", "omega_add_lower", "expected", "omega", "omega_lower",
              "naive_log2_oe", "n_a", "n_az", "n_b", "n_bz"]
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("full ranking -> %s", out)

    log.info("--- top 15 overall ---")
    log.info("%-40s %7s %6s %8s %9s %s", "pair", "n_ab", "n_abz", "E_add",
             "om025", "support")
    for row in rows[:15]:
        log.info("%-40s %7s %6s %8.1f %9.2f %s",
                 f"{row['drug_a'][:19]}+{row['drug_b'][:19]}",
                 f"{row['n_ab']:,}", f"{row['n_abz']:,}",
                 row["additive_expected"], row["omega_add_lower"], row["support"])
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
