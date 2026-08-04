"""Tier B -- negative controls, to measure the false-positive rate.

Tier A shows the pipeline can find interactions that are real. It says nothing
about how often it finds interactions that are not. Without that, the Tier C
screen has no interpretable threshold: Omega_add,025 > 0 is a nominal 2.5%
criterion under a null that assumes away confounding by indication, channelling
and co-prescription, none of which are in the model.

Design
------
Negative controls are GENERATED from criteria, not hand-picked, because a
hand-picked null set is chosen -- consciously or not -- to be easy.

Pairs are frequency-matched to the positive controls on co-report count, since
the shrinkage in Omega_025 makes the false-positive rate a function of count. An
unmatched null set drawn from the long tail would be dominated by pairs too
small to signal at all, and would report a flatteringly low rate.

Two strata, and the split is the point:

  easy  neither drug is individually associated with the event (RR < 2)
  hard  at least one drug is (RR >= 2), but the pair has no known interaction

The hard stratum is the realistic case. Most of what a screen encounters is a
pair containing one genuinely myotoxic drug and one bystander that happens to be
co-prescribed with it. If the false-positive rate is measured only on the easy
stratum it will look excellent and mean nothing.

What could not be implemented
-----------------------------
The configured criteria call for excluding pairs documented in DrugBank and
pairs sharing an ATC level-3 class. Neither resource is available yet (the
DrugBank academic licence is pending and no ATC mapping is in the repository), so
exclusion falls back on a hand-curated list of agents implicated in
drug-induced myotoxicity.

That substitution matters and is not neutral. Some generated "negatives" will be
genuine but undocumented interactions, which inflates the measured false-positive
rate. The bias runs toward a stricter calibrated threshold, which is the safe
direction, but the measured rate is an upper bound rather than an estimate.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys

import duckdb
import numpy as np

from faers_ddi import config as cfg
from faers_ddi import contingency
from faers_ddi.tier_a import load_positive_controls

log = logging.getLogger("tier_b")

# Agents with a recognised role in drug-induced myotoxicity, either as a direct
# myotoxin or as a perpetrator acting through CYP3A4, OATP1B1, P-gp or
# glucuronidation. Curated by hand as a stand-in for a DDI reference database --
# see the module docstring. Erring wide is deliberate: excluding a drug that did
# not need excluding costs a candidate pair, whereas admitting a real interactor
# into the null set corrupts the false-positive rate.
MYOTOXICITY_IMPLICATED = {
    # statins
    "SIMVASTATIN", "ATORVASTATIN", "ROSUVASTATIN", "PRAVASTATIN", "LOVASTATIN",
    "FLUVASTATIN", "PITAVASTATIN", "CERIVASTATIN",
    # other lipid agents
    "GEMFIBROZIL", "FENOFIBRATE", "FENOFIBRIC ACID", "BEZAFIBRATE",
    "CIPROFIBRATE", "NIACIN", "EZETIMIBE",
    # direct myotoxins
    "COLCHICINE", "DAPTOMYCIN", "ZIDOVUDINE", "PROPOFOL", "HYDROXYCHLOROQUINE",
    "CHLOROQUINE", "PENICILLAMINE", "AMPHOTERICIN B",
    # CYP3A4 / P-gp / OATP1B1 perpetrators
    "CLARITHROMYCIN", "ERYTHROMYCIN", "AZITHROMYCIN", "TELITHROMYCIN",
    "ITRACONAZOLE", "KETOCONAZOLE", "FLUCONAZOLE", "VORICONAZOLE",
    "POSACONAZOLE", "RITONAVIR", "LOPINAVIR", "SAQUINAVIR", "INDINAVIR",
    "NELFINAVIR", "ATAZANAVIR", "DARUNAVIR", "COBICISTAT",
    "CYCLOSPORINE", "TACROLIMUS", "SIROLIMUS", "EVEROLIMUS",
    "AMIODARONE", "DRONEDARONE", "DILTIAZEM", "VERAPAMIL", "RANOLAZINE",
    "DANAZOL", "GRAPEFRUIT", "NEFAZODONE", "IMATINIB", "TICAGRELOR",
    # myopathy-associated by class
    "PREDNISONE", "PREDNISOLONE", "DEXAMETHASONE", "METHYLPREDNISOLONE",
    "INTERFERON ALFA", "INTERFERON BETA-1A", "INTERFERON BETA-1B",
    "RALTEGRAVIR", "DOLUTEGRAVIR", "BICTEGRAVIR",
}

EVENT_ASSOCIATED_RR = 2.0   # splits the easy and hard strata
MIN_DRUG_REPORTS = 1_000    # a drug must be common enough to pair up
LOG10_TOLERANCE = 0.5       # frequency match on co-report count


def candidate_drugs(con: duckdb.DuckDBPyConnection, top_n: int = 400) -> list[str]:
    return [r[0] for r in con.execute(f"""
        SELECT ingredient FROM drug_marginals
        WHERE n_drug >= {MIN_DRUG_REPORTS}
        ORDER BY n_drug DESC LIMIT {top_n}
    """).fetchall()]


def generate(con: duckdb.DuckDBPyConnection, tier: str,
             n_pairs: int | None, seed: int) -> list[dict]:
    conf = cfg.load_config()["controls"]["negative_generation"]
    n_total, n_event = contingency.totals(con, tier)
    baseline = n_event / n_total

    positives = load_positive_controls()
    positive_keys = {
        tuple(sorted((p["drug_a"].strip().upper(), p["drug_b"].strip().upper())))
        for p in positives
    }

    drugs = candidate_drugs(con)
    contingency.pair_counts(con, drugs, tier, min_pair=20)
    scored = contingency.score(con, tier)

    # Frequency-match to the positive controls' co-report counts.
    target_counts = [
        r["n_ab"] for r in scored
        if (r["drug_a"], r["drug_b"]) in positive_keys and r["n_ab"] > 0
    ]
    if not target_counts:
        raise RuntimeError("no positive control pairs found among candidates")
    target_logs = np.log10(np.array(target_counts, dtype=float))

    rr = {}
    for ingredient, n_drug, n_drug_event in con.execute(
        "SELECT ingredient, n_drug, n_drug_event FROM drug_marginals"
    ).fetchall():
        rr[ingredient] = (n_drug_event / n_drug) / baseline if n_drug else 0.0

    eligible = []
    for row in scored:
        a, b = row["drug_a"], row["drug_b"]
        if (a, b) in positive_keys:
            continue
        if a in MYOTOXICITY_IMPLICATED and b in MYOTOXICITY_IMPLICATED:
            continue
        if row["n_ab"] <= 0:
            continue
        distance = float(np.min(np.abs(target_logs - math.log10(row["n_ab"]))))
        if distance > LOG10_TOLERANCE:
            continue
        row["stratum"] = (
            "hard" if max(rr.get(a, 0), rr.get(b, 0)) >= EVENT_ASSOCIATED_RR else "easy"
        )
        row["rr_a"] = rr.get(a, 0.0)
        row["rr_b"] = rr.get(b, 0.0)
        eligible.append(row)

    rng = np.random.default_rng(seed)
    selected: list[dict] = []
    for stratum in ("easy", "hard"):
        # Sorted so any sample depends only on the seed. Belt and braces with
        # the ORDER BY in contingency.score -- a fixed seed applied to a pool in
        # nondeterministic order is not a fixed sample.
        pool = sorted((r for r in eligible if r["stratum"] == stratum),
                      key=lambda r: (r["drug_a"], r["drug_b"]))
        # n_pairs=None takes the ENTIRE eligible pool. That is the default, and
        # it matters: sampling 2,000 of 16,138 left the calibrated threshold at
        # the mercy of the draw, and two legitimate runs produced +0.092 and
        # +0.423 -- moving the era-stable set from 35 pairs to 20 and its
        # enrichment from 19.9x to 11.0x. Using the whole pool removes that
        # variance entirely and tightens the rule-of-three bound on the
        # era-stability false-positive rate by an order of magnitude.
        take = len(pool) if n_pairs is None else min(len(pool), n_pairs // 2)
        if take == len(pool):
            selected.extend(pool)
        elif take:
            for index in rng.choice(len(pool), size=take, replace=False):
                selected.append(pool[int(index)])
        log.info("stratum %-5s pool=%d selected=%d", stratum, len(pool), take)
    return selected


def summarise(selected: list[dict], threshold: float = 0.0) -> list[dict]:
    out = []
    for stratum in ("easy", "hard", "all"):
        rows = selected if stratum == "all" else [r for r in selected if r["stratum"] == stratum]
        if not rows:
            continue
        add = np.array([r["omega_add_lower"] for r in rows], dtype=float)
        mult = np.array([r["omega_lower"] for r in rows], dtype=float)
        out.append({
            "stratum": stratum, "n_pairs": len(rows),
            "fpr_additive": float((add > threshold).mean()),
            "fpr_multiplicative": float((mult > threshold).mean()),
            "median_omega_add_lower": float(np.median(add)),
            "p95_omega_add_lower": float(np.percentile(add, 95)),
            "median_n_ab": float(np.median([r["n_ab"] for r in rows])),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    parser.add_argument("--tier", default="core")
    parser.add_argument("--policy", default="primary")
    parser.add_argument("--n-pairs", type=int, default=None,
                        help="override config; 50 is far too few to calibrate a tail quantile")
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "tier_b.log"),
                  logging.StreamHandler(sys.stdout)],
        force=True,
    )

    conf = cfg.load_config()
    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    contingency.build_case_drugs(con, args.policy)
    contingency.drug_marginals(con, args.tier)

    selected = generate(
        con, args.tier,
        n_pairs=args.n_pairs or conf["controls"]["negative_generation"]["n_pairs"],
        seed=conf["seed"],
    )
    log.info("generated %d negative control pairs", len(selected))

    fields = ["drug_a", "drug_b", "stratum", "rr_a", "rr_b", "n_ab", "n_abz",
              "additive_expected", "omega_add", "omega_add_lower",
              "expected", "omega", "omega_lower"]
    out = cfg.path("tables") / "tier_b_pairs.csv"
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selected)

    summary = summarise(selected)
    with (cfg.path("tables") / "tier_b_summary.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    log.info("%-6s %7s %14s %20s %14s", "stratum", "n", "FPR additive",
             "FPR multiplicative", "median n_ab")
    for row in summary:
        log.info("%-6s %7d %13.1f%% %19.1f%% %14.0f",
                 row["stratum"], row["n_pairs"], 100 * row["fpr_additive"],
                 100 * row["fpr_multiplicative"], row["median_n_ab"])

    # Empirical calibration: the threshold that would hold the false-positive
    # rate at the nominal level, given the null set actually observed.
    add = np.array([r["omega_add_lower"] for r in selected], dtype=float)
    for target in (0.05, 0.025, 0.01):
        threshold = float(np.quantile(add, 1 - target))
        log.info("calibrated threshold for %.1f%% FPR: Omega_add,025 > %+.3f",
                 100 * target, threshold)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
