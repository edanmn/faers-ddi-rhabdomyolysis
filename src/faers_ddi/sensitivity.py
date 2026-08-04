"""Sensitivity analyses for the design choices review flagged as unexamined.

Each function answers one reviewer objection with a measurement rather than an
argument. Results land in results/canonical_numbers.json under `sensitivity`.

  screen_size          The negative result rests on 142 documented non-control
                       pairs and has only 57% power at a true enrichment of 2.0.
                       Widening the screen adds documented pairs and tightens
                       the bound.

  drug_selection       Screened drugs are chosen by co-reporting WITH the event
                       -- selection on the dependent variable. Reselecting by
                       total report volume tests whether that drives anything.

  era_bins             The three era boundaries were never varied, and the
                       era-stability result is sensitive to threshold choice.

  ingredient_accuracy  Resolution coverage was reported; accuracy never was.
                       Where one verbatim drug name carries FDA's own prod_ai
                       annotation on many rows, the consistency of that
                       annotation bounds how reliable the backfill can be.

  demographic_strata   No subgroup analysis, despite sex, age and country being
                       parsed. Reporting differs by subgroup in FAERS.
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
from faers_ddi import contingency, screen, statistics as st, tier_a, tier_b

log = logging.getLogger("sensitivity")


def _endpoint_reference() -> set:
    path = cfg.path("tables") / "label_myotoxicity_reference.csv"
    if not path.exists():
        return set()
    with path.open() as fh:
        return {tuple(row) for row in list(csv.reader(fh))[1:]}


def _enrichment(rows, reference, control_drugs, threshold):
    subset = [r for r in rows
              if r["drug_a"] not in control_drugs and r["drug_b"] not in control_drugs]
    documented = [(r["drug_a"], r["drug_b"]) in reference for r in subset]
    signal = [r["omega_add_lower"] > threshold for r in subset]
    counts = [r["n_ab"] for r in subset]
    k_doc = sum(s for s, d in zip(signal, documented) if d)
    n_doc = sum(documented)
    k_und = sum(s for s, d in zip(signal, documented) if not d)
    n_und = len(documented) - n_doc
    if not (n_doc and n_und and k_doc and k_und):
        return {"documented_tested": n_doc, "documented_signalled": k_doc,
                "enrichment": None, "enrichment_ci": None, "stratified": None}
    lo, hi = st.ratio_ci(k_doc, n_doc, k_und, n_und)
    # The crude interval treats every pair as an independent trial. With each
    # drug in hundreds of pairs that is anticonservative: crude intervals
    # excluded unity at top-400 and top-800 where the cluster bootstrap, which
    # resamples DRUGS, does not.
    boot = st.mantel_haenszel_bootstrap(
        [(r["drug_a"], r["drug_b"]) for r in subset],
        signal, documented, counts, n_boot=1000, seed=20260802)
    return {
        "documented_tested": n_doc, "documented_signalled": k_doc,
        "undocumented_tested": n_und, "undocumented_signalled": k_und,
        "enrichment": round((k_doc / n_doc) / (k_und / n_und), 2),
        "enrichment_ci_pairwise_ANTICONSERVATIVE": [round(lo, 2), round(hi, 2)],
        "stratified": boot["ratio"],
        "stratified_ci_cluster_bootstrap": boot["ci"],
        "stratified_excludes_unity": boot.get("excludes_unity"),
    }


def screen_size(con, tier, threshold, control_drugs, reference, sizes=(200, 400, 800)):
    """Does widening the screen tighten the bound on the negative result?"""
    out = []
    for size in sizes:
        contingency.build_case_drugs(con, "primary")
        contingency.drug_marginals(con, tier)
        drugs = screen.screen_drugs(con, size)
        contingency.pair_counts(con, drugs, tier,
                                min_pair=cfg.load_config()["analysis"]["min_co_reports"])
        rows = contingency.score(con, tier)
        result = _enrichment(rows, reference, control_drugs, threshold)
        result.update({"n_drugs": len(drugs), "n_pairs": len(rows)})
        out.append(result)
        log.info("  top-%d: %d pairs, %d documented non-control, stratified %s "
                 "CI %s (excludes unity: %s)",
                 size, len(rows), result["documented_tested"], result["stratified"],
                 result["stratified_ci_cluster_bootstrap"],
                 result["stratified_excludes_unity"])
    return out


def drug_selection(con, tier, threshold, control_drugs, reference, top_n=200):
    """Screened drugs are selected on the outcome. Does that drive the result?"""
    out = {}
    for label, order in (("by_event_coreporting", "n_drug_event DESC"),
                         ("by_total_volume", "n_drug DESC")):
        contingency.build_case_drugs(con, "primary")
        contingency.drug_marginals(con, tier)
        drugs = [r[0] for r in con.execute(
            f"SELECT ingredient FROM drug_marginals WHERE n_drug_event > 0 "
            f"ORDER BY {order}, ingredient LIMIT {top_n}").fetchall()]
        contingency.pair_counts(con, drugs, tier,
                                min_pair=cfg.load_config()["analysis"]["min_co_reports"])
        rows = contingency.score(con, tier)
        result = _enrichment(rows, reference, control_drugs, threshold)
        result["n_pairs"] = len(rows)
        out[label] = result
        log.info("  %-22s %d pairs, stratified %s CI %s",
                 label, len(rows), result["stratified"],
                 result["stratified_ci_cluster_bootstrap"])
    overlap = None
    out["note"] = ("selection by event co-reporting is selection on the dependent "
                   "variable; selection by total volume is not")
    return out


def era_bins(con, tier, threshold, drugs, definitions):
    """The three era boundaries were fixed by hand and never varied."""
    out = []
    for name, bins in definitions:
        per_bin = []
        for start, end in bins:
            con.execute(f"""
                CREATE OR REPLACE TABLE _sb AS SELECT f.* FROM case_flags f
                JOIN cases_deduped c USING (case_id)
                WHERE c.quarter >= '{start}' AND c.quarter <= '{end}'""")
            con.execute("""CREATE OR REPLACE TABLE _sd AS SELECT d.* FROM case_drugs d
                           SEMI JOIN _sb f USING (case_id)""")
            con.execute("CREATE OR REPLACE TABLE _kf AS SELECT * FROM case_flags")
            con.execute("CREATE OR REPLACE TABLE _kd AS SELECT * FROM case_drugs")
            con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _sb")
            con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _sd")
            contingency.drug_marginals(con, tier)
            contingency.pair_counts(con, drugs, tier,
                                    min_pair=cfg.load_config()["analysis"]["min_co_reports"])
            per_bin.append({(r["drug_a"], r["drug_b"]): r["omega_add_lower"]
                            for r in contingency.score(con, tier)})
            con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _kf")
            con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _kd")
        contingency.drug_marginals(con, tier)
        contingency.pair_counts(con, drugs, tier,
                                min_pair=cfg.load_config()["analysis"]["min_co_reports"])
        rows = contingency.score(con, tier)
        stable = [r for r in rows
                  if r["omega_add_lower"] > threshold
                  and all(b.get((r["drug_a"], r["drug_b"]), -99) > threshold
                          for b in per_bin)]
        out.append({"definition": name, "n_bins": len(bins), "n_stable": len(stable)})
        log.info("  %-18s %d bins -> %d era-stable pairs", name, len(bins), len(stable))
    return out


def ingredient_accuracy(con):
    """How consistent is FDA's own prod_ai annotation for one verbatim name?

    Level-2 resolution copies the prod_ai attached to the same verbatim string
    elsewhere. Its ceiling is therefore how often FDA itself gives one string a
    single ingredient. Measured over strings appearing on at least 20 annotated
    rows.
    """
    row = con.execute("""
        WITH annotated AS (
            SELECT upper(trim(drugname)) AS name, upper(trim(prod_ai)) AS ingredient,
                   count(*) AS n
            -- union_by_name: prod_ai exists only from 2014Q3, so the
            -- schemas differ across the glob.
            FROM read_parquet(?, union_by_name=true)
            WHERE trim(prod_ai) <> '' AND trim(drugname) <> ''
            GROUP BY 1, 2
        ), totals AS (
            SELECT name, sum(n) AS total, max(n) AS modal FROM annotated
            GROUP BY 1 HAVING sum(n) >= 20
        )
        SELECT count(*), sum(total), sum(modal),
               count(*) FILTER (WHERE modal = total)
        FROM totals
    """, [str(cfg.path("parquet") / "drug" / "*.parquet")]).fetchone()
    names, total_rows, modal_rows, unanimous = row
    return {
        "names_examined": names,
        "rows_examined": int(total_rows),
        "modal_agreement": round(modal_rows / total_rows, 4),
        "names_unanimous": unanimous,
        "fraction_unanimous": round(unanimous / names, 4),
        "note": "upper bound on level-2 backfill accuracy; FDA's own annotation "
                "of one verbatim string is this consistent",
    }


def demographic_strata(con, tier, threshold, drugs, control_drugs, reference):
    """Signal behaviour by sex. Reporting differs by subgroup in FAERS."""
    out = []
    for label, predicate in (("female", "c.sex = 'F'"), ("male", "c.sex = 'M'")):
        con.execute(f"""
            CREATE OR REPLACE TABLE _sb AS SELECT f.* FROM case_flags f
            JOIN cases_deduped c USING (case_id) WHERE {predicate}""")
        con.execute("""CREATE OR REPLACE TABLE _sd AS SELECT d.* FROM case_drugs d
                       SEMI JOIN _sb f USING (case_id)""")
        con.execute("CREATE OR REPLACE TABLE _kf AS SELECT * FROM case_flags")
        con.execute("CREATE OR REPLACE TABLE _kd AS SELECT * FROM case_drugs")
        con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _sb")
        con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _sd")
        n_total, n_event = contingency.totals(con, tier)
        contingency.drug_marginals(con, tier)
        contingency.pair_counts(con, drugs, tier,
                                min_pair=cfg.load_config()["analysis"]["min_co_reports"])
        rows = contingency.score(con, tier)
        result = _enrichment(rows, reference, control_drugs, threshold)
        result.update({"stratum": label, "n_cases": n_total, "n_event_cases": n_event,
                       "event_rate": round(n_event / n_total, 5), "n_pairs": len(rows)})
        out.append(result)
        con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _kf")
        con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _kd")
        log.info("  %-7s %d cases, event rate %.3f%%, stratified %s CI %s",
                 label, n_total, 100 * n_event / n_total, result["stratified"],
                 result["stratified_ci_cluster_bootstrap"])
    return out


def independent_positive_controls(con, tier, threshold, control_drugs, reference):
    """A positive control set the authors did not choose.

    The 16 controls were author-selected and are the only positive evaluation
    set; leave-one-out addresses optimism in the ESTIMAND choice, not in the
    choice of controls. Label-documented myotoxicity pairs that are NOT among
    the 16 form a set selected by FDA labelling rather than by us.

    They are not independent of FAERS -- labelling is informed by surveillance --
    so this bounds author-selection bias, not data-derived bias.
    """
    contingency.build_case_drugs(con, "primary")
    contingency.drug_marginals(con, tier)
    drugs = screen.screen_drugs(con, 800)
    contingency.pair_counts(con, drugs, tier, min_pair=1)
    scored = contingency.score(con, tier)
    authors = {tuple(sorted((c["drug_a"].strip().upper(),
                             c["drug_b"].strip().upper())))
               for c in tier_a.load_positive_controls()}
    held_out = [r for r in scored
                if (r["drug_a"], r["drug_b"]) in reference
                and (r["drug_a"], r["drug_b"]) not in authors
                and r["n_ab"] >= 50]
    if not held_out:
        return {"n_pairs": 0}
    # Both nulls at BOTH operating points. An earlier version scored the
    # multiplicative null at 0 and the additive one at the calibrated +0.436,
    # then printed the result beside the Tier A row where both are at 0. The
    # asymmetry ran against the additive null, so the finding survived, but the
    # table as published was not a like-for-like comparison.
    mult_zero = sum(r["omega_lower"] > 0 for r in held_out)
    add_zero = sum(r["omega_add_lower"] > 0 for r in held_out)
    mult_cal = sum(r["omega_lower"] > threshold for r in held_out)
    add_cal = sum(r["omega_add_lower"] > threshold for r in held_out)
    lo_m, hi_m = st.proportion_ci(mult_zero, len(held_out))
    lo_a, hi_a = st.proportion_ci(add_zero, len(held_out))
    return {
        "note": "label-documented myotoxicity pairs excluding the 16 author-chosen "
                "controls; selected by FDA labelling, not by the authors. Both "
                "nulls reported at both thresholds -- Tier A uses 0, the screen "
                "uses the calibrated threshold.",
        "n_pairs": len(held_out),
        "threshold_calibrated": threshold,
        "recovered_multiplicative": mult_zero,
        "recovered_multiplicative_ci": [round(lo_m, 3), round(hi_m, 3)],
        "recovered_additive": add_zero,
        "recovered_additive_ci": [round(lo_a, 3), round(hi_a, 3)],
        "at_threshold_zero": {"multiplicative": mult_zero, "additive": add_zero},
        "at_calibrated_threshold": {"multiplicative": mult_cal, "additive": add_cal},
        "examples": sorted(
            ({"pair": f"{r['drug_a']}+{r['drug_b']}", "n_ab": r["n_ab"],
              "n_abz": r["n_abz"], "omega": round(r["omega"], 2),
              "omega_add_lower": round(r["omega_add_lower"], 2)}
             for r in held_out), key=lambda x: -x["n_ab"])[:10],
    }


def pt_list_second_annotation(con) -> dict:
    """A mechanically independent second pass over the event definition.

    The PT list had a single curator and no inter-rater statistic. A second
    human is not available, so the comparison here is against a mechanical
    annotation: every PT in REAC whose text matches the myotoxicity vocabulary
    used to build the label reference, which was written for a different purpose.

    This is weaker than a second reader -- it cannot exercise judgement about
    whether a term denotes the intended clinical entity -- so it is reported as
    a coverage check, not as a kappa.
    """
    import re
    from faers_ddi.label_reference import MYOTOXICITY_TERMS
    curated = {r["pt"] for r in __import__(
        "faers_ddi.define_event", fromlist=["load_pt_list"]).load_pt_list()}
    vocab = con.execute(
        "SELECT pt, reports FROM pt_vocab WHERE reports >= 25").fetchall()
    mechanical = {pt for pt, _ in vocab if MYOTOXICITY_TERMS.search(pt)}
    reports = dict(vocab)
    both = curated & mechanical
    curated_only = curated - mechanical
    mechanical_only = mechanical - curated
    return {
        "note": "mechanical second annotation, not a second human reader",
        "curated_terms": len(curated),
        "mechanical_terms": len(mechanical),
        "agreed": len(both),
        "curated_only": sorted(curated_only),
        "mechanical_only_top": sorted(
            mechanical_only, key=lambda p: -reports.get(p, 0))[:15],
        "jaccard": round(len(both) / len(curated | mechanical), 3),
        "curated_recall_of_mechanical": round(len(both) / len(mechanical), 3)
        if mechanical else None,
    }


def residual_near_duplicates(con, tier) -> dict:
    """How many duplicates does the exact drug-set rule miss?

    Phase 3 merges cases whose drug sets match EXACTLY. The alirocumab cluster
    that dominated the first screen was precisely a set of near-identical
    reports whose drug lists differed slightly, so the rule provably misses the
    cases that matter most.

    Measured here on the EVENT cases, which are what the result depends on:
    among cases sharing event date, age, sex and country, how many further pairs
    have drug-set Jaccard above 0.8 without being exactly equal?
    """
    con.execute(f"""
        CREATE OR REPLACE TABLE _event_sets AS
        SELECT c.case_id, c.event_dt, c.age_years, c.sex, c.country,
               list_sort(list(DISTINCT d.ingredient)) AS drugs
        FROM cases_deduped c
        JOIN case_events e ON e.case_id = c.case_id AND e.is_{tier}
        JOIN case_drugs d ON d.case_id = c.case_id
        WHERE c.event_dt <> '' AND c.age_years IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5
    """)
    total = con.execute("SELECT count(*) FROM _event_sets").fetchone()[0]

    # Block on the demographic fingerprint, then compare drug sets within block.
    row = con.execute("""
        WITH blocked AS (
            SELECT a.case_id AS a_id, b.case_id AS b_id,
                   a.drugs AS a_drugs, b.drugs AS b_drugs
            FROM _event_sets a
            JOIN _event_sets b
              ON a.event_dt = b.event_dt AND a.age_years = b.age_years
             AND a.sex = b.sex AND a.country = b.country
             AND a.case_id < b.case_id
        ), scored AS (
            SELECT a_id, b_id,
                   len(list_intersect(a_drugs, b_drugs))::DOUBLE
                     / nullif(len(list_distinct(list_concat(a_drugs, b_drugs))), 0) AS jaccard,
                   a_drugs = b_drugs AS exact_match
            FROM blocked
        )
        SELECT count(*),
               count(*) FILTER (WHERE exact_match),
               count(*) FILTER (WHERE NOT exact_match AND jaccard >= 0.8),
               count(DISTINCT b_id) FILTER (WHERE NOT exact_match AND jaccard >= 0.8)
        FROM scored
    """).fetchone()
    compared, exact, fuzzy, fuzzy_cases = row
    return {
        "note": "event cases with a populated event date and age; blocked on "
                "event date, age, sex and country",
        "event_cases_examined": total,
        "within_block_pairs_compared": compared,
        "exact_drug_set_matches": exact,
        "additional_jaccard_0_8_matches": fuzzy,
        "cases_removable_by_fuzzy_rule": fuzzy_cases,
        "share_of_event_cases": round(fuzzy_cases / total, 5) if total else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(cfg.path("logs") / "sensitivity.log"),
                  logging.StreamHandler(sys.stdout)], force=True)

    canonical = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
    numbers = json.loads(canonical.read_text())
    conf = cfg.load_config()
    tier = conf["event"]["primary_tier"]
    threshold = numbers["tier_b"]["calibrated_threshold"]
    reference = _endpoint_reference()
    control_drugs = {d for c in tier_a.load_positive_controls()
                     for d in (c["drug_a"].strip().upper(), c["drug_b"].strip().upper())}

    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    results = {}
    log.info("--- screen size (power on the negative result) ---")
    results["screen_size"] = screen_size(con, tier, threshold, control_drugs, reference)

    log.info("--- drug selection criterion ---")
    results["drug_selection"] = drug_selection(con, tier, threshold, control_drugs, reference)

    log.info("--- era bin definitions ---")
    contingency.build_case_drugs(con, "primary")
    contingency.drug_marginals(con, tier)
    drugs = screen.screen_drugs(con, conf["analysis"]["screen"]["top_n_drugs"])
    results["era_bins"] = era_bins(con, tier, threshold, drugs, [
        ("3 bins (primary)", [("2004q1", "2012q4"), ("2013q1", "2018q4"),
                              ("2019q1", "2026q2")]),
        ("2 bins", [("2004q1", "2014q4"), ("2015q1", "2026q2")]),
        ("4 bins", [("2004q1", "2009q4"), ("2010q1", "2015q4"),
                    ("2016q1", "2021q4"), ("2022q1", "2026q2")]),
        ("5 bins", [("2004q1", "2008q4"), ("2009q1", "2012q4"),
                    ("2013q1", "2017q4"), ("2018q1", "2022q4"),
                    ("2023q1", "2026q2")]),
    ])

    log.info("--- ingredient resolution accuracy ---")
    results["ingredient_accuracy"] = ingredient_accuracy(con)
    ia = results["ingredient_accuracy"]
    log.info("  %d names, %.2f%% modal agreement, %.1f%% unanimous",
             ia["names_examined"], 100 * ia["modal_agreement"],
             100 * ia["fraction_unanimous"])

    log.info("--- residual near-duplicates (fuzzy drug-set match) ---")
    contingency.build_case_drugs(con, "primary")
    results["residual_near_duplicates"] = residual_near_duplicates(con, tier)
    rd = results["residual_near_duplicates"]
    log.info("  %d event cases; %d exact matches already merged; %d further "
             "pairs at Jaccard>=0.8 affecting %d cases (%.3f%% of event cases)",
             rd["event_cases_examined"], rd["exact_drug_set_matches"],
             rd["additional_jaccard_0_8_matches"], rd["cases_removable_by_fuzzy_rule"],
             100 * (rd["share_of_event_cases"] or 0))

    log.info("--- independent positive controls ---")
    results["independent_positive_controls"] = independent_positive_controls(
        con, tier, threshold, control_drugs, reference)
    ipc = results["independent_positive_controls"]
    if ipc["n_pairs"]:
        log.info("  %d label-selected pairs: multiplicative %d, additive %d",
                 ipc["n_pairs"], ipc["recovered_multiplicative"],
                 ipc["recovered_additive"])

    log.info("--- PT list second annotation ---")
    results["pt_second_annotation"] = pt_list_second_annotation(con)
    pa = results["pt_second_annotation"]
    log.info("  curated %d, mechanical %d, agreed %d, Jaccard %.2f",
             pa["curated_terms"], pa["mechanical_terms"], pa["agreed"],
             pa["jaccard"])

    log.info("--- demographic strata ---")
    contingency.build_case_drugs(con, "primary")
    contingency.drug_marginals(con, tier)
    results["demographic_strata"] = demographic_strata(
        con, tier, threshold, drugs, control_drugs, reference)

    numbers["sensitivity"] = results
    numbers.setdefault("stages", []).append("sensitivity")
    numbers["stages"] = sorted(set(numbers["stages"]))
    canonical.write_text(json.dumps(numbers, indent=2, sort_keys=True) + "\n")
    log.info("sensitivity results merged into %s", canonical)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
