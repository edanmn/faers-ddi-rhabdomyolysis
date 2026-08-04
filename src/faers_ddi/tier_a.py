"""Tier A -- can the pipeline recover interactions already known to be real?

This is the gate on everything downstream. A pipeline that cannot find
simvastatin + amiodarone has not earned the right to report a novel finding, and
Phase 9's screen does not run until this passes.

Recovery is judged on Omega_025 > 0 against the core tier, with the broad tier
reported alongside. Core is specific but small: 42,058 cases across the whole
database, so an established pair with modest co-reporting may simply lack the
counts, and the shrinkage in Omega_025 is designed to withhold a signal exactly
there. A pair that fires on broad but not core is underpowered, not refuted.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys

import duckdb

from faers_ddi import config as cfg
from faers_ddi import contingency

log = logging.getLogger("tier_a")


def load_positive_controls() -> list[dict]:
    path = cfg.resolve(cfg.load_config()["controls"]["positive_file"])
    with path.open() as fh:
        return [r for r in csv.DictReader(fh) if r["drug_a"].strip()]


def evaluate(con: duckdb.DuckDBPyConnection, tier: str, policy: str,
             rebuild: bool = True) -> dict:
    """Score the positive controls under both nulls.

    `rebuild=False` leaves case_drugs and drug_marginals as the caller built
    them. The polypharmacy cap sweep in `faers_ddi.audit` needs that: rebuilding
    here would silently restore the configured 20-drug cap and every arm of the
    sweep would return the same numbers.
    """
    controls = load_positive_controls()
    drugs = sorted({r["drug_a"].strip().upper() for r in controls}
                   | {r["drug_b"].strip().upper() for r in controls})

    if rebuild:
        contingency.build_case_drugs(con, policy)
        contingency.drug_marginals(con, tier)
    contingency.pair_counts(con, drugs, tier, min_pair=1)
    scored = {(r["drug_a"], r["drug_b"]): r for r in contingency.score(con, tier)}

    results = []
    for control in controls:
        a = control["drug_a"].strip().upper()
        b = control["drug_b"].strip().upper()
        key = (a, b) if a < b else (b, a)
        row = scored.get(key)
        results.append({
            "drug_a": a, "drug_b": b,
            "mechanism": control["mechanism"],
            "expected_strength": control["expected_strength"],
            "n_ab": row["n_ab"] if row else 0,
            "n_abz": row["n_abz"] if row else 0,
            "expected": round(row["expected"], 2) if row else None,
            "omega": round(row["omega"], 3) if row else None,
            "omega_lower": round(row["omega_lower"], 3) if row else None,
            "additive_expected": round(row["additive_expected"], 2) if row else None,
            "omega_add": round(row["omega_add"], 3) if row else None,
            "omega_add_lower": round(row["omega_add_lower"], 3) if row else None,
            "naive_log2_oe": round(row["naive_log2_oe"], 3) if row else None,
            # The gate is judged on the additive null.
            "signal": bool(row and row["omega_add_lower"] > 0),
            "signal_multiplicative": bool(row and row["omega_lower"] > 0),
        })
    return {"tier": tier, "policy": policy, "results": results}


def evaluate_all(con: duckdb.DuckDBPyConnection,
                 policies=("primary", "sensitivity"),
                 tiers=("core", "broad")) -> list[dict]:
    """Every tier/policy combination, tagged, in one pass."""
    rows = []
    for policy in policies:
        for tier in tiers:
            for row in evaluate(con, tier, policy)["results"]:
                rows.append({**row, "tier": tier, "policy": policy})
    return rows


def write_results_csv(rows: list[dict]):
    """Single writer for tier_a_results.csv.

    This table used to be written only by `python -m faers_ddi.tier_a`, a
    separate invocation from the one that wrote canonical_numbers.json. The two
    drifted: all 16 Omega values disagreed in the third decimal, so Figure 2
    (drawn from canonical `correlation_points`) disagreed with the results
    table, while the manuscript claimed byte-identical reruns. run_analysis now
    calls this too, so one run produces both artifacts.
    """
    out = cfg.path("tables") / "tier_a_results.csv"
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "tier_a.log"),
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

    all_rows = []
    for policy in ("primary", "sensitivity"):
      for tier in ("core", "broad"):
        outcome = evaluate(con, tier, policy)
        n_total, n_event = contingency.totals(con, tier)
        log.info("=== policy=%s tier=%s  n_total=%s  n_event=%s ===",
                 policy, tier, f"{n_total:,}", f"{n_event:,}")
        log.info("%-26s %7s %6s %8s %7s %8s %7s %7s",
                 "pair", "n_ab", "n_abz", "E_add", "om_add", "om_add025",
                 "omega", "signal")
        recovered = 0
        for row in outcome["results"]:
            row["tier"] = tier
            row["policy"] = policy
            all_rows.append(row)
            recovered += row["signal"]
            log.info("%-26s %7s %6s %8s %7s %8s %7s %7s",
                     f"{row['drug_a'][:11]}+{row['drug_b'][:11]}",
                     f"{row['n_ab']:,}", f"{row['n_abz']:,}",
                     row["additive_expected"], row["omega_add"],
                     row["omega_add_lower"], row["omega"],
                     "YES" if row["signal"] else "-")
        multiplicative = sum(r["signal_multiplicative"] for r in outcome["results"])
        log.info(">>> recovered %d/%d additive, %d/%d multiplicative  policy=%s tier=%s",
                 recovered, len(outcome["results"]), multiplicative,
                 len(outcome["results"]), policy, tier)

    log.info("tier A results -> %s", write_results_csv(all_rows))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
