"""Run every analysis stage in one consistent pass and emit canonical numbers.

Motivation: during development the analysis stages were run separately and
re-run as bugs were fixed, so the findings documents ended up quoting figures
from different generations of the pipeline -- a 6.2% false-positive rate against
6.6% on disk, a threshold of +0.305 against +0.374, 11/16 controls against
12/16. Every one of those pairs is a real number that was true at some point.

Anything reported anywhere in this repository must come from
`results/canonical_numbers.json`, which only this script writes, and which is
produced by a single uninterrupted run. `tests/test_canonical_numbers.py`
asserts the documents agree with it.

Order matters: Tier B calibrates the threshold that Tier C then applies, so the
threshold is computed here and written back to config before the screen runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys

import duckdb
import numpy as np
from scipy import stats

from faers_ddi import config as cfg
from faers_ddi import contingency, omega as om, screen, statistics as st, tier_a, tier_b

log = logging.getLogger("run_analysis")

TARGET_FPR = 0.05
POWERED_MIN_PAIR = 50


def _connect(memory_limit: str) -> duckdb.DuckDBPyConnection:
    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)
    return con


def write_threshold(value: float) -> None:
    """Persist the calibrated threshold so the screen and docs agree."""
    path = cfg.CONFIG_PATH
    text = path.read_text()
    updated = re.sub(r"(?m)^(\s*signal_threshold:\s*)[-\d.]+",
                     lambda m: f"{m.group(1)}{value:.3f}", text)
    path.write_text(updated)
    cfg.load_config.cache_clear()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    parser.add_argument("--negatives", type=int, default=None,
                        help="default None = use the entire eligible pool")
    parser.add_argument("--top-n", type=int, default=200)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(cfg.path("logs") / "run_analysis.log"),
                  logging.StreamHandler(sys.stdout)], force=True)

    conf = cfg.load_config()
    tier = conf["event"]["primary_tier"]
    policy = "primary"
    # run_analysis rewrites canonical_numbers.json wholesale, so the
    # downstream stages must be re-run after it. `stages` records what has
    # run; tests/test_canonical_numbers.py fails if any is missing.
    numbers: dict = {"tier": tier, "policy": policy, "stages": ["run_analysis"]}

    con = _connect(args.memory_limit)
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    n_total, n_event = contingency.totals(con, tier)
    numbers["n_cases"] = n_total
    numbers["n_event_cases"] = n_event
    numbers["event_rate"] = n_event / n_total
    log.info("cases=%s  event cases=%s (%.3f%%)",
             f"{n_total:,}", f"{n_event:,}", 100 * n_event / n_total)

    # --- Tier A -------------------------------------------------------------
    log.info("--- Tier A ---")
    outcome = tier_a.evaluate(con, tier, policy)
    results = outcome["results"]
    powered = [r for r in results if r["n_ab"] >= POWERED_MIN_PAIR]
    numbers["tier_a"] = {
        "n_controls": len(results),
        "recovered_additive": sum(r["signal"] for r in results),
        "recovered_multiplicative": sum(r["signal_multiplicative"] for r in results),
        "n_powered": len(powered),
        "recovered_powered": sum(r["signal"] for r in powered),
        "powered_min_pair": POWERED_MIN_PAIR,
        # Round 27: same definition generalization.py uses for the other three
        # events -- the median of all 2N per-drug marginal RRs -- so the
        # generalization table's comparative column is populated for the primary
        # event too. It was the only blank cell, in the column that
        # operationalises "drug-dominant", which is the paper's conditional.
        "median_marginal_rr": round(float(np.median(
            [r["rr_a"] for r in results if r.get("rr_a")]
            + [r["rr_b"] for r in results if r.get("rr_b")])), 1)
        if any(r.get("rr_a") for r in results) else None,
    }
    lo, hi = st.proportion_ci(numbers["tier_a"]["recovered_powered"], len(powered))
    numbers["tier_a"]["recovered_powered_ci"] = [round(lo, 4), round(hi, 4)]

    # The 16 controls are 5 victim drugs, and simvastatin is in 7 of them, so a
    # binomial interval on 14 "independent" trials is too narrow. Resample the
    # victim drug -- the same correction already used for screen enrichment.
    numbers["tier_a"]["recovered_powered_clustered"] = st.cluster_proportion_ci(
        [r["signal"] for r in powered], [r["drug_a"] for r in powered],
        seed=conf["seed"])
    numbers["tier_a"]["recovered_all_clustered"] = st.cluster_proportion_ci(
        [r["signal"] for r in results], [r["drug_a"] for r in results],
        seed=conf["seed"])
    lo, hi = st.proportion_ci(numbers["tier_a"]["recovered_additive"], len(results))
    numbers["tier_a"]["recovered_additive_ci"] = [round(lo, 4), round(hi, 4)]

    # Selection on the evaluation set: the additive null was chosen because it
    # recovered more of these controls, so in-sample recovery overstates
    # sensitivity. Cross-validate the (binary) selection decision.
    numbers["tier_a"]["leave_one_out"] = st.leave_one_out_selection(
        [r["signal"] for r in results],
        [r["signal_multiplicative"] for r in results])

    # The abstract previously reported r = -0.42 with no n, interval or p.
    n_total_a, n_event_a = contingency.totals(con, tier)
    baseline = n_event_a / n_total_a
    marginals = {row[0]: (row[1], row[2]) for row in con.execute(
        "SELECT ingredient, n_drug, n_drug_event FROM drug_marginals").fetchall()}
    xs, ys = [], []
    for r in results:
        ma, mb = marginals.get(r["drug_a"]), marginals.get(r["drug_b"])
        if not (ma and mb and ma[0] and mb[0] and ma[1] and mb[1]):
            continue
        rr_a = (ma[1] / ma[0]) / baseline
        rr_b = (mb[1] / mb[0]) / baseline
        if r["omega"] is None:
            continue
        xs.append(np.log2(rr_a * rr_b))
        ys.append(r["omega"])
    numbers["tier_a"]["omega_vs_marginal_product"] = st.correlation_with_ci(xs, ys)
    numbers["tier_a"]["correlation_points"] = [
        [round(x, 4), round(y, 4)] for x, y in zip(xs, ys)]

    # The SAME correlation for the additive null, and for the observed rate.
    # Omega = log2(O/E) and E is an increasing function of the marginals, so a
    # negative r is partly mechanical: reporting it for the multiplicative null
    # alone implies the gradient is diagnostic OF that null, which it is not.
    # faers_ddi.audit simulates the induced value; these are the point estimates.
    ys_add = [r["omega_add"] for r in results if r["omega"] is not None]
    ys_obs = [np.log2(max(r["n_abz"], 0.5) / r["n_ab"])
              for r in results if r["omega"] is not None and r["n_ab"]]
    numbers["tier_a"]["omega_add_vs_marginal_product"] = st.correlation_with_ci(xs, ys_add)
    numbers["tier_a"]["observed_rate_vs_marginal_product"] = st.correlation_with_ci(
        xs[:len(ys_obs)], ys_obs)


    log.info("recovered %d/%d additive (%d/%d powered, 95%% CI %.0f-%.0f%%), %d/%d multiplicative",
             numbers["tier_a"]["recovered_additive"], len(results),
             numbers["tier_a"]["recovered_powered"], len(powered),
             100 * numbers["tier_a"]["recovered_powered_ci"][0],
             100 * numbers["tier_a"]["recovered_powered_ci"][1],
             numbers["tier_a"]["recovered_multiplicative"], len(results))
    loo = numbers["tier_a"]["leave_one_out"]
    log.info("leave-one-out: additive chosen in %d/%d folds, held-out recovery %d/%d (optimism %.3f)",
             loo["folds_selecting_additive"], loo["n_folds"],
             loo["loo_recovered"], loo["n_folds"], loo["optimism"])
    corr = numbers["tier_a"]["omega_vs_marginal_product"]
    log.info("omega vs log2(RR_a*RR_b): r=%.2f (n=%d, 95%% CI %.2f to %.2f, p=%.3f)",
             corr["r"], corr["n"], corr["ci_low"], corr["ci_high"], corr["p_value"])

    # --- Tier B -------------------------------------------------------------
    log.info("--- Tier B ---")
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    negatives = tier_b.generate(con, tier, args.negatives, conf["seed"])
    summary = tier_b.summarise(negatives)
    lower = np.array([r["omega_add_lower"] for r in negatives], dtype=float)
    threshold = float(np.quantile(lower, 1 - TARGET_FPR))
    numbers["tier_b"] = {
        "n_pairs": len(negatives),
        "used_full_pool": args.negatives is None,
        "target_fpr": TARGET_FPR,
        "calibrated_threshold": round(threshold, 3),
        "strata": {},
    }
    for row in summary:
        hits = int(round(row["fpr_additive"] * row["n_pairs"]))
        lo, hi = st.proportion_ci(hits, row["n_pairs"])
        numbers["tier_b"]["strata"][row["stratum"]] = {
            "n": row["n_pairs"],
            "fpr_additive": row["fpr_additive"],
            "fpr_additive_ci": [round(lo, 5), round(hi, 5)],
            "fpr_multiplicative": row["fpr_multiplicative"],
        }
    for row in summary:
        log.info("  %-5s n=%d  FPR additive %.1f%%  multiplicative %.1f%%",
                 row["stratum"], row["n_pairs"],
                 100 * row["fpr_additive"], 100 * row["fpr_multiplicative"])
    log.info("calibrated threshold for %.0f%% FPR: %+.3f", 100 * TARGET_FPR, threshold)
    write_threshold(threshold)

    # --- Tier A sensitivity at the calibrated threshold ---------------------
    numbers["tier_a"]["recovered_at_calibrated"] = sum(
        1 for r in results if (r["omega_add_lower"] or -99) > threshold)
    numbers["tier_a"]["recovered_powered_at_calibrated"] = sum(
        1 for r in powered if (r["omega_add_lower"] or -99) > threshold)

    # --- Tier C -------------------------------------------------------------
    log.info("--- Tier C ---")
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    drugs = screen.screen_drugs(con, args.top_n)
    contingency.pair_counts(con, drugs, tier, min_pair=conf["analysis"]["min_co_reports"])
    rows = contingency.score(con, tier)
    positive_keys = {tuple(sorted((c["drug_a"].strip().upper(),
                                   c["drug_b"].strip().upper())))
                     for c in tier_a.load_positive_controls()}
    screen.annotate(rows, positive_keys)

    # --- era stratification -------------------------------------------------
    bins = conf["analysis"]["era_stratification"]
    per_bin: dict[str, dict] = {}
    for era_bin in bins:
        con.execute(f"""
            CREATE OR REPLACE TABLE _bin_flags AS
            SELECT f.* FROM case_flags f JOIN cases_deduped c USING (case_id)
            WHERE c.quarter >= '{era_bin['start']}' AND c.quarter <= '{era_bin['end']}'
        """)
        con.execute("""CREATE OR REPLACE TABLE _bin_drugs AS
                       SELECT d.* FROM case_drugs d SEMI JOIN _bin_flags f USING (case_id)""")
        con.execute("CREATE OR REPLACE TABLE _keep_flags AS SELECT * FROM case_flags")
        con.execute("CREATE OR REPLACE TABLE _keep_drugs AS SELECT * FROM case_drugs")
        con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _bin_flags")
        con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _bin_drugs")
        contingency.drug_marginals(con, tier)
        contingency.pair_counts(con, drugs, tier, min_pair=conf["analysis"]["min_co_reports"])
        per_bin[era_bin["name"]] = {
            (r["drug_a"], r["drug_b"]): r["omega_add_lower"]
            for r in contingency.score(con, tier)
        }
        con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _keep_flags")
        con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _keep_drugs")
        log.info("  era %s: %d pairs testable", era_bin["name"], len(per_bin[era_bin["name"]]))

    for row in rows:
        key = (row["drug_a"], row["drug_b"])
        row["eras_with_signal"] = sum(
            1 for name in per_bin if per_bin[name].get(key, -99) > threshold)
        for name in per_bin:
            row[f"om025_{name}"] = per_bin[name].get(key)

    signalled = [r for r in rows if r["omega_add_lower"] > threshold]
    bands = ("positive_control", "known_pair", "plausible", "unsupported")

    def band_stats(subset: list[dict]) -> dict:
        """Enrichment relative to the unsupported band OF THE SAME SUBSET.

        Comparing an era-stable band against the pooled unsupported rate mixes
        two different denominators and understates enrichment by an order of
        magnitude -- it reported known-pair enrichment of 0.15x where the
        like-for-like figure is far above 1.
        """
        reference = (
            sum(1 for r in subset if r["support"] == "unsupported")
            / max(1, sum(1 for r in rows if r["support"] == "unsupported")))
        reference_n = sum(1 for r in rows if r["support"] == "unsupported")
        reference_k = sum(1 for r in subset if r["support"] == "unsupported")
        out = {"reference_unsupported_rate": round(reference, 5)}
        for band in bands:
            tested = [r for r in rows if r["support"] == band]
            hits = [r for r in subset if r["support"] == band]
            rate = len(hits) / len(tested) if tested else 0.0
            rate_lo, rate_hi = st.proportion_ci(len(hits), len(tested))
            enr_lo, enr_hi = st.ratio_ci(len(hits), len(tested), reference_k, reference_n)
            out[band] = {
                "tested": len(tested), "signalled": len(hits),
                "rate": round(rate, 4),
                "rate_ci": [round(rate_lo, 5), round(rate_hi, 5)],
                "enrichment": round(rate / reference, 2) if reference else None,
                "enrichment_ci": ([round(enr_lo, 2), round(enr_hi, 2)]
                                  if np.isfinite(enr_lo) else None),
                # No p-value here. A binomial test assumes pair independence,
                # which is false -- each drug sits in 199 pairs -- and an
                # earlier version shipped one under a _INVALID suffix. Carrying
                # an invalid statistic in the canonical artifact invites it
                # being quoted; the drug-level permutation test is the valid
                # one and lives in numbers["permutation_test"].
            }
        return out

    era_stable = [r for r in signalled if r["eras_with_signal"] == 3]

    # Dependence-aware significance. Permutes which drugs are implicated,
    # holding the pair graph and the signal pattern fixed.
    from faers_ddi.tier_b import MYOTOXICITY_IMPLICATED
    pair_keys = [(r["drug_a"], r["drug_b"]) for r in rows]
    numbers["permutation_test"] = {
        "pooled": st.drug_level_permutation_test(
            pair_keys, [r["omega_add_lower"] > threshold for r in rows],
            MYOTOXICITY_IMPLICATED, n_permutations=10_000, seed=conf["seed"]),
        "era_stable": st.drug_level_permutation_test(
            pair_keys, [r["eras_with_signal"] == 3 and r["omega_add_lower"] > threshold
                        for r in rows],
            MYOTOXICITY_IMPLICATED, n_permutations=10_000, seed=conf["seed"]),
    }

    # The support annotation is not independent of the control set: every
    # positive-control drug is on the implicated list. Recompute enrichment
    # over pairs containing NO control drug, which removes that circularity.
    control_drugs = {d for pair in positive_keys for d in pair}
    independent = [r for r in rows
                   if r["drug_a"] not in control_drugs and r["drug_b"] not in control_drugs]
    ind_known = [r for r in independent if r["support"] == "known_pair"]
    ind_unsup = [r for r in independent if r["support"] == "unsupported"]
    k_known = sum(r["omega_add_lower"] > threshold for r in ind_known)
    k_unsup = sum(r["omega_add_lower"] > threshold for r in ind_unsup)
    enr_lo, enr_hi = st.ratio_ci(k_known, len(ind_known), k_unsup, len(ind_unsup))
    numbers["independent_annotation"] = {
        "note": "pairs containing no positive-control drug; removes the "
                "circularity in the support annotation",
        "known_pair_tested": len(ind_known), "known_pair_signalled": k_known,
        "unsupported_tested": len(ind_unsup), "unsupported_signalled": k_unsup,
        "enrichment": (round((k_known / len(ind_known)) / (k_unsup / len(ind_unsup)), 2)
                       if ind_known and k_unsup else None),
        "enrichment_ci": [round(enr_lo, 2), round(enr_hi, 2)] if np.isfinite(enr_lo) else None,
    }
    numbers["tier_c"] = {
        "n_drugs": len(drugs),
        "n_pairs_tested": len(rows),
        "n_signalled": len(signalled),
        "signalled_fraction": round(len(signalled) / len(rows), 4),
        "expected_by_chance": int(round(TARGET_FPR * len(rows))),
        "bands_pooled": band_stats(signalled),
        "era_stable": {
            "n_pairs": len(era_stable),
            "with_prior_support": sum(
                1 for r in era_stable
                if r["support"] in ("positive_control", "known_pair")),
            "bands": band_stats(era_stable),
        },
        "by_era_count": {
            str(k): sum(1 for r in signalled if r["eras_with_signal"] == k)
            for k in (3, 2, 1, 0)
        },
    }
    log.info("screen: %d/%d pairs signal (%.1f%%), ~%d expected by chance",
             len(signalled), len(rows), 100 * len(signalled) / len(rows),
             numbers["tier_c"]["expected_by_chance"])
    negative_keys = {(r["drug_a"], r["drug_b"]) for r in negatives}
    negative_rows = [r for r in rows if (r["drug_a"], r["drug_b"]) in negative_keys]
    neg_pooled = sum(1 for r in negative_rows if r["omega_add_lower"] > threshold)
    neg_stable = sum(1 for r in negative_rows
                     if r["omega_add_lower"] > threshold and r["eras_with_signal"] == 3)
    lo, hi = st.proportion_ci(neg_stable, len(negative_rows))
    bound = st.rule_of_three_upper(len(negative_rows)) if neg_stable == 0 else hi
    numbers["era_stability_validation"] = {
        "note": "the era-stability filter applied to the negative controls; "
                "omitted from the first version of this analysis",
        "n_negative_controls_screened": len(negative_rows),
        "pass_pooled_threshold": neg_pooled,
        "pass_era_stability": neg_stable,
        "era_stable_fpr": round(neg_stable / len(negative_rows), 6) if negative_rows else None,
        "era_stable_fpr_ci": [round(lo, 6), round(hi, 6)],
        "upper_bound_used": round(bound, 6),
        # Round 19 renamed this. It was called `expected_era_stable_by_chance`
        # while being computed from `bound` -- the UPPER confidence limit, not
        # the point estimate. It evaluates to 33.2 where the expectation is
        # 16.1, so anyone reading the key by its name would conclude the 19
        # observed pairs fall well BELOW chance. The papers always quoted 16.1
        # correctly; nothing asserted this key, so nothing caught it.
        "expected_era_stable_at_upper_bound": round(bound * len(rows), 1),
        "expected_era_stable_point": (round(neg_stable / len(negative_rows) * len(rows), 1)
                                      if negative_rows else None),
        "observed_era_stable": len(era_stable),
    }
    ev = numbers["era_stability_validation"]
    log.info("era-stability on negatives: %d/%d pass (upper bound %.4f%%) -> "
             "<=%.1f of %d era-stable pairs expected by chance",
             neg_stable, len(negative_rows), 100 * bound,
             ev["expected_era_stable_at_upper_bound"], len(era_stable))
    log.info("era-stable (3/3): %d pairs, known-pair enrichment %.2fx",
             len(era_stable),
             numbers["tier_c"]["era_stable"]["bands"]["known_pair"]["enrichment"] or 0)

    # The era loop leaves `pair_counts` and `drug_marginals` holding the final
    # bin. Everything below needs the full-window tables, so rebuild them.
    # Without this the alpha sensitivity below silently ran on 2019-2026 only,
    # reporting 5-8/15 control recovery against the true 11/15.
    contingency.drug_marginals(con, tier)
    contingency.pair_counts(con, drugs, tier, min_pair=conf["analysis"]["min_co_reports"])

    # --- independent reference: FDA product labelling -----------------------
    # Replaces the author-curated annotation, whose circularity accounted for
    # the entire apparent enrichment. Independent of the authors; NOT
    # independent of FAERS, since labelling is informed by surveillance.
    label_path = cfg.path("tables") / "label_interaction_reference.csv"
    myo_path = cfg.path("tables") / "label_myotoxicity_reference.csv"
    if label_path.exists():
        with label_path.open() as fh:
            documented = {tuple(row) for row in list(csv.reader(fh))[1:]}
        myotoxicity_documented = set()
        if myo_path.exists():
            with myo_path.open() as fh:
                myotoxicity_documented = {tuple(row) for row in list(csv.reader(fh))[1:]}
        controls_captured = sum(
            1 for c in tier_a.load_positive_controls()
            if tuple(sorted((c["drug_a"].strip().upper(),
                             c["drug_b"].strip().upper()))) in documented)

        def label_enrichment(subset: list[dict], universe: list[dict]) -> dict:
            hits_doc = sum(1 for r in subset
                           if (r["drug_a"], r["drug_b"]) in documented)
            n_doc = sum(1 for r in universe
                        if (r["drug_a"], r["drug_b"]) in documented)
            hits_undoc = len(subset) - hits_doc
            n_undoc = len(universe) - n_doc
            if not (n_doc and n_undoc and hits_undoc):
                return {"documented_tested": n_doc, "documented_signalled": hits_doc,
                        "undocumented_tested": n_undoc,
                        "undocumented_signalled": hits_undoc,
                        "enrichment": None, "enrichment_ci": None}
            rate_doc, rate_undoc = hits_doc / n_doc, hits_undoc / n_undoc
            lo, hi = st.ratio_ci(hits_doc, n_doc, hits_undoc, n_undoc)
            return {
                "documented_tested": n_doc, "documented_signalled": hits_doc,
                "undocumented_tested": n_undoc, "undocumented_signalled": hits_undoc,
                "enrichment": round(rate_doc / rate_undoc, 2),
                "enrichment_ci": [round(lo, 2), round(hi, 2)],
            }

        no_control = [r for r in rows if r["drug_a"] not in control_drugs
                      and r["drug_b"] not in control_drugs]
        numbers["label_reference"] = {
            "note": "FDA product labelling via openFDA; independent of the "
                    "authors' curation but not of FAERS",
            "n_documented_pairs": len(documented),
            "positive_controls_captured": controls_captured,
            "n_positive_controls": len(tier_a.load_positive_controls()),
            "pooled": label_enrichment(signalled, rows),
            "excluding_control_drugs": label_enrichment(
                [r for r in signalled if r in no_control], no_control),
            "era_stable": label_enrichment(era_stable, rows),
            "era_stable_excluding_control_drugs": label_enrichment(
                [r for r in era_stable if r in no_control], no_control),
            "permutation": st.drug_level_permutation_test(
                pair_keys, [r["omega_add_lower"] > threshold for r in rows],
                {d for pair in documented for d in pair},
                n_permutations=10_000, seed=conf["seed"]),
        }

        # A label documents that two drugs interact, not that the interaction
        # causes THIS event: 82% of the 1,400 pairs are documented for an
        # unrelated endpoint. The endpoint-specific reference requires a
        # myotoxicity term near the partner drug's name.
        #
        # Documented pairs are also co-reported ~3x more often than undocumented
        # ones, and co-report count drives power, so the crude comparison is
        # confounded. Both corrections are applied here.
        if myotoxicity_documented:
            myo_controls = sum(
                1 for c in tier_a.load_positive_controls()
                if tuple(sorted((c["drug_a"].strip().upper(),
                                 c["drug_b"].strip().upper()))) in myotoxicity_documented)
            corrected = {"n_pairs": len(myotoxicity_documented),
                         "positive_controls_captured": myo_controls}
            # The era-stable scopes are here as well as in `label_reference`.
            # The composition claim in section 4.6 was previously reported ONLY
            # against the any-endpoint reference -- the one shown two sections
            # earlier to be 82% endpoint-irrelevant -- and without the
            # co-report stratification that the same section calls mandatory.
            # Two standards in adjacent sections. Same standard now.
            def _signalled(r):
                return r["omega_add_lower"] > threshold

            def _era_stable_signalled(r):
                return r["eras_with_signal"] == 3 and r["omega_add_lower"] > threshold

            for scope, universe, hit in (
                    ("all_pairs", rows, _signalled),
                    ("excluding_control_drugs", no_control, _signalled),
                    ("era_stable", rows, _era_stable_signalled),
                    ("era_stable_excluding_control_drugs", no_control,
                     _era_stable_signalled)):
                sig = [hit(r) for r in universe]
                doc = [(r["drug_a"], r["drug_b"]) in myotoxicity_documented
                       for r in universe]
                cnt = [r["n_ab"] for r in universe]
                k_doc = sum(s for s, d in zip(sig, doc) if d)
                n_doc = sum(doc)
                k_und = sum(s for s, d in zip(sig, doc) if not d)
                n_und = len(doc) - n_doc
                crude = ((k_doc / n_doc) / (k_und / n_und)
                         if n_doc and n_und and k_und else None)
                lo, hi = st.ratio_ci(k_doc, n_doc, k_und, n_und)
                entry = {
                    "documented_tested": n_doc, "documented_signalled": k_doc,
                    "undocumented_tested": n_und, "undocumented_signalled": k_und,
                    "crude_enrichment": round(crude, 2) if crude else None,
                    "crude_enrichment_ci": ([round(lo, 2), round(hi, 2)]
                                            if np.isfinite(lo) else None),
                    "stratified_enrichment": st.mantel_haenszel_ratio(sig, doc, cnt)["ratio"],
                }
                # A point estimate with no interval is not reportable. The
                # bootstrap resamples DRUGS, since each sits in hundreds of pairs.
                if n_doc and n_und and k_doc and k_und:
                    boot = st.mantel_haenszel_bootstrap(
                        [(r["drug_a"], r["drug_b"]) for r in universe],
                        sig, doc, cnt, n_boot=1000, seed=conf["seed"])
                    entry["stratified_ci_cluster_bootstrap"] = boot["ci"]
                    entry["stratified_excludes_unity"] = boot.get("excludes_unity")
                corrected[scope] = entry
            numbers["endpoint_specific_reference"] = corrected
            log.info("endpoint-specific reference: %d pairs, %d/16 controls captured",
                     len(myotoxicity_documented), myo_controls)
            for scope in ("all_pairs", "excluding_control_drugs"):
                v = corrected[scope]
                log.info("  %-24s crude %s (CI %s)  n_ab-stratified %s",
                         scope, v["crude_enrichment"], v["crude_enrichment_ci"],
                         v["stratified_enrichment"])
        lr = numbers["label_reference"]
        log.info("label reference: %d pairs, %d/%d positive controls captured",
                 len(documented), controls_captured,
                 numbers["label_reference"]["n_positive_controls"])
        for scope in ("pooled", "excluding_control_drugs", "era_stable",
                      "era_stable_excluding_control_drugs"):
            v = lr[scope]
            log.info("  %-24s enrichment %s (95%% CI %s)",
                     scope, v["enrichment"], v["enrichment_ci"])

    # --- alpha sensitivity ---------------------------------------------------
    # alpha = 0.5 is conventional and could not be verified against Noren et al.
    # Rather than leave that as an open dependency, vary it and show the
    # conclusions do not turn on it.
    #
    # alpha enters ONLY the shrinkage, not the expected counts, so it can be
    # varied analytically from counts already computed. Re-scoring through the
    # database instead recalibrated the threshold on whichever negative controls
    # happened to reach the screen (6,471 of 16,138) rather than the full pool,
    # and reported control recovery from a biased subset.
    neg_observed = np.array([r["n_abz"] for r in negatives], dtype=float)
    neg_expected = np.array([r["additive_expected"] for r in negatives], dtype=float)
    screen_observed = np.array([r["n_abz"] for r in rows], dtype=float)
    screen_expected = np.array([r["additive_expected"] for r in rows], dtype=float)
    is_control = np.array([r["support"] == "positive_control" for r in rows])
    quantile = conf["analysis"]["omega"]["quantile"]

    alpha_rows = []
    for alpha in (0.1, 0.25, 0.5, 1.0, 2.0):
        neg_bound = om.omega_quantile_vec(neg_observed, neg_expected, quantile, alpha)
        thr_a = float(np.quantile(neg_bound, 1 - TARGET_FPR))
        screen_bound = om.omega_quantile_vec(
            screen_observed, screen_expected, quantile, alpha)
        signalled_a = screen_bound > thr_a
        alpha_rows.append({
            "alpha": alpha,
            "calibrated_threshold": round(thr_a, 3),
            "n_signalled": int(signalled_a.sum()),
            "positive_controls_recovered": int((signalled_a & is_control).sum()),
            "n_positive_controls_screened": int(is_control.sum()),
        })
    numbers["alpha_sensitivity"] = alpha_rows
    log.info("alpha sensitivity: " + "; ".join(
        f"a={r['alpha']} thr={r['calibrated_threshold']:+.2f} "
        f"ctrl={r['positive_controls_recovered']}/{r['n_positive_controls_screened']} "
        f"sig={r['n_signalled']}" for r in alpha_rows))

    # --- outputs ------------------------------------------------------------
    fields = ["drug_a", "drug_b", "support", "n_ab", "n_abz", "additive_expected",
              "omega_add", "omega_add_lower", "expected", "omega", "omega_lower",
              "naive_log2_oe", "eras_with_signal"] + [f"om025_{b['name']}" for b in bins]
    rows.sort(key=lambda r: -r["omega_add_lower"])
    with (cfg.path("tables") / "screen_results.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with (cfg.path("tables") / "era_stable_signals.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(era_stable, key=lambda r: -r["omega_add_lower"]))

    # Written here, at the end, from this same process: the table and
    # canonical_numbers.json must not come from different runs. Rebuilding
    # case_drugs for each tier/policy is safe now that nothing downstream reads
    # the connection state.
    all_arms = tier_a.evaluate_all(con)
    log.info("tier A table -> %s", tier_a.write_results_csv(all_arms))

    # THE FULL SPECIFICATION GRID. Four arms are computed; only core/primary is
    # the pre-specified one (config event.primary_tier), and earlier versions
    # reported that arm alone without saying the others existed. One of them --
    # broad tier with the wider role policy -- erases the additive null's
    # advantage entirely (6/16 against 6/16). A reader cannot judge robustness
    # without seeing the grid, so it is canonical now.
    grid = []
    for arm_tier in ("core", "broad"):
        for arm_policy in ("primary", "sensitivity"):
            arm = [r for r in all_arms
                   if r["tier"] == arm_tier and r["policy"] == arm_policy]
            if not arm:
                continue
            arm_powered = [r for r in arm if r["n_ab"] >= POWERED_MIN_PAIR]
            grid.append({
                "tier": arm_tier, "policy": arm_policy,
                "pre_specified": arm_tier == tier and arm_policy == "primary",
                "n_controls": len(arm),
                "recovered_additive": sum(r["signal"] for r in arm),
                "recovered_multiplicative": sum(
                    r["signal_multiplicative"] for r in arm),
                "n_powered": len(arm_powered),
                "recovered_powered": sum(r["signal"] for r in arm_powered),
                "additive_advantage": sum(r["signal"] for r in arm)
                                      - sum(r["signal_multiplicative"] for r in arm),
            })
    numbers["specification_grid"] = {
        "note": "all four tier x role-policy arms; core/primary is pre-specified "
                "in config as event.primary_tier",
        "arms": grid,
        "n_arms_where_additive_wins": sum(1 for g in grid if g["additive_advantage"] > 0),
        "n_arms": len(grid),
        "min_additive_advantage": min(g["additive_advantage"] for g in grid),
    }
    log.info("--- specification grid ---")
    for g in grid:
        log.info("  tier=%-6s policy=%-11s additive %2d/%d  multiplicative %2d/%d %s",
                 g["tier"], g["policy"], g["recovered_additive"], g["n_controls"],
                 g["recovered_multiplicative"], g["n_controls"],
                 "<- PRE-SPECIFIED" if g["pre_specified"] else "")

    out = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
    out.write_text(json.dumps(numbers, indent=2, sort_keys=True) + "\n")
    log.info("canonical numbers -> %s", out)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
