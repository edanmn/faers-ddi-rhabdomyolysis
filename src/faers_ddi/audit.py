"""Analyses answering the round-7 review, which challenged the inference layer.

Rounds 1-6 hardened the pipeline. Round 7 attacked the statistics on top of it
and four objections could only be answered by computing something new.

  induced_correlation   The paper's signature finding is that Omega correlates
                        NEGATIVELY with the strength of the two drugs' marginal
                        associations, framed as a defect of the MULTIPLICATIVE
                        null. But Omega = log2(O/E) and E is an increasing
                        function of those same marginals, so regressing Omega on
                        them is regressing a residual on a proxy for its own
                        denominator (Oldham's fallacy). This decomposes the
                        correlation into its observed and expected parts,
                        computes it for BOTH nulls, and simulates the value
                        induced under a no-three-way-interaction null.

  heldout_calibration   The signal threshold is the 95th percentile of the same
                        negative-control pool whose false-positive rate is then
                        reported, so the "5%" is definitional rather than
                        measured. This calibrates on one half and measures on
                        the other, repeatedly.

  reference_coverage    17.2% of screened ingredients have NO openFDA label at
                        all -- including cerivastatin, bezafibrate, ciprofibrate
                        and fusidic acid, i.e. the endpoint's defining classes.
                        Every pair containing one is scored "undocumented" and
                        lands in the denominator of the null. This quantifies
                        the blindness and re-runs enrichment restricted to pairs
                        where both labels exist, so "undocumented" means the
                        label is silent rather than absent.

  fdr_screen            17,375 pairs were tested with no multiplicity control
                        beyond a threshold that is itself in-sample. Benjamini-
                        Hochberg on exact Poisson tail probabilities gives a
                        discovery count that does not depend on that
                        calibration.

  top_ranked_pairs      The screen's highest-event-rate pair is atorvastatin +
                        fusidic acid, a contraindicated combination, banded
                        "plausible" because neither reference contains it. The
                        two era-stable pairs in that band were never examined
                        for confounding the way section 4.7 examines the eight
                        unsupported ones.

  cap_sweep             The 20-drug polypharmacy cap was chosen because it
                        improved sensitivity AND the false-positive rate --
                        selection on the evaluation set, previously undisclosed.

Results land in results/canonical_numbers.json under `audit`.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import logging
import sys

import duckdb
import numpy as np
from scipy import stats

from faers_ddi import config as cfg
from faers_ddi import contingency, define_event, omega as om, screen, statistics as st, tier_a, tier_b

log = logging.getLogger("audit")

N_SIMULATIONS = 10_000
N_SPLITS = 500
SEED = 20260803


# --------------------------------------------------------------------------
# R1  Is the Omega-vs-marginals correlation a property of the multiplicative
#     null, or of any log(observed/expected) statistic?
# --------------------------------------------------------------------------

def _pearson(x, y) -> float:
    return float(np.corrcoef(np.asarray(x, float), np.asarray(y, float))[0, 1])


def induced_correlation(rows: list[dict], alpha: float) -> dict:
    """Decompose r(Omega, log2(RR_a*RR_b)) and simulate its value under the null.

    The claim under test is that Omega grows more negative as the marginal
    associations strengthen BECAUSE the multiplicative null is wrong for
    drug-dominant events. If that is right, the additive null -- the remedy this
    paper adopts -- should not show the same gradient, and the correlation
    should exceed what the estimator induces mechanically.
    """
    usable = [r for r in rows if r["n_ab"] and r["expected"] and r["additive_expected"]]
    x = np.array([np.log2(r["rr_a"] * r["rr_b"]) for r in usable])
    n_ab = np.array([r["n_ab"] for r in usable], float)
    n_abz = np.array([r["n_abz"] for r in usable], float)
    exp_mult = np.array([r["expected"] for r in usable], float)
    exp_add = np.array([r["additive_expected"] for r in usable], float)

    observed_rate = np.log2(np.maximum(n_abz, 0.5) / n_ab)
    omega_mult = np.log2((n_abz + alpha) / (exp_mult + alpha))
    omega_add = np.log2((n_abz + alpha) / (exp_add + alpha))

    def simulate(expected: np.ndarray) -> dict:
        """Null distribution of r when the model generating the data IS the null.

        Draw the triple count from the model's own expectation, recompute the
        statistic, and correlate against the (fixed) marginal strength. Any
        correlation here is induced by the construction, not by interaction.
        """
        rng = np.random.default_rng(SEED)
        p = np.clip(expected / n_ab, 1e-12, 1.0)
        draws = rng.binomial(n_ab.astype(int), p, size=(N_SIMULATIONS, len(p)))
        stat = np.log2((draws + alpha) / (expected + alpha))
        # corrcoef row-wise against the fixed x
        xc = x - x.mean()
        sc = stat - stat.mean(axis=1, keepdims=True)
        r = (sc @ xc) / np.sqrt((sc ** 2).sum(axis=1) * (xc ** 2).sum())
        r = r[np.isfinite(r)]
        return {
            "median": round(float(np.median(r)), 3),
            "ci": [round(float(np.percentile(r, 2.5)), 3),
                   round(float(np.percentile(r, 97.5)), 3)],
        }

    r_mult, r_add = _pearson(x, omega_mult), _pearson(x, omega_add)
    null_mult, null_add = simulate(exp_mult), simulate(exp_add)
    return {
        "n": len(usable),
        "note": "x = log2(RR_a * RR_b). Omega = log2((O+a)/(E+a)); E rises with x "
                "by construction, so a negative r is partly mechanical. The null "
                "simulation draws O from each model's own expectation.",
        "r_omega_multiplicative": round(r_mult, 3),
        "r_omega_additive": round(r_add, 3),
        "r_observed_event_rate": round(_pearson(x, observed_rate), 3),
        "r_expected_multiplicative": round(_pearson(x, np.log2(exp_mult / n_ab)), 3),
        "r_expected_additive": round(_pearson(x, np.log2(exp_add / n_ab)), 3),
        "null_r_multiplicative": null_mult,
        "null_r_additive": null_add,
        "multiplicative_exceeds_null": bool(r_mult < null_mult["ci"][0]),
        "additive_exceeds_null": bool(r_add < null_add["ci"][0]),
        "both_nulls_show_the_gradient": bool(r_add < 0 and r_mult < 0),
    }


# --------------------------------------------------------------------------
# R2  The threshold is a quantile of the sample it is evaluated on.
# --------------------------------------------------------------------------

def heldout_calibration(values: np.ndarray, target: float = 0.05) -> dict:
    """Calibrate on half the negative controls, measure on the other half.

    A quantile evaluated on the sample that defined it returns the target
    exactly, by construction. Splitting makes the reported rate a measurement.
    """
    rng = np.random.default_rng(SEED)
    n = len(values)
    thresholds, rates = [], []
    for _ in range(N_SPLITS):
        order = rng.permutation(n)
        fit, test = values[order[: n // 2]], values[order[n // 2:]]
        threshold = float(np.quantile(fit, 1 - target))
        thresholds.append(threshold)
        rates.append(float((test > threshold).mean()))
    rates = np.array(rates)
    return {
        "target_fpr": target,
        "n_negative_controls": n,
        "n_splits": N_SPLITS,
        "in_sample_threshold": round(float(np.quantile(values, 1 - target)), 3),
        "heldout_threshold_median": round(float(np.median(thresholds)), 3),
        "heldout_fpr_mean": round(float(rates.mean()), 4),
        "heldout_fpr_ci": [round(float(np.percentile(rates, 2.5)), 4),
                           round(float(np.percentile(rates, 97.5)), 4)],
        "note": "in-sample calibration returns the target by construction; the "
                "held-out rate is the measured one",
    }


# --------------------------------------------------------------------------
# R6  How much of the screen can the label reference not see at all?
# --------------------------------------------------------------------------

def _labelled_ingredients() -> tuple[set[str], set[str]]:
    """Ingredients openFDA returned a label for, and those it did not."""
    found, missing = set(), set()
    for path in glob.glob(str(cfg.PROJECT_ROOT / "data" / "reference"
                              / "openfda_labels" / "*.json")):
        with open(path) as fh:
            payload = json.load(fh)
        (found if payload.get("found") else missing).add(payload["ingredient"])
    return found, missing


def reference_coverage(rows: list[dict], reference: set, control_drugs: set,
                       threshold: float) -> dict:
    """Enrichment restricted to pairs whose two labels both exist.

    A pair containing a drug with no FDA label can never be `label_documented`,
    so scoring it "undocumented" imports a structural zero into the denominator.
    Restricting to label-covered pairs makes "undocumented" mean the label is
    SILENT about the partner rather than absent entirely.
    """
    found, missing = _labelled_ingredients()
    endpoint_relevant = sorted(missing & tier_b.MYOTOXICITY_IMPLICATED)
    blind = [r for r in rows if r["drug_a"] in missing or r["drug_b"] in missing]

    covered = [r for r in rows
               if r["drug_a"] in found and r["drug_b"] in found
               and r["drug_a"] not in control_drugs
               and r["drug_b"] not in control_drugs]
    documented = [(r["drug_a"], r["drug_b"]) in reference for r in covered]
    signal = [r["omega_add_lower"] > threshold for r in covered]
    counts = [r["n_ab"] for r in covered]
    k_doc, n_doc = sum(s for s, d in zip(signal, documented) if d), sum(documented)
    k_und, n_und = sum(s for s, d in zip(signal, documented) if not d), \
        len(documented) - sum(documented)

    # The blindness that bears on the screen is over the SCREENED ingredients,
    # not over the label cache. The cache was built out to 800 drugs for the
    # screen-size sensitivity analysis; reporting 138/800 as the screen's
    # blindness overstated it threefold and cited four drugs the screen never
    # contained.
    screened = {d for r in rows for d in (r["drug_a"], r["drug_b"])}
    screened_missing = screened & missing
    out = {
        "ingredients_cached": len(found) + len(missing),
        "ingredients_without_any_label": len(missing),
        "share_without_label": round(len(missing) / (len(found) + len(missing)), 4),
        "screened_ingredients": len(screened),
        "screened_without_label": len(screened_missing),
        "screened_share_without_label": round(len(screened_missing) / len(screened), 4),
        "screened_without_label_names": sorted(screened_missing),
        "cited_but_not_screened": sorted(
            {"CERIVASTATIN", "BEZAFIBRATE", "CIPROFIBRATE", "TELITHROMYCIN"}
            - screened),
        "endpoint_relevant_without_label": endpoint_relevant,
        "pairs_total": len(rows),
        "pairs_touching_an_unlabelled_drug": len(blind),
        # NOT rounded to 4dp. Round-19 found the paper quoting 9.8% where
        # 1712/17375 = 9.853% -> 9.9%: the value was stored pre-rounded and
        # then re-rounded for display, and the guard re-derived the paper's
        # figure from the same rounded intermediate, so it could not fail.
        "share_of_pairs_structurally_undocumentable": len(blind) / len(rows),
        "documented_tested": n_doc,
        "documented_signalled": k_doc,
        "undocumented_tested": n_und,
        "undocumented_signalled": k_und,
        "note": "restricted to non-control pairs where BOTH drugs have an FDA "
                "label, so 'undocumented' means the label is silent, not absent",
    }
    if n_doc and n_und and k_doc and k_und:
        lo, hi = st.ratio_ci(k_doc, n_doc, k_und, n_und)
        out["enrichment"] = round((k_doc / n_doc) / (k_und / n_und), 2)
        out["enrichment_ci_pairwise_ANTICONSERVATIVE"] = [round(lo, 2), round(hi, 2)]
        boot = st.mantel_haenszel_bootstrap(
            [(r["drug_a"], r["drug_b"]) for r in covered],
            signal, documented, counts, n_boot=1000, seed=SEED)
        out["stratified"] = boot["ratio"]
        out["stratified_ci_cluster_bootstrap"] = boot["ci"]
        out["stratified_excludes_unity"] = boot.get("excludes_unity")
    return out


# --------------------------------------------------------------------------
# Multiplicity: 17,375 tests, no correction anywhere in the paper.
# --------------------------------------------------------------------------

def fdr_screen(rows: list[dict], q: float = 0.05) -> dict:
    """Benjamini-Hochberg on exact Poisson tail probabilities.

    The shrinkage bound Omega_add,025 > t is not a p-value and carries no
    multiplicity guarantee; the threshold that stands in for one is calibrated
    in-sample (see heldout_calibration). A one-sided Poisson test of the triple
    count against the additive expectation is a frequentist statement about the
    same null and admits standard FDR control.

    Poisson rather than binomial because the expectation is a rate estimate, not
    a fixed probability; the two agree closely at these counts and the Poisson
    tail is the more conservative of the pair here.
    """
    observed = np.array([r["n_abz"] for r in rows], float)
    expected = np.array([r["additive_expected"] for r in rows], float)
    p = stats.poisson.sf(observed - 1, np.maximum(expected, 1e-12))
    order = np.argsort(p)
    ranked = p[order]
    m = len(p)
    crit = q * np.arange(1, m + 1) / m
    passing = np.where(ranked <= crit)[0]
    k = int(passing[-1] + 1) if len(passing) else 0
    discoveries = set(order[:k].tolist())
    threshold_rows = [rows[i] for i in sorted(discoveries)]
    return {
        "method": "Benjamini-Hochberg on one-sided Poisson tail probabilities",
        "q": q,
        "n_tested": m,
        "n_discoveries": k,
        "n_signalled_by_shrinkage_threshold": sum(
            r["omega_add_lower"] > cfg.load_config()["analysis"]["omega"]["signal_threshold"]
            for r in rows),
        "overlap_with_shrinkage_signals": sum(
            1 for r in threshold_rows
            if r["omega_add_lower"] > cfg.load_config()["analysis"]["omega"]["signal_threshold"]),
        "note": "the shrinkage bound is not a p-value and carries no multiplicity "
                "guarantee; this is the FDR-controlled count for comparison",
    }


# --------------------------------------------------------------------------
# R7 / R8  The top of the ranking, and the band the paper said it was watching.
# --------------------------------------------------------------------------

def top_ranked_pairs(rows: list[dict], min_pair: int = 150, top: int = 10) -> dict:
    """Rank every screened pair by event rate among its co-reports.

    Section 4.7 examines the eight era-stable pairs banded `unsupported` and
    concludes no pair is a genuine interaction. It never examines the two banded
    `plausible` -- the band designated in advance as where a novel interaction
    would appear -- nor the head of this ranking.
    """
    eligible = [r for r in rows if r["n_ab"] >= min_pair]
    ranked = sorted(eligible, key=lambda r: -(r["n_abz"] / r["n_ab"]))
    def fmt(r):
        return {
            "pair": f"{r['drug_a']}+{r['drug_b']}",
            "n_ab": r["n_ab"], "n_abz": r["n_abz"],
            "event_rate": round(r["n_abz"] / r["n_ab"], 4),
            "band": r["support"],
            "omega_add_lower": round(r["omega_add_lower"], 3),
            "eras_with_signal": r.get("eras_with_signal"),
        }
    controls = [r for r in ranked if r["support"] == "positive_control"]
    return {
        "min_pair": min_pair,
        "n_ranked": len(ranked),
        "top": [fmt(r) for r in ranked[:top]],
        "best_positive_control": fmt(controls[0]) if controls else None,
        "n_non_control_above_best_control": sum(
            1 for r in ranked[:ranked.index(controls[0])] if controls) if controls else 0,
    }


def era_stable_plausible(con: duckdb.DuckDBPyConnection, tier: str,
                         pairs: list[tuple[str, str]]) -> list[dict]:
    """Confounder profile for named pairs, as section 4.7 does for the others.

    Reports what share of each pair's event cases also carry a drug already
    implicated in myotoxicity -- the test that showed the eight unsupported
    era-stable pairs to be statin proxies.
    """
    implicated = ", ".join(f"'{d}'" for d in sorted(tier_b.MYOTOXICITY_IMPLICATED))
    flag = "is_core" if tier == "core" else "is_broad"
    background = con.execute(f"""
        SELECT avg(CASE WHEN n_impl > 0 THEN 1.0 ELSE 0.0 END)
        FROM (SELECT d.case_id, sum(CASE WHEN d.ingredient IN ({implicated})
                                         THEN 1 ELSE 0 END) AS n_impl
              FROM case_drugs d JOIN case_flags f USING (case_id)
              WHERE f.{flag} GROUP BY d.case_id)
    """).fetchone()[0]

    out = []
    for a, b in pairs:
        row = con.execute(f"""
            WITH pair_cases AS (
                SELECT f.case_id
                FROM case_flags f
                WHERE f.{flag}
                  AND EXISTS (SELECT 1 FROM case_drugs d
                              WHERE d.case_id = f.case_id AND d.ingredient = ?)
                  AND EXISTS (SELECT 1 FROM case_drugs d
                              WHERE d.case_id = f.case_id AND d.ingredient = ?)
            )
            SELECT count(*),
                   sum(CASE WHEN EXISTS (
                        SELECT 1 FROM case_drugs d
                        WHERE d.case_id = pair_cases.case_id
                          AND d.ingredient IN ({implicated})
                          AND d.ingredient NOT IN (?, ?)) THEN 1 ELSE 0 END)
            FROM pair_cases
        """, [a, b, a, b]).fetchone()
        n_event, n_other = row[0] or 0, row[1] or 0
        out.append({
            "pair": f"{a}+{b}",
            "event_cases": n_event,
            "event_cases_with_another_implicated_drug": int(n_other),
            "share": round(n_other / n_event, 4) if n_event else None,
            "background_share": round(float(background), 4),
        })
    return out


# --------------------------------------------------------------------------
# The polypharmacy cap was chosen on the evaluation set.
# --------------------------------------------------------------------------

def top_ranked_pairs(con: duckdb.DuckDBPyConnection, tier: str,
                     screen_rows: list[dict], reference: set,
                     threshold: float, top_n: int = 5) -> dict:
    """The screen's highest-event-rate signals, and whether they are proxies.

    Round 29. The screen's top-ranked pairs were discussed one at a time in the
    prose. Ranking them and applying the same third-drug test §4.7 uses for the
    era-stable pairs makes the check reproducible, and separates pairs whose
    event rate is carried by a co-reported statin from pairs where it is not.
    A known proxy scores near 100%; a pair carrying its own signal scores near
    zero.
    """
    implicated = sorted(tier_b.MYOTOXICITY_IMPLICATED)
    flag = "is_core" if tier == "core" else "is_broad"
    ranked = []
    for row in screen_rows:
        try:
            n_ab, n_abz = float(row["n_ab"]), float(row["n_abz"])
            lower = float(row["omega_add_lower"])
        except (TypeError, ValueError, KeyError):
            continue
        if n_ab < 50 or lower <= threshold:
            continue
        ranked.append((n_abz / n_ab, row))
    ranked.sort(key=lambda r: -r[0])

    out = []
    placeholder = ", ".join("?" * len(implicated))
    for rate, row in ranked[:top_n]:
        a, b = row["drug_a"], row["drug_b"]
        third = con.execute(f"""
            WITH pair AS (
              SELECT cd1.case_id FROM case_drugs cd1 JOIN case_drugs cd2 USING (case_id)
              WHERE cd1.ingredient = ? AND cd2.ingredient = ?
            ), ev AS (
              SELECT p.case_id FROM pair p WHERE EXISTS (
                SELECT 1 FROM case_events e WHERE e.case_id = p.case_id AND e.{flag})
            )
            SELECT count(*), count(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM case_drugs c3 WHERE c3.case_id = ev.case_id
                  AND c3.ingredient IN ({placeholder})
                  AND c3.ingredient NOT IN (?, ?)))
            FROM ev
        """, [a, b] + implicated + [a, b]).fetchone()
        events, with_third = third[0] or 0, third[1] or 0
        key = tuple(sorted((a, b)))
        out.append({
            "pair": f"{a}+{b}",
            "n_ab": int(float(row["n_ab"])),
            "n_abz": int(float(row["n_abz"])),
            "event_rate": round(100 * rate, 1),
            "omega_add_lower": round(float(row["omega_add_lower"]), 3),
            "omega_lower": round(float(row["omega_lower"]), 3),
            "signals_multiplicative_too": float(row["omega_lower"]) > 0,
            "band": row.get("support"),
            "label_documented": key in reference,
            "event_cases_with_a_third_implicated_drug": (
                round(100 * with_third / events, 1) if events else None),
        })
    return {
        "note": "signalled pairs with at least 50 co-reports, ranked by event "
                "rate; the third-drug share is the proxy test of 4.7, where a "
                "known proxy scores near 100%",
        "threshold": threshold,
        "pairs": out,
    }


def nesting_condition(negative_rows: list[dict]) -> dict:
    """The condition under which the multiplicative signal set nests inside the
    additive one, and how often the literature's unconditional form fails.

    Round 29. Jung & Jung (2024) state that satisfying the multiplicative
    assumption implies satisfying the additive one. Under their simulation
    scenarios, which assume positive single-drug effects, that is right: with
    a = RR_A and b = RR_B, the multiplicative expectation is proportional to ab
    and the additive one to a + b - 1, and ab - (a + b - 1) = (a-1)(b-1) >= 0
    exactly when both drugs sit on the same side of unity.

    It is not right in general, and a real screen is full of the exceptions.
    Reported here as the condition (both marginals elevated) together with the
    count of pairs that violate the unconditional form.
    """
    both_up = viol_up = viol_all = total = 0
    for row in negative_rows:
        try:
            rr_a, rr_b = float(row["rr_a"]), float(row["rr_b"])
            mult, add = float(row["omega_lower"]), float(row["omega_add_lower"])
        except (TypeError, ValueError, KeyError):
            continue
        total += 1
        violates = mult > 0 and not add > 0
        viol_all += violates
        if rr_a > 1 and rr_b > 1:
            both_up += 1
            viol_up += violates
    return {
        "note": "the multiplicative signal set nests inside the additive one "
                "when both marginals are elevated; the unconditional form "
                "stated in the literature fails otherwise",
        "n_pairs": total,
        "n_both_elevated": both_up,
        "violations_all": viol_all,
        "violations_both_elevated": viol_up,
        "nesting_exact_when_both_elevated": viol_up == 0,
    }


def null_nesting(screen_rows: list[dict]) -> dict:
    """When do the two nulls stop being different tests?

    Both statistics are log2((n + alpha) / (E + alpha)) under identical
    shrinkage, so they differ only through E. The posterior quantile is
    decreasing in E, which gives an exact implication:

        E_mult >= E_add   =>   Omega_025 <= Omega_add,025
                          =>   {Omega_025 > 0} is contained in {Omega_add,025 > 0}

    Whether that antecedent holds is an empirical question, and it turns out to
    depend on exactly the quantity this paper is about. When both drugs are
    strongly associated with the event, the multiplicative expectation runs far
    above the additive one and the signal sets nest: the two nulls cannot then
    disagree about which pairs signal, only about where the threshold sits. When
    the marginals are weak the ordering reverses and they are genuinely
    different tests.

    This is checkable before any outcome data is used -- both expectations are
    functions of the marginals alone -- so a screen can determine in advance
    whether its choice of null is a choice of null or merely of operating point.
    """
    pairs = []
    for row in screen_rows:
        try:
            e_mult = float(row["expected"])
            e_add = float(row["additive_expected"])
            add = float(row["omega_add_lower"])
            mult = float(row["omega_lower"])
            n_ab = float(row["n_ab"])
        except (TypeError, ValueError, KeyError):
            continue
        if not n_ab:
            continue
        pairs.append((e_mult, e_add, mult, add, e_mult / n_ab))

    dominant = [p for p in pairs if p[4] > 0.05]
    weak = [p for p in pairs if p[4] <= 0.005]
    nested = [p for p in pairs if p[0] >= p[1]]
    violations = [p for p in pairs if p[2] > 0 and not p[3] > 0]
    return {
        "note": "both nulls are log2((n+a)/(E+a)) under identical shrinkage, so "
                "E_mult >= E_add implies the multiplicative signal set is "
                "contained in the additive one; the antecedent holds almost "
                "always in the drug-dominant regime and rarely outside it",
        "n_pairs": len(pairs),
        "n_expectation_ordered": len(nested),
        "share_expectation_ordered": round(len(nested) / len(pairs), 4) if pairs else None,
        "share_ordered_high_expected_rate": round(
            sum(1 for p in dominant if p[0] >= p[1]) / len(dominant), 4) if dominant else None,
        "n_high_expected_rate": len(dominant),
        "share_ordered_low_expected_rate": round(
            sum(1 for p in weak if p[0] >= p[1]) / len(weak), 4) if weak else None,
        "n_low_expected_rate": len(weak),
        "multiplicative_signals_not_additive": len(violations),
        "violations_with_expectation_reversed": sum(
            1 for p in violations if p[0] < p[1]),
        "nesting_holds_where_expectations_ordered": sum(
            1 for p in nested if p[2] > 0 and not p[3] > 0) == 0,
    }


def event_definition(pt_rows: list[dict]) -> dict:
    """The tier split of the curated PT list, and what each tier admits.

    Added in round 24. The paper described the event as "23 PTs in 10 concepts"
    -- the whole curation -- while every primary result uses the `core` tier,
    which is 10 PTs in 3 concepts. The counts differ eight-fold in event cases,
    so a reader applying the stated definition reproduces nothing. Emitting the
    split makes the prose checkable against the config rather than against
    someone's memory of it.
    """
    core = [r for r in pt_rows if r["tier"] == "core"]
    broad = [r for r in pt_rows if r["tier"] != "core"]
    counts = {"core": 0, "broad": 0}
    path = cfg.path("tables") / "event_case_counts.csv"
    if path.exists():
        with path.open() as fh:
            for row in csv.DictReader(fh):
                if row.get("scope") == "era":
                    counts["core"] += int(row["core_cases"])
                    counts["broad"] += int(row["broad_cases"])
    # Round 25: the report count of the largest broad-only term is quoted in
    # the prose to explain why the broad arm behaves as it does. It lived only
    # in event_pt_verification.csv, so quoting it breached the rule that nothing
    # is quoted which is not in the canonical file.
    verification = cfg.path("tables") / "event_pt_verification.csv"
    broad_reports: dict = {}
    if verification.exists():
        with verification.open() as fh:
            for row in csv.DictReader(fh):
                if row.get("tier", "").strip().lower() != "core" and row.get("reports"):
                    broad_reports[row["pt"]] = int(row["reports"])
    largest = max(broad_reports.items(), key=lambda kv: kv[1], default=("", 0))

    return {
        "note": "core is the primary analysis; broad is sensitivity only and is "
                "inclusive of core",
        "broad_only_largest_pt": largest[0],
        "broad_only_largest_pt_reports": largest[1],
        "curated_pts": len(pt_rows),
        "curated_concepts": len({r["concept"] for r in pt_rows}),
        "core_pts": len(core),
        "core_concepts": len({r["concept"] for r in core}),
        "broad_only_pts": len(broad),
        "broad_only_concepts": len({r["concept"] for r in broad}),
        "core_event_cases": counts["core"],
        "broad_event_cases": counts["broad"],
    }


POLYPHARMACY_BANDS = ((1, 1, "1"), (2, 5, "2-5"), (6, 10, "6-10"), (11, 20, "11-20"),
                      (21, 30, "21-30"), (31, 50, "31-50"), (51, None, "51+"))


def polypharmacy_bands(con: duckdb.DuckDBPyConnection, tier: str) -> dict:
    """Pair contribution and event rate by drugs-per-case band.

    Added in round 20+2. Figure 5 carried these fourteen numbers as literals in
    figures.py -- the same defect as the stale Table 1, in the one medium the
    table provenance guard did not look at. The values turned out to be exactly
    right, but nothing shipped could show that, while the paper claimed every
    figure was generated from the canonical file.

    A case listing k drugs contributes k(k-1)/2 pairs, so pair count grows
    quadratically while case count does not: that is the leverage the section
    is about. The event rate is reported per band because the aggregate hides a
    reversal -- the 51+ band contributes the largest share of pairs of any band
    while sitting far BELOW the database background rate.
    """
    flag = "is_core" if tier == "core" else "is_broad"
    cases = []
    for lo, hi, label in POLYPHARMACY_BANDS:
        upper = "" if hi is None else f" AND n.n_drugs <= {hi}"
        row = con.execute(f"""
            SELECT count(*),
                   sum(n.n_drugs * (n.n_drugs - 1) / 2.0),
                   sum(CASE WHEN e.case_id IS NOT NULL THEN 1 ELSE 0 END)
            FROM case_ndrugs n
            LEFT JOIN (SELECT DISTINCT case_id FROM case_events WHERE {flag}) e
                   USING (case_id)
            WHERE n.n_drugs >= {lo}{upper}
        """).fetchone()
        cases.append({"band": label, "cases": int(row[0]),
                      "pairs": float(row[1] or 0.0), "events": int(row[2] or 0)})

    total_pairs = sum(b["pairs"] for b in cases)
    total_cases = sum(b["cases"] for b in cases)
    total_events = sum(b["events"] for b in cases)
    background = total_events / total_cases if total_cases else 0.0
    for b in cases:
        b["share_of_pairs"] = round(100 * b["pairs"] / total_pairs, 1) if total_pairs else 0.0
        b["event_rate"] = round(100 * b["events"] / b["cases"], 2) if b["cases"] else 0.0
        b.pop("pairs")
    above = [b for b in cases if b["band"] in ("21-30", "31-50", "51+")]
    above_cases = sum(b["cases"] for b in above)
    above_events = sum(b["events"] for b in above)
    return {
        "note": "a case with k drugs contributes k(k-1)/2 pairs; the aggregate "
                "enrichment above the cap hides a reversal in the largest band",
        "bands": cases,
        "background_event_rate": round(100 * background, 3),
        "above_cap_cases": above_cases,
        "above_cap_share_of_pairs": round(sum(b["share_of_pairs"] for b in above), 1),
        "above_cap_event_rate": round(100 * above_events / above_cases, 3) if above_cases else 0.0,
        "above_cap_enrichment": round((above_events / above_cases) / background, 1)
        if above_cases and background else 0.0,
    }


NO_CAP = 10_000  # build_case_drugs treats None as "use the configured cap"


def cap_sweep(con: duckdb.DuckDBPyConnection, tier: str, policy: str,
              caps=(10, 15, 20, 30, 40, NO_CAP)) -> list[dict]:
    """Recovery and false-positive rate as the drugs-per-case cap varies.

    20 was adopted because it improved BOTH sensitivity and the false-positive
    rate. That is a choice made on the evaluation set and was not previously
    reported as such.

    NO_CAP is a large finite number, not None: build_case_drugs reads None as
    "fall back to the configured cap", so a None arm silently re-ran the 20-drug
    arm and reported it as the uncapped result.
    """
    out = []
    for cap in caps:
        contingency.build_case_drugs(con, policy, max_drugs=cap)
        contingency.drug_marginals(con, tier)
        n_total, n_event = contingency.totals(con, tier)
        outcome = tier_a.evaluate(con, tier, policy, rebuild=False)
        results = outcome["results"]
        powered = [r for r in results if r["n_ab"] >= 50]
        negatives = tier_b.generate(con, tier, None, seed=SEED)
        add = np.array([r["omega_add_lower"] for r in negatives], float)
        out.append({
            "cap": None if cap == NO_CAP else cap,
            "n_cases": n_total,
            "n_event_cases": n_event,
            "recovered_additive": sum(r["signal"] for r in results),
            "recovered_multiplicative": sum(r["signal_multiplicative"] for r in results),
            "n_controls": len(results),
            "n_powered": len(powered),
            "recovered_powered": sum(r["signal"] for r in powered),
            "n_negative_controls": len(negatives),
            "fpr_at_zero": round(float((add > 0).mean()), 4),
        })
        log.info("  cap=%-4s recovery %d/%d (powered %d/%d)  FPR@0 %.1f%%  negatives %d",
                 cap, out[-1]["recovered_additive"], len(results),
                 out[-1]["recovered_powered"], len(powered),
                 100 * out[-1]["fpr_at_zero"], len(negatives))
    return out


# --------------------------------------------------------------------------
# R6  Band enrichment is unadjusted for the one covariate section 4.1 proves
#     drives the statistic.
# --------------------------------------------------------------------------

def band_enrichment_by_marginal_strength(con, tier, rows, threshold) -> dict:
    """Signal rate by band, stratified on log2(RR_a * RR_b).

    Section 4.1 establishes that the expected count rises steeply with the two
    drugs' marginal associations (r = +0.94) and that this pushes the statistic
    down. The band comparison stratifies on co-report COUNT and never on
    marginal STRENGTH, yet the bands differ systematically on it -- median
    log2(RR_a x RR_b) runs 2.89 (unsupported) to 8.18 (positive control). The
    `plausible` band's headline 0.77x is a contrast across a 1.3-unit gap in an
    unadjusted covariate.

    This applies the same Mantel-Haenszel machinery already written for
    co-report count, with the drug-level cluster bootstrap for the interval.
    """
    n_total, n_event = contingency.totals(con, tier)
    baseline = n_event / n_total
    marginals = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT ingredient, n_drug, n_drug_event FROM drug_marginals").fetchall()}

    def rr(name):
        n_drug, n_drug_event = marginals.get(name, (0, 0))
        return (n_drug_event / n_drug) / baseline if n_drug and n_drug_event else None

    usable = []
    for row in rows:
        rr_a, rr_b = rr(row["drug_a"]), rr(row["drug_b"])
        if rr_a and rr_b:
            usable.append({**row, "strength": float(np.log2(rr_a * rr_b))})

    strength = np.array([r["strength"] for r in usable])
    signal = [r["omega_add_lower"] > threshold for r in usable]
    out = {
        "n_pairs": len(usable),
        "note": "strata are deciles of log2(RR_a * RR_b); the reference band is "
                "`unsupported`, matching the pooled band table",
        "median_strength_by_band": {},
        "quintile_signal_rate": [],
    }
    for band in ("unsupported", "plausible", "known_pair", "positive_control"):
        mask = np.array([r["support"] == band for r in usable])
        if mask.sum():
            out["median_strength_by_band"][band] = round(
                float(np.median(strength[mask])), 2)

    # Is marginal strength actually associated with signalling? Reported so the
    # size of the confound is visible rather than assumed.
    edges = np.quantile(strength, [0, .2, .4, .6, .8, 1.0])
    sig = np.array(signal)
    for i in range(5):
        mask = (strength >= edges[i]) & (strength <= edges[i + 1])
        out["quintile_signal_rate"].append({
            "quintile": i + 1,
            "strength_range": [round(float(edges[i]), 2), round(float(edges[i + 1]), 2)],
            "signal_rate": round(float(sig[mask].mean()), 4),
            "n": int(mask.sum()),
        })

    # Stratified enrichment of each band against `unsupported`.
    for band in ("plausible", "known_pair"):
        subset = [r for r in usable if r["support"] in (band, "unsupported")]
        in_band = [r["support"] == band for r in subset]
        sub_signal = [r["omega_add_lower"] > threshold for r in subset]
        strengths = [r["strength"] for r in subset]
        crude_num = np.mean([s for s, b in zip(sub_signal, in_band) if b])
        crude_den = np.mean([s for s, b in zip(sub_signal, in_band) if not b])
        entry = {"crude_enrichment": round(float(crude_num / crude_den), 3)
                 if crude_den else None}
        mh = st.mantel_haenszel_ratio(sub_signal, in_band, strengths)
        entry["stratified_on_marginal_strength"] = mh["ratio"]
        boot = st.mantel_haenszel_bootstrap(
            [(r["drug_a"], r["drug_b"]) for r in subset],
            sub_signal, in_band, strengths, n_boot=1000, seed=SEED)
        entry["stratified_ci_cluster_bootstrap"] = boot["ci"]
        entry["stratified_excludes_unity"] = boot.get("excludes_unity")
        out[band] = entry
    return out


# --------------------------------------------------------------------------
# R4  The inpatient adjustment used a 30-drug proxy touching 1.4% of cases,
#     while FAERS ships an actual hospitalisation outcome code.
# --------------------------------------------------------------------------

def inpatient_stratification(con, tier, drugs, threshold) -> dict:
    """Band enrichment split on the reported hospitalisation outcome code.

    Section 4.7 excluded cases containing any of 30 hand-picked
    procedural/critical-care drugs -- 275,205 cases, 1.4% of the analysis
    population -- and reported that band enrichment was unchanged. Removing
    1.4% of the data cannot establish that inpatient confounding is absent.

    FAERS records the outcome directly: `outc_cod = 'HO'` (hospitalisation,
    initial or prolonged) covers 5.7M reports and is already parsed. This
    stratifies on it instead.
    """
    outc = str(cfg.path("parquet") / "outc" / "*.parquet")
    con.execute(f"""
        CREATE OR REPLACE TABLE _hospitalised AS
        SELECT DISTINCT c.case_id
        FROM read_parquet('{outc}') o
        JOIN cases_deduped c ON c.era = o.era AND c.report_id = o.report_id
        WHERE upper(trim(o.outc_cod)) = 'HO'
    """)
    con.execute("CREATE OR REPLACE TABLE _keep_flags AS SELECT * FROM case_flags")
    con.execute("CREATE OR REPLACE TABLE _keep_drugs AS SELECT * FROM case_drugs")

    out = {"note": "stratified on FAERS outc_cod = 'HO', the reported "
                   "hospitalisation outcome, rather than a 30-drug proxy",
           "strata": []}
    for label, predicate in (("hospitalised", "IN"), ("not_hospitalised", "NOT IN")):
        con.execute(f"""CREATE OR REPLACE TABLE case_flags AS
                        SELECT * FROM _keep_flags
                        WHERE case_id {predicate} (SELECT case_id FROM _hospitalised)""")
        con.execute("""CREATE OR REPLACE TABLE case_drugs AS
                       SELECT d.* FROM _keep_drugs d SEMI JOIN case_flags f
                       USING (case_id)""")
        contingency.drug_marginals(con, tier)
        n_cases, n_event = contingency.totals(con, tier)
        contingency.pair_counts(con, drugs, tier,
                                min_pair=cfg.load_config()["analysis"]["min_co_reports"])
        scored = contingency.score(con, tier)
        positive_keys = {tuple(sorted((c["drug_a"].strip().upper(),
                                       c["drug_b"].strip().upper())))
                         for c in tier_a.load_positive_controls()}
        screen.annotate(scored, positive_keys)
        signal = [r["omega_add_lower"] > threshold for r in scored]
        rates = {}
        for band in ("unsupported", "plausible", "known_pair"):
            mask = [r["support"] == band for r in scored]
            k = sum(s for s, m in zip(signal, mask) if m)
            rates[band] = {"tested": sum(mask), "signalled": k,
                           "rate": round(k / sum(mask), 4) if sum(mask) else None}
        reference = rates["unsupported"]["rate"]
        for band in ("plausible", "known_pair"):
            rates[band]["enrichment"] = (
                round(rates[band]["rate"] / reference, 3)
                if reference and rates[band]["rate"] is not None else None)
        out["strata"].append({
            "stratum": label, "n_cases": n_cases, "n_event_cases": n_event,
            "event_rate": round(n_event / n_cases, 6) if n_cases else None,
            "n_pairs": len(scored), "bands": rates,
        })
        log.info("  %-17s %s cases, event rate %.3f%%, plausible enrichment %s",
                 label, f"{n_cases:,}", 100 * n_event / n_cases if n_cases else 0,
                 rates["plausible"].get("enrichment"))

    con.execute("CREATE OR REPLACE TABLE case_flags AS SELECT * FROM _keep_flags")
    con.execute("CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM _keep_drugs")
    contingency.drug_marginals(con, tier)
    return out


# --------------------------------------------------------------------------
# Vocabulary hygiene: entries in the screened set that cannot form a drug pair.
# --------------------------------------------------------------------------

# FDA's prod_ai field supplies these for entries it cannot resolve to an active
# moiety. They are counted in the 98.0% resolution coverage and then enter the
# screen as first-class drugs, but "UNSPECIFIED INGREDIENT + atorvastatin" is
# not a drug pair and cannot be an interaction.
NON_SPECIFIC_INGREDIENTS = {
    "UNSPECIFIED INGREDIENT", "HERBALS", "INSULIN NOS",
    "CANNABIS SATIVA SUBSP INDICA TOP",
}

# One active moiety reaching the vocabulary under several names. A pair drawn
# from within a group is the drug with itself.
SAME_MOIETY_GROUPS = [
    {"DIVALPROEX", "VALPROATE", "VALPROIC ACID"},
]


def _invalid_pair(drug_a: str, drug_b: str) -> bool:
    if drug_a in NON_SPECIFIC_INGREDIENTS or drug_b in NON_SPECIFIC_INGREDIENTS:
        return True
    return any({drug_a, drug_b} <= group for group in SAME_MOIETY_GROUPS)


def vocabulary_hygiene(rows: list[dict], threshold: float) -> dict:
    """Band enrichment with and without pairs that cannot be interactions.

    The screened drug set is the top 200 ingredients by co-reporting with the
    event, applied mechanically. That rule is pre-specified and is not changed
    here: excluding terms after seeing results would be a researcher degree of
    freedom. What is reported instead is the sensitivity, so a reader can see
    both the analysis as specified and the analysis over pairs that could in
    principle be interactions.
    """
    def bands(subset):
        out = {}
        for band in ("positive_control", "known_pair", "plausible", "unsupported"):
            rows_b = [r for r in subset if r["support"] == band]
            hits = sum(r["omega_add_lower"] > threshold for r in rows_b)
            out[band] = {"signalled": hits, "tested": len(rows_b),
                         "rate": round(hits / len(rows_b), 4) if rows_b else None}
        reference = out["unsupported"]["rate"]
        for band, entry in out.items():
            entry["enrichment"] = (round(entry["rate"] / reference, 3)
                                   if reference and entry["rate"] is not None else None)
        return out

    invalid = [r for r in rows if _invalid_pair(r["drug_a"], r["drug_b"])]
    valid = [r for r in rows if not _invalid_pair(r["drug_a"], r["drug_b"])]
    signalled_invalid = sum(r["omega_add_lower"] > threshold for r in invalid)
    return {
        "note": "the screened set is chosen mechanically by co-reporting; these "
                "terms are reported as a sensitivity, not removed from the "
                "primary analysis",
        "non_specific_ingredients": sorted(NON_SPECIFIC_INGREDIENTS),
        "same_moiety_groups": [sorted(g) for g in SAME_MOIETY_GROUPS],
        "invalid_pairs": len(invalid),
        "invalid_pairs_share": round(len(invalid) / len(rows), 4),
        "invalid_pairs_signalled": signalled_invalid,
        "invalid_pairs_in_plausible_band": sum(
            1 for r in invalid if r["support"] == "plausible"),
        "as_specified": bands(rows),
        "excluding_invalid_pairs": bands(valid),
    }


# --------------------------------------------------------------------------
# Provenance: figures the papers quote that no artifact previously backed.
# --------------------------------------------------------------------------

AEOLUS_WINDOW = ("2004q1", "2015q2")   # Banda et al. 2016 coverage
AEOLUS_CASES = 4_928_413               # their published retained-case count


def provenance(con, tier: str, policy: str, threshold: float) -> dict:
    """Compute and store the pipeline statistics the manuscripts quote.

    Eleven of eighteen substantive figures checked during review were absent
    from canonical_numbers.json, while all four documents claimed every quoted
    figure was generated into it and asserted by the test suite. Most were
    correct but computed in ad-hoc queries and never persisted -- including the
    AEOLUS deduplication benchmark, whose only occurrences in the repository
    were the prose and a test asserting that the prose contained it.

    Nothing here is new analysis. It is the provenance the claim already
    assumed.
    """
    demo = str(cfg.path("parquet") / "demo" / "*.parquet")
    out: dict = {"note": "pipeline figures quoted in the papers, persisted so the "
                         "availability claim is true rather than assumed"}

    out["raw_demo_rows"] = con.execute(
        f"SELECT count(*) FROM read_parquet('{demo}')").fetchone()[0]
    out["raw_demo_rows_by_era"] = {
        era: n for era, n in con.execute(
            f"SELECT era, count(*) FROM read_parquet('{demo}') GROUP BY 1 ORDER BY 1"
        ).fetchall()}
    out["laers_rows_without_case_id"] = con.execute(
        f"SELECT count(*) FROM read_parquet('{demo}') "
        "WHERE era = 'laers' AND case_id IS NULL").fetchone()[0]
    out["pt_vocabulary_size"] = con.execute(
        "SELECT count(*) FROM pt_vocab").fetchone()[0]
    # Read from the attrition table rather than recomputed: after the bridge has
    # run there is one row per case_id, so a self-join finds nothing and a naive
    # recomputation silently reports 0.
    attrition = cfg.path("tables") / "attrition.csv"
    if attrition.exists():
        with attrition.open() as fh:
            for row in csv.DictReader(fh):
                if "bridge" in row["stage"]:
                    out["cross_era_bridge_identifiers"] = int(row["removed"])
                    out["cross_era_bridge_source"] = "results/tables/attrition.csv"

    # AEOLUS benchmark, recomputed rather than remembered.
    start, end = AEOLUS_WINDOW
    ours = con.execute(
        "SELECT count(*) FROM cases_deduped WHERE quarter >= ? AND quarter <= ?",
        [start, end]).fetchone()[0]
    out["aeolus_benchmark"] = {
        "window": f"{start}-{end}",
        "aeolus_published_cases": AEOLUS_CASES,
        "this_pipeline_cases": ours,
        "difference_fraction": round((ours - AEOLUS_CASES) / AEOLUS_CASES, 4),
    }

    # Polypharmacy exclusion and the hospital-context proxy, as case counts.
    contingency.build_case_drugs(con, policy, max_drugs=NO_CAP)
    uncapped = con.execute("SELECT count(DISTINCT case_id) FROM case_drugs").fetchone()[0]
    contingency.build_case_drugs(con, policy)
    capped = con.execute("SELECT count(DISTINCT case_id) FROM case_drugs").fetchone()[0]
    contingency.build_case_drugs(con, policy, exclude_hospital_context=True)
    without_markers = con.execute(
        "SELECT count(DISTINCT case_id) FROM case_drugs").fetchone()[0]
    out["polypharmacy_excluded_cases"] = uncapped - capped
    out["hospital_context_excluded_cases"] = capped - without_markers
    out["hospital_context_excluded_share"] = round((capped - without_markers) / capped, 4)

    outc = str(cfg.path("parquet") / "outc" / "*.parquet")
    out["hospitalisation_outcome_reports"] = con.execute(
        f"SELECT count(*) FROM read_parquet('{outc}') "
        "WHERE upper(trim(outc_cod)) = 'HO'").fetchone()[0]

    # Background rate of an implicated drug among event cases -- the reference
    # the section 4.7 confounding argument is measured against.
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    implicated = ", ".join(f"'{d}'" for d in sorted(tier_b.MYOTOXICITY_IMPLICATED))
    flag = "is_core" if tier == "core" else "is_broad"
    out["implicated_drug_share_among_event_cases"] = round(float(con.execute(f"""
        SELECT avg(CASE WHEN n > 0 THEN 1.0 ELSE 0.0 END) FROM (
          SELECT d.case_id, sum(CASE WHEN d.ingredient IN ({implicated})
                                     THEN 1 ELSE 0 END) AS n
          FROM case_drugs d JOIN case_flags f USING (case_id)
          WHERE f.{flag} GROUP BY d.case_id)""").fetchone()[0]), 4)

    # The 86%-vs-12% mechanism: event rate among co-reports, both control sets.
    n_total, n_event = contingency.totals(con, tier)
    baseline = n_event / n_total
    authors = {tuple(sorted((c["drug_a"].strip().upper(),
                             c["drug_b"].strip().upper())))
               for c in tier_a.load_positive_controls()}
    reference = _endpoint_reference()
    drugs = screen.screen_drugs(con, 800)
    contingency.pair_counts(con, drugs, tier, min_pair=1)
    scored = contingency.score(con, tier)
    def rates(rows):
        return sorted(r["n_abz"] / r["n_ab"] for r in rows if r["n_ab"])
    author_rows = [r for r in scored if (r["drug_a"], r["drug_b"]) in authors]
    label_rows = [r for r in scored
                  if (r["drug_a"], r["drug_b"]) in reference
                  and (r["drug_a"], r["drug_b"]) not in authors and r["n_ab"] >= 50]
    def summarise(rows, label):
        vals = rates(rows)
        if not vals:
            return {"n": 0}
        median = float(np.median(vals))
        top = sorted(rows, key=lambda r: -r["n_ab"])[:max(1, len(rows) // 10)]
        top_median = float(np.median(rates(top))) if top else None
        return {"n": len(rows),
                "median_event_rate_among_coreports": round(median, 4),
                "vs_baseline": round(median / baseline, 1),
                "top_decile_by_coreporting_median": round(top_median, 4),
                "top_decile_vs_baseline": round(top_median / baseline, 2)}
    out["recovery_gap"] = {
        "baseline_event_rate": round(baseline, 6),
        "author_selected": summarise(author_rows, "author"),
        "label_selected": summarise(label_rows, "label"),
    }

    # The pair named in advance as the one that must work, taken from the Tier A
    # table so that one number has one source. Recomputing it here produced
    # 189.5 against the 189.2 the manuscripts quoted -- the quoted figure was
    # stale, and persisting provenance is what surfaced it.
    table = cfg.path("tables") / "tier_a_results.csv"
    if table.exists():
        with table.open() as fh:
            for row in csv.DictReader(fh):
                if (row["tier"] == tier and row["policy"] == policy
                        and {row["drug_a"], row["drug_b"]}
                        == {"SIMVASTATIN", "AMIODARONE"}):
                    out["simvastatin_amiodarone"] = {
                        "n_ab": int(row["n_ab"]), "n_abz": int(row["n_abz"]),
                        "expected_multiplicative": float(row["expected"]),
                        "omega": float(row["omega"]),
                        "omega_lower": float(row["omega_lower"]),
                        "source": "results/tables/tier_a_results.csv",
                    }
    return out


# --------------------------------------------------------------------------

def _endpoint_reference() -> set:
    path = cfg.path("tables") / "label_myotoxicity_reference.csv"
    if not path.exists():
        return set()
    with path.open() as fh:
        return {tuple(row) for row in list(csv.reader(fh))[1:]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    parser.add_argument("--skip-cap-sweep", action="store_true",
                        help="the cap sweep rebuilds case_drugs six times")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(cfg.path("logs") / "audit.log"),
                  logging.StreamHandler(sys.stdout)], force=True)

    conf = cfg.load_config()
    tier, policy = conf["event"]["primary_tier"], "primary"
    alpha = conf["analysis"]["omega"]["alpha"]
    canonical = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
    numbers = json.loads(canonical.read_text())
    threshold = numbers["tier_b"]["calibrated_threshold"]
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
    n_total, n_event = contingency.totals(con, tier)
    baseline = n_event / n_total
    marginals = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT ingredient, n_drug, n_drug_event FROM drug_marginals").fetchall()}

    # --- R1 -----------------------------------------------------------------
    log.info("--- induced correlation (is the Omega gradient an artifact?) ---")
    outcome = tier_a.evaluate(con, tier, policy, rebuild=False)
    rows = []
    for r in outcome["results"]:
        ma, mb = marginals.get(r["drug_a"]), marginals.get(r["drug_b"])
        if not (ma and mb and ma[0] and mb[0] and ma[1] and mb[1] and r["expected"]):
            continue
        rows.append({**r,
                     "rr_a": (ma[1] / ma[0]) / baseline,
                     "rr_b": (mb[1] / mb[0]) / baseline})
    results["induced_correlation"] = induced_correlation(rows, alpha)
    ic = results["induced_correlation"]
    log.info("  r(Omega_mult) = %+.3f   null %s", ic["r_omega_multiplicative"],
             ic["null_r_multiplicative"]["ci"])
    log.info("  r(Omega_add ) = %+.3f   null %s", ic["r_omega_additive"],
             ic["null_r_additive"]["ci"])
    log.info("  r(observed event rate) = %+.3f  r(expected, mult) = %+.3f",
             ic["r_observed_event_rate"], ic["r_expected_multiplicative"])

    # --- R2 -----------------------------------------------------------------
    log.info("--- held-out threshold calibration ---")
    negatives = tier_b.generate(con, tier, None, seed=SEED)
    add_values = np.array([r["omega_add_lower"] for r in negatives], float)
    results["heldout_calibration"] = heldout_calibration(add_values)
    hc = results["heldout_calibration"]
    log.info("  in-sample threshold %+.3f; held-out FPR %.2f%% (95%% CI %.2f-%.2f%%)",
             hc["in_sample_threshold"], 100 * hc["heldout_fpr_mean"],
             100 * hc["heldout_fpr_ci"][0], 100 * hc["heldout_fpr_ci"][1])

    # --- R6, FDR, R7/R8 -----------------------------------------------------
    screen_rows = []
    with (cfg.path("tables") / "screen_results.csv").open() as fh:
        for r in csv.DictReader(fh):
            screen_rows.append({
                "drug_a": r["drug_a"], "drug_b": r["drug_b"],
                "support": r["support"],
                "n_ab": int(r["n_ab"]), "n_abz": int(r["n_abz"]),
                "additive_expected": float(r["additive_expected"]),
                "omega_add_lower": float(r["omega_add_lower"]),
                "eras_with_signal": int(r["eras_with_signal"]),
            })
    control_drugs = {d for c in tier_a.load_positive_controls()
                     for d in (c["drug_a"].strip().upper(), c["drug_b"].strip().upper())}

    log.info("--- null nesting ---")
    results["null_nesting"] = null_nesting(screen_rows)
    nn = results["null_nesting"]
    log.info("  E_mult >= E_add in %.1f%% of pairs (%.1f%% when the expected "
             "joint rate exceeds 5%%, %.1f%% when it is under 0.5%%)",
             100 * nn["share_expectation_ordered"],
             100 * nn["share_ordered_high_expected_rate"],
             100 * nn["share_ordered_low_expected_rate"])
    log.info("  nesting holds wherever the expectations are ordered: %s",
             nn["nesting_holds_where_expectations_ordered"])

    log.info("--- event definition tiers ---")
    results["event_definition"] = event_definition(define_event.load_pt_list())
    ed = results["event_definition"]
    log.info("  core %d PTs / %d concepts -> %d cases; broad %d PTs -> %d cases",
             ed["core_pts"], ed["core_concepts"], ed["core_event_cases"],
             ed["curated_pts"], ed["broad_event_cases"])

    log.info("--- polypharmacy bands ---")
    results["polypharmacy_bands"] = polypharmacy_bands(con, tier)
    pb = results["polypharmacy_bands"]
    log.info("  above the cap: %d cases, %.1f%% of pairs, %.3f%% event rate (%.1fx)",
             pb["above_cap_cases"], pb["above_cap_share_of_pairs"],
             pb["above_cap_event_rate"], pb["above_cap_enrichment"])

    log.info("--- reference coverage ---")
    results["reference_coverage"] = reference_coverage(
        screen_rows, _endpoint_reference(), control_drugs, threshold)
    rc = results["reference_coverage"]
    log.info("  %d/%d ingredients have no FDA label (%.1f%%); endpoint-relevant: %s",
             rc["ingredients_without_any_label"], rc["ingredients_cached"],
             100 * rc["share_without_label"], rc["endpoint_relevant_without_label"])
    log.info("  %d/%d pairs (%.1f%%) can never be label-documented",
             rc["pairs_touching_an_unlabelled_drug"], rc["pairs_total"],
             100 * rc["share_of_pairs_structurally_undocumentable"])
    log.info("  restricted to label-covered pairs: enrichment %s, stratified %s %s",
             rc.get("enrichment"), rc.get("stratified"),
             rc.get("stratified_ci_cluster_bootstrap"))

    log.info("--- multiplicity ---")
    results["fdr"] = fdr_screen(screen_rows)
    log.info("  BH q=0.05: %d discoveries of %d tested (shrinkage threshold gives %d)",
             results["fdr"]["n_discoveries"], results["fdr"]["n_tested"],
             results["fdr"]["n_signalled_by_shrinkage_threshold"])

    log.info("--- vocabulary hygiene ---")
    results["vocabulary_hygiene"] = vocabulary_hygiene(screen_rows, threshold)
    vh = results["vocabulary_hygiene"]
    log.info("  %d pairs (%.1f%%) cannot be interactions; %d signal, %d in plausible",
             vh["invalid_pairs"], 100 * vh["invalid_pairs_share"],
             vh["invalid_pairs_signalled"], vh["invalid_pairs_in_plausible_band"])
    for band in ("known_pair", "plausible"):
        log.info("    %-12s as specified %s -> excluding invalid %s", band,
                 vh["as_specified"][band]["enrichment"],
                 vh["excluding_invalid_pairs"][band]["enrichment"])

    log.info("--- provenance for figures the papers quote ---")
    results["provenance"] = provenance(con, tier, policy, threshold)
    pv = results["provenance"]
    log.info("  AEOLUS window: ours %s vs published %s (%.1f%% apart)",
             f"{pv['aeolus_benchmark']['this_pipeline_cases']:,}",
             f"{pv['aeolus_benchmark']['aeolus_published_cases']:,}",
             100 * pv["aeolus_benchmark"]["difference_fraction"])
    log.info("  polypharmacy excluded %s; hospital-context %s; HO reports %s",
             f"{pv['polypharmacy_excluded_cases']:,}",
             f"{pv['hospital_context_excluded_cases']:,}",
             f"{pv['hospitalisation_outcome_reports']:,}")
    log.info("  recovery gap: author %s vs label %s of baseline",
             pv["recovery_gap"]["author_selected"].get("vs_baseline"),
             pv["recovery_gap"]["label_selected"].get("vs_baseline"))

    log.info("--- band enrichment stratified on marginal strength ---")
    results["band_by_marginal_strength"] = band_enrichment_by_marginal_strength(
        con, tier, screen_rows, threshold)
    bm = results["band_by_marginal_strength"]
    log.info("  median log2(RRa*RRb) by band: %s", bm["median_strength_by_band"])
    for band in ("plausible", "known_pair"):
        log.info("  %-16s crude %s -> stratified %s %s", band,
                 bm[band]["crude_enrichment"],
                 bm[band]["stratified_on_marginal_strength"],
                 bm[band]["stratified_ci_cluster_bootstrap"])

    log.info("--- inpatient stratification on the reported outcome code ---")
    contingency.build_case_drugs(con, policy)
    contingency.drug_marginals(con, tier)
    screened = screen.screen_drugs(con, 200)
    results["inpatient_stratification"] = inpatient_stratification(
        con, tier, screened, threshold)

    log.info("--- top of the ranking ---")
    results["top_ranked"] = top_ranked_pairs(screen_rows)
    for entry in results["top_ranked"]["top"][:5]:
        log.info("  %-46s %5.1f%%  n_ab=%-6d %s", entry["pair"],
                 100 * entry["event_rate"], entry["n_ab"], entry["band"])

    plausible = [(r["drug_a"], r["drug_b"]) for r in screen_rows
                 if r["eras_with_signal"] == 3 and r["support"] == "plausible"]
    results["era_stable_plausible"] = era_stable_plausible(con, tier, plausible)
    for entry in results["era_stable_plausible"]:
        log.info("  %-34s %s of %s event cases carry another implicated drug "
                 "(background %s)", entry["pair"],
                 entry["event_cases_with_another_implicated_drug"],
                 entry["event_cases"], entry["background_share"])

    # --- cap sweep ----------------------------------------------------------
    if not args.skip_cap_sweep:
        log.info("--- polypharmacy cap sweep (the cap was chosen on the controls) ---")
        results["cap_sweep"] = cap_sweep(con, tier, policy)

    numbers["audit"] = results
    numbers.setdefault("stages", []).append("audit")
    numbers["stages"] = sorted(set(numbers["stages"]))
    canonical.write_text(json.dumps(numbers, indent=2, sort_keys=True) + "\n")
    log.info("audit results merged into %s", canonical)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
