"""Does the Omega failure generalise beyond rhabdomyolysis, and to what?

The paper's central claim is conditional: the multiplicative null fails *when the
drugs under study are the leading reported causes of the outcome*. One event
cannot establish a conditional claim -- it shows the phenomenon, not the
condition.

Two further events are analysed here, chosen to sit on opposite sides of the
proposed condition:

  torsade / QT prolongation   Drug-dominant, like rhabdomyolysis. The condition
                              predicts Omega fails here too.

  anaphylaxis                 Drugs cause it, but the marginal associations of
                              any individual drug are far weaker, because the
                              event is spread across hundreds of agents rather
                              than concentrated in one class. The condition
                              predicts Omega performs comparatively BETTER here.

If Omega fails on both, the finding is "Omega fails", which is weaker and less
useful. If it fails on the drug-dominant events and holds up where marginals are
weak, the conditional claim is supported and the condition is diagnostic --
computable in advance from the marginal relative risks alone.

Positive controls for each event are drug pairs with a documented interaction
producing that event. They are deliberately few and are used only to compare the
two nulls on the same data, never to claim a discovery.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import duckdb
import numpy as np

from faers_ddi import config as cfg
from faers_ddi import contingency, omega as om, statistics as st

log = logging.getLogger("generalization")

# PT strings verified present in REAC before use (see verify_terms below).
EVENTS = {
    "torsade_qt": {
        "label": "torsade de pointes / QT prolongation",
        "expected": "drug-dominant, like rhabdomyolysis",
        # Curated to the primary event's standard: repolarisation-specific
        # terms only. An earlier version also included CARDIAC ARREST,
        # VENTRICULAR TACHYCARDIA and VENTRICULAR FIBRILLATION, which are
        # non-specific terminal events with many non-QT causes; they tripled the
        # event rate relative to rhabdomyolysis and made the replication a
        # weaker test than the primary analysis it was replicating.
        # `pts_dropped_as_nonspecific` is analysed alongside as a sensitivity.
        "pts": [
            "TORSADE DE POINTES", "ELECTROCARDIOGRAM QT PROLONGED",
            "LONG QT SYNDROME", "ELECTROCARDIOGRAM QT INTERVAL ABNORMAL",
            "VENTRICULAR TACHYARRHYTHMIA",
        ],
        "pts_dropped_as_nonspecific": [
            "VENTRICULAR TACHYCARDIA", "VENTRICULAR FIBRILLATION",
            "CARDIAC ARREST",
        ],
        # QT-prolonging combinations with documented additive/pharmacokinetic
        # interaction. Amiodarone, sotalol, methadone, haloperidol, citalopram
        # and the macrolide/azole perpetrators are the standard agents.
        "controls": [
            ("AMIODARONE", "SOTALOL"), ("AMIODARONE", "CLARITHROMYCIN"),
            ("METHADONE", "CLARITHROMYCIN"), ("HALOPERIDOL", "CLARITHROMYCIN"),
            ("CITALOPRAM", "CLARITHROMYCIN"), ("METHADONE", "FLUCONAZOLE"),
            ("AMIODARONE", "FLUCONAZOLE"), ("ONDANSETRON", "AMIODARONE"),
            ("HALOPERIDOL", "AMIODARONE"), ("CITALOPRAM", "AMIODARONE"),
        ],
    },
    "anaphylaxis": {
        "label": "anaphylaxis",
        "expected": "drug-caused but marginals diffuse across many agents",
        "pts": [
            "ANAPHYLACTIC REACTION", "ANAPHYLACTIC SHOCK",
            "ANAPHYLACTOID REACTION", "ANAPHYLACTOID SHOCK",
            "TYPE I HYPERSENSITIVITY",
        ],
        # THIS ARM IS DESIGN-INVALID, not merely underpowered, and is retained
        # only so that the failure is on the record.
        #
        # Anaphylaxis is overwhelmingly single-agent: there is no established
        # drug pair whose INTERACTION causes it. What follows are common
        # co-exposures among agents that each cause anaphylaxis independently,
        # which is a different thing entirely -- there is no interaction present
        # for either null to detect, so no amount of additional data would make
        # the arm informative. Two entries in the first version were worse than
        # weak: AMOXICILLIN + CLAVULANATE POTASSIUM is a fixed-dose combination
        # product (co-amoxiclav), not a drug-drug interaction at all, and
        # CONTRAST MEDIA + IOHEXOL pairs a class with a member of that class.
        # Both are removed; the remainder are labelled for what they are.
        "design_valid": False,
        "design_note": ("co-exposures among independently anaphylactogenic "
                        "agents, not interaction pairs; cannot test the "
                        "conditional claim at any sample size"),
        "controls": [
            ("IBUPROFEN", "AMOXICILLIN"), ("VANCOMYCIN", "PIPERACILLIN"),
            ("ASPIRIN", "IBUPROFEN"), ("CEFTRIAXONE", "VANCOMYCIN"),
        ],
    },
}


def verify_terms(con: duckdb.DuckDBPyConnection, pts: list[str]) -> list[str]:
    """Keep only PTs that actually occur, as in Phase 5 for the primary event."""
    present = []
    for pt in pts:
        hit = con.execute(
            "SELECT reports FROM pt_vocab WHERE pt = ?", [pt]).fetchone()
        if hit and hit[0] > 0:
            present.append(pt)
        else:
            log.warning("  PT absent from REAC, dropped: %r", pt)
    return present


def build_event_flags(con: duckdb.DuckDBPyConnection, pts: list[str]) -> None:
    placeholders = ", ".join("?" for _ in pts)
    reac = str(cfg.path("parquet") / "reac" / "*.parquet")
    con.execute(f"""
        CREATE OR REPLACE TABLE alt_event_cases AS
        SELECT DISTINCT c.case_id
        FROM read_parquet('{reac}') r
        JOIN cases_deduped c ON c.era = r.era AND c.report_id = r.report_id
        WHERE upper(trim(r.pt)) IN ({placeholders})
    """, pts)
    con.execute("""
        CREATE OR REPLACE TABLE case_flags AS
        SELECT f.case_id,
               (e.case_id IS NOT NULL) AS is_core,
               (e.case_id IS NOT NULL) AS is_broad
        FROM (SELECT case_id FROM case_flags) f
        LEFT JOIN alt_event_cases e USING (case_id)
    """)


def evaluate_event(con: duckdb.DuckDBPyConnection, name: str, spec: dict) -> dict:
    log.info("--- %s (%s) ---", spec["label"], spec["expected"])
    contingency.build_case_drugs(con, "primary")
    pts = verify_terms(con, spec["pts"])
    if not pts:
        return {"event": name, "error": "no PTs present"}
    build_event_flags(con, pts)
    contingency.drug_marginals(con, "core")
    n_total, n_event = contingency.totals(con, "core")
    baseline = n_event / n_total

    drugs = sorted({d for pair in spec["controls"] for d in pair})
    contingency.pair_counts(con, drugs, "core", min_pair=1)
    scored = {(r["drug_a"], r["drug_b"]): r for r in contingency.score(con, "core")}

    marginals = {row[0]: (row[1], row[2]) for row in con.execute(
        "SELECT ingredient, n_drug, n_drug_event FROM drug_marginals").fetchall()}

    rows, xs, ys, ys_add, ys_obs = [], [], [], [], []
    for a, b in spec["controls"]:
        key = tuple(sorted((a, b)))
        row = scored.get(key)
        ma, mb = marginals.get(a), marginals.get(b)
        if not (row and ma and mb and ma[0] and mb[0] and ma[1] and mb[1]):
            continue
        rr_a = (ma[1] / ma[0]) / baseline
        rr_b = (mb[1] / mb[0]) / baseline
        rows.append({
            "pair": f"{a}+{b}", "n_ab": row["n_ab"], "n_abz": row["n_abz"],
            "rr_a": round(rr_a, 1), "rr_b": round(rr_b, 1),
            "omega": round(row["omega"], 3),
            "omega_lower": round(row["omega_lower"], 3),
            "omega_add": round(row["omega_add"], 3),
            "omega_add_lower": round(row["omega_add_lower"], 3),
            "signal_multiplicative": bool(row["omega_lower"] > 0),
            "signal_additive": bool(row["omega_add_lower"] > 0),
        })
        xs.append(np.log2(rr_a * rr_b))
        ys.append(row["omega"])
        ys_add.append(row["omega_add"])
        ys_obs.append(np.log2(max(row["n_abz"], 0.5) / row["n_ab"]))

    powered = [r for r in rows if r["n_ab"] >= 50]
    result = {
        "event": name, "label": spec["label"], "expected": spec["expected"],
        "design_valid": spec.get("design_valid", True),
        "design_note": spec.get("design_note"),
        "pts_used": pts, "n_cases": n_total, "n_event_cases": n_event,
        "event_rate": round(baseline, 6),
        "median_marginal_rr": round(float(np.median(
            [r["rr_a"] for r in rows] + [r["rr_b"] for r in rows])), 1) if rows else None,
        "n_controls": len(rows), "n_powered": len(powered),
        "recovered_multiplicative": sum(r["signal_multiplicative"] for r in rows),
        "recovered_additive": sum(r["signal_additive"] for r in rows),
        "recovered_multiplicative_powered": sum(
            r["signal_multiplicative"] for r in powered),
        "recovered_additive_powered": sum(r["signal_additive"] for r in powered),
        "pairs": rows,
    }
    if len(xs) >= 4:
        result["omega_vs_marginal_product"] = st.correlation_with_ci(xs, ys)
        # The same correlation for the additive null and for the raw observed
        # rate. Omega = log2(O/E) and E rises with the marginals by
        # construction, so reporting this for the multiplicative null alone
        # implies the gradient is diagnostic OF that null. It is not.
        result["omega_add_vs_marginal_product"] = st.correlation_with_ci(xs, ys_add)
        result["observed_rate_vs_marginal_product"] = st.correlation_with_ci(xs, ys_obs)
    log.info("  %d cases, event rate %.3f%%, median marginal RR %.1f",
             n_total, 100 * baseline, result["median_marginal_rr"] or 0)
    log.info("  controls %d (%d powered): multiplicative %d, additive %d",
             len(rows), len(powered), result["recovered_multiplicative"],
             result["recovered_additive"])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(cfg.path("logs") / "generalization.log"),
                  logging.StreamHandler(sys.stdout)], force=True)

    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in (f"SET memory_limit='{args.memory_limit}'",
                   "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false",
                   f"SET temp_directory='{db_path.parent / 'duckdb_tmp'}'"):
        con.execute(pragma)

    results = {name: evaluate_event(con, name, spec) for name, spec in EVENTS.items()}

    # Sensitivity: the broad PT list the first version used. Reported so the
    # narrowing is visible rather than a silent researcher degree of freedom.
    broad = dict(EVENTS["torsade_qt"])
    broad["pts"] = EVENTS["torsade_qt"]["pts"] + \
        EVENTS["torsade_qt"]["pts_dropped_as_nonspecific"]
    broad["label"] = "torsade/QT, broad PT list (non-specific terms retained)"
    results["torsade_qt_broad_pts"] = evaluate_event(con, "torsade_qt_broad_pts", broad)

    canonical = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
    numbers = json.loads(canonical.read_text())
    primary = numbers["tier_a"]
    results["rhabdomyolysis_primary"] = {
        "label": "rhabdomyolysis (primary event)",
        "recovered_multiplicative": primary["recovered_multiplicative"],
        "recovered_additive": primary["recovered_additive"],
        "n_controls": primary["n_controls"],
        "median_marginal_rr": primary.get("median_marginal_rr"),
        "omega_vs_marginal_product": primary["omega_vs_marginal_product"],
    }
    numbers["generalization"] = results
    numbers.setdefault("stages", []).append("generalization")
    numbers["stages"] = sorted(set(numbers["stages"]))
    canonical.write_text(json.dumps(numbers, indent=2, sort_keys=True) + "\n")

    log.info("=== summary ===")
    log.info("%-34s %10s %14s %12s", "event", "median RR", "multiplicative", "additive")
    for name, r in results.items():
        if "n_controls" not in r:
            continue
        log.info("%-34s %10s %10d/%-3d %8d/%-3d",
                 r["label"][:34], r.get("median_marginal_rr", "—"),
                 r["recovered_multiplicative"], r["n_controls"],
                 r["recovered_additive"], r["n_controls"])
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
