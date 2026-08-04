"""Phase 6 -- build (drug A, drug B, event) contingency tables and score them.

Wires the validated Omega implementation to real data. For a pair of drugs and
an event, the eight cells of the 2x2x2 table are recoverable from the triple
count plus six marginals and the total, so only those are computed.

Design choices that shape every downstream number
-------------------------------------------------
**Unit of analysis is the case**, not the drug row. A report listing simvastatin
twice contributes one simvastatin, not two.

**Denominator is the full deduplicated case set** (20,293,421), the standard
case/non-case background. Cases carrying no resolved drug still count toward the
total and toward the event marginal -- they are part of the reporting background
even though they cannot enter a drug marginal.

**Role policy.** The primary analysis counts primary suspect, secondary suspect
and interacting drugs (PS/SS/I) and excludes concomitant (C). Concomitant drugs
are the reporter's medication list rather than an implicated agent, and
including them changes both the numerator and the co-prescription marginal that
Omega's expected count is built from. The sensitivity analysis adds C.
"""

from __future__ import annotations

import logging

import duckdb
import numpy as np

from faers_ddi import config as cfg
from faers_ddi import omega as om

log = logging.getLogger("contingency")

ROLE_SETS = {
    "primary": ("PS", "SS", "I"),
    "sensitivity": ("PS", "SS", "I", "C"),
}

# Markers of inpatient or critical-care treatment. A report listing any of these
# almost certainly describes a hospitalised patient, and rhabdomyolysis is common
# in critical illness for reasons that have nothing to do with drug interaction.
#
# The Tier C screen's top 15 was dominated by exactly this: rocuronium, IV
# saline, norepinephrine and benzodiazepines paired with antipsychotics. Real
# associations -- antipsychotics cause rhabdomyolysis through neuroleptic
# malignant syndrome, and critically ill patients get muscle injury -- but not
# interactions. The top 100 was 2.9x enriched for these drugs.
#
# Excluding cases that contain any of them approximates an ambulatory
# population. It is a blunt instrument and it costs real scope: PROPOFOL is a
# genuine myotoxin (propofol infusion syndrome) and is dropped along with the
# context it marks, so this restriction cannot study propofol myotoxicity at
# all. That is the price of testing whether the DDI signals survive.
HOSPITAL_CONTEXT = {
    # neuromuscular blockers -- procedural use only
    "ROCURONIUM", "VECURONIUM", "SUCCINYLCHOLINE", "CISATRACURIUM",
    "ATRACURIUM", "PANCURONIUM", "MIVACURIUM",
    # general anaesthetics
    "PROPOFOL", "SEVOFLURANE", "DESFLURANE", "ISOFLURANE", "ENFLURANE",
    "ETOMIDATE", "THIOPENTAL", "NITROUS OXIDE",
    # vasopressors and inotropes
    "NOREPINEPHRINE", "EPINEPHRINE", "DOPAMINE", "DOBUTAMINE", "VASOPRESSIN",
    "PHENYLEPHRINE", "MILRINONE",
    # intravenous fluids and electrolyte replacement
    "SODIUM CHLORIDE", "DEXTROSE", "GLUCOSE", "POTASSIUM CHLORIDE",
    "SODIUM BICARBONATE", "CALCIUM GLUCONATE", "CALCIUM CHLORIDE",
    "MAGNESIUM SULFATE", "WATER", "SODIUM LACTATE", "ALBUMIN HUMAN",
}


