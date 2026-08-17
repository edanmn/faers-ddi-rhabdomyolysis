"""Error rates in the regime the study is actually about.

Round-11 review found that the false-positive rate was measured almost entirely
outside the regime where sensitivity was measured. The positive controls sit at
a median log2(RR_a x RR_b) of 8.2; the generated negative controls sit at 0.6,
and only 0.1% of them reach the positive controls' interquartile floor. Because
the expected count rises steeply with marginal strength -- the paper's own
finding -- a false-positive rate averaged over that pool says little about the
rate among strongly-associated pairs.

The consequence was concrete. At Omega_025 > 0 the two nulls were reported as
running at "an essentially identical false-positive rate", 6.4% against 6.7%.
Restricted to negative controls as strongly associated as the weakest positive
control, the rates are 1.2% and 9.0%. The published recovery comparison was
therefore not a comparison of nulls at a common error rate; it was a comparison
of two different operating points.

This module measures what was missing:

  in_regime          false-positive rate as a function of marginal strength,
                     for both nulls, on the existing negative pool.

  matched_recovery   positive-control recovery when each null is calibrated to
                     the SAME in-regime false-positive rate, which is the
                     comparison the headline claim requires.

  high_marginal_pool a purpose-built negative set: pairs whose two drugs are
                     BOTH strongly associated with the event but which are not
                     documented interactions. The existing generator excludes
                     pairs where both drugs are implicated, which is exactly the
                     configuration every positive control has -- so it can never
                     produce a negative that resembles a positive.

  strength_matched_chance
                     the screen's expected-by-chance count when the rate is
                     allowed to vary with marginal strength instead of being
                     held at the pooled value.

Two drugs that each cause an event independently need not interact, so a
strongly-associated pair with no documented interaction is a legitimate
negative. As with any negative control set drawn from spontaneous reports, some
members may be undocumented true interactions, so every rate here is an upper
bound -- the same caveat the pooled rate already carries.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys

import duckdb
import numpy as np

from faers_ddi import config as cfg
from faers_ddi import contingency, generalization, screen, statistics as st
from faers_ddi import tier_a, tier_b

log = logging.getLogger("regime")

SEED = 20260804
# Quintiles are reported; this is the cut used for the headline in-regime rate.
# It is the marginal strength of the WEAKEST positive control, so "in regime"
# means "at least as strongly associated as the easiest pair we claim to find".
N_QUANTILES = 5


def marginal_strength(con: duckdb.DuckDBPyConnection, tier: str) -> tuple[dict, float]:
    n_total, n_event = contingency.totals(con, tier)
    baseline = n_event / n_total
    rr = {}
    for ingredient, n_drug, n_drug_event in con.execute(
        "SELECT ingredient, n_drug, n_drug_event FROM drug_marginals"
    ).fetchall():
        if n_drug and n_drug_event:
            rr[ingredient] = (n_drug_event / n_drug) / baseline
    return rr, baseline


def _strength(rows: list[dict]) -> np.ndarray:
    return np.array([np.log2(r["rr_a"] * r["rr_b"]) for r in rows])


def in_regime(negatives: list[dict], positives: list[dict],
              cut: float | None = None) -> dict:
    """False-positive rate by marginal strength, both nulls.

    `cut` defaults to the weakest positive control, so the headline rate answers
    "how often does each null fire on a pair as strongly associated as the
    easiest interaction we claim to detect, but which is not one?"
    """
    usable = [r for r in negatives if r["rr_a"] > 0 and r["rr_b"] > 0]
    x = _strength(usable)
    add = np.array([r["omega_add_lower"] > 0 for r in usable])
    mult = np.array([r["omega_lower"] > 0 for r in usable])
    pos_x = np.array([p["strength"] for p in positives])
    cut = float(pos_x.min()) if cut is None else cut

    edges = np.quantile(x, np.linspace(0, 1, N_QUANTILES + 1))
    quintiles = []
    for i in range(N_QUANTILES):
        mask = (x >= edges[i]) & (x <= edges[i + 1])
        quintiles.append({
            "quintile": i + 1,
            "strength_range": [round(float(edges[i]), 2), round(float(edges[i + 1]), 2)],
            "n": int(mask.sum()),
            "fpr_additive": round(float(add[mask].mean()), 4),
            "fpr_multiplicative": round(float(mult[mask].mean()), 4),
        })

    mask = x >= cut
    return {
        "note": "the negative pool spans a far weaker range than the positive "
                "controls; a pooled false-positive rate is not the rate in the "
                "regime where recovery is measured",
        "positive_strength_median": round(float(np.median(pos_x)), 2),
        "positive_strength_min": round(cut, 2),
        "negative_strength_median": round(float(np.median(x)), 2),
        "negatives_reaching_positive_iqr": int(
            (x >= np.percentile(pos_x, 25)).sum()),
        "negatives_total": len(usable),
        "quintiles": quintiles,
        "in_regime_cut": round(cut, 2),
        "in_regime_n": int(mask.sum()),
        "in_regime_fpr_additive": round(float(add[mask].mean()), 4),
        "in_regime_fpr_multiplicative": round(float(mult[mask].mean()), 4),
        # Round 23. These two rates carry the paper's calibration claim and had
        # shipped as bare point estimates for six rounds, while Methods promised
        # a cluster bootstrap for pair-aggregated quantities. The pairs are not
        # independent -- each drug recurs across many of them -- so the binomial
        # interval is too narrow. Resampling drugs is the honest version.
        "in_regime_fpr_additive_clustered": st.pair_cluster_proportion_ci(
            add[mask], [(r["drug_a"], r["drug_b"]) for r, m in zip(usable, mask) if m],
            seed=SEED),
        "in_regime_fpr_multiplicative_clustered": st.pair_cluster_proportion_ci(
            mult[mask], [(r["drug_a"], r["drug_b"]) for r, m in zip(usable, mask) if m],
            seed=SEED),
    }


def matched_recovery(positives: list[dict], negatives: list[dict],
                     cut: float, targets=(0.05, 0.10, 0.20)) -> dict:
    """Recovery when both nulls are calibrated to the same in-regime rate.

    At Omega_025 > 0 the two nulls sit at very different in-regime error rates,
    so the published recovery gap conflates the choice of null with the choice
    of operating point. This separates them.
    """
    usable = [r for r in negatives if r["rr_a"] > 0 and r["rr_b"] > 0]
    x = _strength(usable)
    mask = x >= cut
    neg_add = np.array([r["omega_add_lower"] for r in usable])[mask]
    neg_mult = np.array([r["omega_lower"] for r in usable])[mask]
    pos_add = np.array([p["omega_add_lower"] for p in positives])
    pos_mult = np.array([p["omega_lower"] for p in positives])

    rows = [{
        "operating_point": "Omega_025 > 0 (as published)",
        "threshold_additive": 0.0, "threshold_multiplicative": 0.0,
        "recovered_additive": int((pos_add > 0).sum()),
        "recovered_multiplicative": int((pos_mult > 0).sum()),
        "in_regime_fpr_additive": round(float((neg_add > 0).mean()), 4),
        "in_regime_fpr_multiplicative": round(float((neg_mult > 0).mean()), 4),
    }]
    for target in targets:
        t_add = float(np.quantile(neg_add, 1 - target))
        t_mult = float(np.quantile(neg_mult, 1 - target))
        rows.append({
            "operating_point": f"matched at {target:.0%} in-regime FPR",
            "threshold_additive": round(t_add, 3),
            "threshold_multiplicative": round(t_mult, 3),
            "recovered_additive": int((pos_add > t_add).sum()),
            "recovered_multiplicative": int((pos_mult > t_mult).sum()),
            "in_regime_fpr_additive": target,
            "in_regime_fpr_multiplicative": target,
        })
    gaps = [r["recovered_additive"] - r["recovered_multiplicative"] for r in rows]
    return {
        "n_positive_controls": len(positives),
        "n_in_regime_negatives": int(mask.sum()),
        "caveat": "calibrating a tail quantile on this many negatives is noisy; "
                  "the 5%/10%/20% points rest on roughly 5%/10%/20% of them",
        "rows": rows,
        "gap_as_published": gaps[0],
        "gap_matched_min": min(gaps[1:]),
        "gap_matched_max": max(gaps[1:]),
        "additive_wins_at_every_matched_rate": all(g > 0 for g in gaps[1:]),
    }


def high_marginal_pool(con: duckdb.DuckDBPyConnection, tier: str,
                       reference: set, min_rr: float = 2.0,
                       min_pair: int = 20) -> dict:
    """Negative controls that resemble positive controls in marginal strength.

    `tier_b.generate` drops any pair where BOTH drugs are on the implicated
    list. Every positive control is such a pair, so that generator cannot
    produce a negative in the regime under study. Here the exclusion is on
    documented INTERACTION -- the authors' control set and the endpoint-specific
    label reference -- rather than on the drugs being individually implicated,
    because two independently myotoxic drugs need not interact.
    """
    rr, _ = marginal_strength(con, tier)
    strong = sorted(d for d, value in rr.items() if value >= min_rr)
    contingency.pair_counts(con, strong, tier, min_pair=min_pair)
    scored = contingency.score(con, tier)

    authors = {tuple(sorted((c["drug_a"].strip().upper(),
                             c["drug_b"].strip().upper())))
               for c in tier_a.load_positive_controls()}
    pool = []
    for row in scored:
        key = (row["drug_a"], row["drug_b"])
        if key in authors or key in reference:
            continue
        if row["drug_a"] in tier_b.MYOTOXICITY_IMPLICATED and \
           row["drug_b"] in tier_b.MYOTOXICITY_IMPLICATED:
            # Both on the implicated list AND undocumented: too likely to be an
            # unrecorded true interaction to serve as a negative.
            continue
        row["rr_a"], row["rr_b"] = rr.get(row["drug_a"], 0), rr.get(row["drug_b"], 0)
        pool.append(row)
    return {
        "note": "pairs whose two drugs are each associated with the event "
                "(RR >= %.1f) but which are not documented interactions; "
                "excludes both-implicated pairs as too likely to be "
                "undocumented true positives" % min_rr,
        "min_rr": min_rr, "min_pair": min_pair,
        "n_strong_drugs": len(strong),
        "pool": pool,
    }


def strength_matched_chance(screen_rows: list[dict], negatives: list[dict],
                            rr: dict, threshold: float) -> dict:
    """Expected-by-chance per band, letting the rate vary with marginal strength.

    The screen reports a single pooled rate times the number of pairs. The rate
    is not constant across the range, and the bands differ systematically in
    marginal strength, so a pooled figure mis-states every band.
    """
    usable = [r for r in negatives if r["rr_a"] > 0 and r["rr_b"] > 0]
    x_neg = _strength(usable)
    sig_neg = np.array([r["omega_add_lower"] > threshold for r in usable])
    edges = np.quantile(x_neg, np.linspace(0, 1, N_QUANTILES + 1))
    rate = []
    for i in range(N_QUANTILES):
        mask = (x_neg >= edges[i]) & (x_neg <= edges[i + 1])
        rate.append(float(sig_neg[mask].mean()) if mask.sum() else float(sig_neg.mean()))
    pooled = float(sig_neg.mean())

    bands: dict = {}
    for row in screen_rows:
        a, b = rr.get(row["drug_a"]), rr.get(row["drug_b"])
        if not (a and b):
            continue
        strength = np.log2(a * b)
        index = int(np.clip(np.searchsorted(edges, strength, side="right") - 1,
                            0, N_QUANTILES - 1))
        entry = bands.setdefault(row["support"],
                                 {"tested": 0, "observed": 0,
                                  "expected_pooled": 0.0, "expected_matched": 0.0})
        entry["tested"] += 1
        entry["observed"] += int(row["omega_add_lower"] > threshold)
        entry["expected_pooled"] += pooled
        entry["expected_matched"] += rate[index]
    for entry in bands.values():
        entry["expected_pooled"] = round(entry["expected_pooled"])
        entry["expected_matched"] = round(entry["expected_matched"])
    total = {k: sum(e[k] for e in bands.values())
             for k in ("tested", "observed", "expected_pooled", "expected_matched")}
    return {
        "note": "the pooled rate assumes the false-positive rate is constant "
                "across the marginal-strength range; it varies by an order of "
                "magnitude, and the bands differ systematically on it",
        "pooled_rate": round(pooled, 4),
        "rate_by_quintile": [round(v, 4) for v in rate],
        "bands": bands, "total": total,
        "screen_below_chance_when_matched": total["observed"] < total["expected_matched"],
    }


def _positive_rows(con, tier: str, policy: str, rr: dict) -> list[dict]:
    outcome = tier_a.evaluate(con, tier, policy, rebuild=False)
    rows = []
    for r in outcome["results"]:
        a, b = rr.get(r["drug_a"]), rr.get(r["drug_b"])
        if a and b and r["omega"] is not None:
            rows.append({**r, "rr_a": a, "rr_b": b, "strength": float(np.log2(a * b))})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(cfg.path("logs") / "regime.log"),
                  logging.StreamHandler(sys.stdout)], force=True)

    conf = cfg.load_config()
    tier, policy = conf["event"]["primary_tier"], "primary"
    threshold = conf["analysis"]["omega"]["signal_threshold"]
    canonical = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
    numbers = json.loads(canonical.read_text())
    results: dict = {}

    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    rr, _ = marginal_strength(con, tier)
    positives = _positive_rows(con, tier, policy, rr)

    log.info("--- generated negative pool, by marginal strength ---")
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    negatives = tier_b.generate(con, tier, None, conf["seed"])
    results["in_regime"] = in_regime(negatives, positives)
    ir = results["in_regime"]
    log.info("  positives median %.2f, negatives median %.2f; only %d of %d "
             "negatives reach the positive IQR floor",
             ir["positive_strength_median"], ir["negative_strength_median"],
             ir["negatives_reaching_positive_iqr"], ir["negatives_total"])
    log.info("  in regime (>= %.2f, n=%d): additive %.1f%%, multiplicative %.1f%%",
             ir["in_regime_cut"], ir["in_regime_n"],
             100 * ir["in_regime_fpr_additive"],
             100 * ir["in_regime_fpr_multiplicative"])

    log.info("--- recovery at matched in-regime error rates ---")
    results["matched_recovery"] = matched_recovery(
        positives, negatives, ir["in_regime_cut"])
    for row in results["matched_recovery"]["rows"]:
        log.info("  %-34s additive %2d/16  multiplicative %2d/16",
                 row["operating_point"], row["recovered_additive"],
                 row["recovered_multiplicative"])

    log.info("--- purpose-built high-marginal negative pool ---")
    ref_path = cfg.path("tables") / "label_myotoxicity_reference.csv"
    reference = set()
    if ref_path.exists():
        with ref_path.open() as fh:
            reference = {tuple(row) for row in list(csv.reader(fh))[1:]}
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    built = high_marginal_pool(con, tier, reference)
    pool = built.pop("pool")
    add = np.array([r["omega_add_lower"] > 0 for r in pool])
    mult = np.array([r["omega_lower"] > 0 for r in pool])
    x_pool = _strength(pool)
    built.update({
        "n_pairs": len(pool),
        "strength_median": round(float(np.median(x_pool)), 2),
        "fpr_additive": round(float(add.mean()), 4),
        "fpr_multiplicative": round(float(mult.mean()), 4),
    })
    strong_mask = x_pool >= ir["in_regime_cut"]
    if strong_mask.sum():
        strong_pairs = [(r["drug_a"], r["drug_b"])
                        for r, m in zip(pool, strong_mask) if m]
        built["at_positive_control_strength"] = {
            "n": int(strong_mask.sum()),
            "fpr_additive": round(float(add[strong_mask].mean()), 4),
            "fpr_multiplicative": round(float(mult[strong_mask].mean()), 4),
            # Round 23: the headline pair, now with the interval Methods promised.
            "fpr_additive_clustered": st.pair_cluster_proportion_ci(
                add[strong_mask], strong_pairs, seed=SEED),
            "fpr_multiplicative_clustered": st.pair_cluster_proportion_ci(
                mult[strong_mask], strong_pairs, seed=SEED),
        }
    results["high_marginal_pool"] = built
    log.info("  %d pairs, median strength %.2f: additive %.1f%%, multiplicative %.1f%%",
             built["n_pairs"], built["strength_median"],
             100 * built["fpr_additive"], 100 * built["fpr_multiplicative"])
    if "at_positive_control_strength" in built:
        s = built["at_positive_control_strength"]
        log.info("  at positive-control strength (n=%d): additive %.1f%%, "
                 "multiplicative %.1f%%", s["n"],
                 100 * s["fpr_additive"], 100 * s["fpr_multiplicative"])

    log.info("--- strength-matched chance baseline for the screen ---")
    screen_rows = []
    with (cfg.path("tables") / "screen_results.csv").open() as fh:
        for row in csv.DictReader(fh):
            screen_rows.append({"drug_a": row["drug_a"], "drug_b": row["drug_b"],
                                "support": row["support"],
                                "omega_add_lower": float(row["omega_add_lower"])})
    results["strength_matched_chance"] = strength_matched_chance(
        screen_rows, negatives, rr, threshold)
    smc = results["strength_matched_chance"]
    log.info("  observed %d; pooled expectation %d; strength-matched %d",
             smc["total"]["observed"], smc["total"]["expected_pooled"],
             smc["total"]["expected_matched"])

    log.info("--- torsade, at matched in-regime error rates ---")
    spec = generalization.EVENTS["torsade_qt"]
    contingency.build_case_drugs(con, policy)
    pts = generalization.verify_terms(con, spec["pts"])
    generalization.build_event_flags(con, pts)
    contingency.drug_marginals(con, tier)
    rr_t, _ = marginal_strength(con, tier)
    drugs = sorted({d for pair in spec["controls"] for d in pair})
    contingency.pair_counts(con, drugs, tier, min_pair=1)
    scored = {(r["drug_a"], r["drug_b"]): r for r in contingency.score(con, tier)}
    pos_t = []
    for a, b in spec["controls"]:
        row = scored.get(tuple(sorted((a, b))))
        if row and rr_t.get(a) and rr_t.get(b):
            pos_t.append({**row, "rr_a": rr_t[a], "rr_b": rr_t[b],
                          "strength": float(np.log2(rr_t[a] * rr_t[b]))})
    neg_t = tier_b.generate(con, tier, None, conf["seed"])
    if pos_t and neg_t:
        ir_t = in_regime(neg_t, pos_t)
        results["torsade_matched"] = {
            "in_regime": ir_t,
            "matched_recovery": matched_recovery(pos_t, neg_t, ir_t["in_regime_cut"]),
        }
        for row in results["torsade_matched"]["matched_recovery"]["rows"]:
            log.info("  %-34s additive %2d/%d  multiplicative %2d/%d",
                     row["operating_point"], row["recovered_additive"], len(pos_t),
                     row["recovered_multiplicative"], len(pos_t))

    numbers["regime"] = results
    numbers.setdefault("stages", []).append("regime")
    numbers["stages"] = sorted(set(numbers["stages"]))
    canonical.write_text(json.dumps(numbers, indent=2, sort_keys=True) + "\n")
    log.info("regime results merged into %s", canonical)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