def build_case_drugs(
    con: duckdb.DuckDBPyConnection, policy: str = "primary",
    max_drugs: int | None = None, exclude_hospital_context: bool | None = None,
) -> None:
    """One row per (case, ingredient) under the given role policy.

    Cases listing more than `max_drugs` distinct drugs are excluded entirely.
    They are a vanishing share of reports and a third of all pairs: a case with
    40 drugs contributes 780 of them, and high-polypharmacy cases carry a 4x
    enriched event rate. Leaving them in lets one report in a thousand drive the
    screen. See analysis.max_drugs_per_case in config.
    """
    roles = ", ".join(f"'{r}'" for r in ROLE_SETS[policy])
    if max_drugs is None:
        max_drugs = cfg.load_config()["analysis"].get("max_drugs_per_case")
    if exclude_hospital_context is None:
        exclude_hospital_context = cfg.load_config()["analysis"].get(
            "exclude_hospital_context", False)

    con.execute(f"""
        CREATE OR REPLACE TABLE raw_case_drugs AS
        SELECT DISTINCT c.case_id, d.ingredient
        FROM drug_ingredients d
        JOIN cases_deduped c ON c.era = d.era AND c.report_id = d.report_id
        WHERE d.role_cod IN ({roles})
    """)

    predicates = []
    if max_drugs:
        predicates.append(
            f"case_id IN (SELECT case_id FROM raw_case_drugs GROUP BY case_id "
            f"HAVING count(*) <= {max_drugs})")
    if exclude_hospital_context:
        markers = ", ".join(f"'{d}'" for d in sorted(HOSPITAL_CONTEXT))
        predicates.append(
            f"case_id NOT IN (SELECT case_id FROM raw_case_drugs "
            f"WHERE ingredient IN ({markers}))")
    where = ("WHERE " + " AND ".join(predicates)) if predicates else ""

    con.execute(f"CREATE OR REPLACE TABLE case_drugs AS SELECT * FROM raw_case_drugs {where}")

    # The denominator must follow the restrictions, but must NOT be defined as
    # "cases that have a drug row". Cases carrying no resolved drug are part of
    # the reporting background and belong in the total; excluding them shrinks
    # every marginal and inflates every signal.
    #
    # Defining case_flags by a semi-join to case_drugs conflates the two and
    # silently dropped 19,479 drugless cases. Excluded cases are therefore
    # enumerated explicitly and subtracted.
    excluded = " UNION ".join(
        f"SELECT case_id FROM raw_case_drugs GROUP BY case_id HAVING count(*) > {max_drugs}"
        for _ in [0] if max_drugs
    )
    if exclude_hospital_context:
        markers = ", ".join(f"'{d}'" for d in sorted(HOSPITAL_CONTEXT))
        clause = (f"SELECT DISTINCT case_id FROM raw_case_drugs "
                  f"WHERE ingredient IN ({markers})")
        excluded = f"{excluded} UNION {clause}" if excluded else clause
    anti = f"ANTI JOIN ({excluded}) x USING (case_id)" if excluded else ""

    con.execute(f"""
        CREATE OR REPLACE TABLE case_flags AS
        SELECT c.case_id,
               coalesce(e.is_core, false) AS is_core,
               coalesce(e.is_broad, false) AS is_broad
        FROM cases_deduped c
        LEFT JOIN case_events e USING (case_id)
        {anti}
    """)


def totals(con: duckdb.DuckDBPyConnection, tier: str) -> tuple[int, int]:
    """(n_total, n_event) -- the denominator and the event marginal."""
    return con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE is_{tier}) FROM case_flags
    """).fetchone()


def drug_marginals(con: duckdb.DuckDBPyConnection, tier: str) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE drug_marginals AS
        SELECT d.ingredient,
               count(*) AS n_drug,
               count(*) FILTER (WHERE f.is_{tier}) AS n_drug_event
        FROM case_drugs d JOIN case_flags f USING (case_id)
        GROUP BY 1
    """)


def pair_counts(
    con: duckdb.DuckDBPyConnection, drugs: list[str], tier: str, min_pair: int = 1
) -> duckdb.DuckDBPyRelation:
    """Co-occurrence counts for every unordered pair drawn from `drugs`."""
    con.execute("CREATE OR REPLACE TEMP TABLE _screen_drugs (ingredient VARCHAR)")
    con.executemany("INSERT INTO _screen_drugs VALUES (?)", [(d,) for d in drugs])
    con.execute(f"""
        CREATE OR REPLACE TABLE pair_counts AS
        WITH sub AS (
            SELECT d.case_id, d.ingredient
            FROM case_drugs d SEMI JOIN _screen_drugs s USING (ingredient)
        )
        SELECT a.ingredient AS drug_a, b.ingredient AS drug_b,
               count(*) AS n_ab,
               count(*) FILTER (WHERE f.is_{tier}) AS n_abz
        FROM sub a
        JOIN sub b ON a.case_id = b.case_id AND a.ingredient < b.ingredient
        JOIN case_flags f ON f.case_id = a.case_id
        GROUP BY 1, 2
        HAVING count(*) >= {min_pair}
    """)
    return con.table("pair_counts")


def score(
    con: duckdb.DuckDBPyConnection, tier: str, alpha: float | None = None,
    quantile: float | None = None,
) -> "list[dict]":
    """Attach Omega and its lower credibility bound to every counted pair."""
    conf = cfg.load_config()["analysis"]["omega"]
    alpha = conf["alpha"] if alpha is None else alpha
    quantile = conf["quantile"] if quantile is None else quantile

    n_total, n_event = totals(con, tier)
    frame = con.execute("""
        SELECT p.drug_a, p.drug_b, p.n_ab, p.n_abz,
               ma.n_drug AS n_a, ma.n_drug_event AS n_az,
               mb.n_drug AS n_b, mb.n_drug_event AS n_bz
        FROM pair_counts p
        JOIN drug_marginals ma ON ma.ingredient = p.drug_a
        JOIN drug_marginals mb ON mb.ingredient = p.drug_b
        -- Explicit ordering is required, not cosmetic. `preserve_insertion_order`
        -- is off for memory reasons, so without ORDER BY DuckDB returns rows in
        -- whatever order parallel execution produces. Tier B seeds its sampler
        -- from this sequence, so a varying order silently defeated the fixed
        -- seed and made the calibrated threshold -- and every figure downstream
        -- of it -- irreproducible across runs.
        ORDER BY p.drug_a, p.drug_b
    """).fetch_df()

    if frame.empty:
        return []

    tables = om.triples_to_tables(
        frame["n_abz"].to_numpy(), frame["n_ab"].to_numpy(),
        frame["n_az"].to_numpy(), frame["n_bz"].to_numpy(),
        frame["n_a"].to_numpy(), frame["n_b"].to_numpy(),
        np.full(len(frame), n_event), n_total,
    )
    # A negative reconstructed cell means the marginals are mutually
    # inconsistent, which should be impossible here and would silently poison
    # the fit. Surface it rather than letting IPF converge to nonsense.
    negative = int((tables < -1e-9).any(axis=(1, 2, 3)).sum())
    if negative:
        log.error("%d pairs produced a negative contingency cell", negative)

    expected = om.expected_count_vec(tables)
    frame["expected"] = expected
    frame["omega"] = om.omega_vec(frame["n_abz"].to_numpy(), expected, alpha)
    frame["omega_lower"] = om.omega_quantile_vec(
        frame["n_abz"].to_numpy(), expected, quantile, alpha)
    # The naive comparison the method exists to improve on, reported alongside
    # so the difference is visible on real data rather than only on synthetic.
    naive_expected = (
        frame["n_a"].to_numpy().astype(float) * frame["n_b"].to_numpy()
        * n_event / (float(n_total) * n_total)
    )
    frame["naive_expected"] = naive_expected
    frame["naive_log2_oe"] = om.omega_vec(frame["n_abz"].to_numpy(), naive_expected, alpha)

    # Additive null. Primary for this study -- see the omega module for why the
    # multiplicative null is untenable when the marginal associations are this
    # strong. Same shrinkage, so the two are directly comparable.
    additive = om.additive_expected_vec(
        frame["n_az"].to_numpy(), frame["n_bz"].to_numpy(),
        frame["n_a"].to_numpy(), frame["n_b"].to_numpy(),
        n_event, n_total, frame["n_ab"].to_numpy(),
    )
    frame["additive_expected"] = additive
    frame["omega_add"] = om.omega_vec(frame["n_abz"].to_numpy(), additive, alpha)
    frame["omega_add_lower"] = om.omega_quantile_vec(
        frame["n_abz"].to_numpy(), additive, quantile, alpha)
    frame["n_total"] = n_total
    frame["n_event"] = n_event
    return frame.to_dict("records")
