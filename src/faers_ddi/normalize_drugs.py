"""Phase 4 -- resolve verbatim drug entries to active ingredients.

853,439 distinct verbatim strings appear across 73,960,318 drug rows. `prod_ai`
(FDA's own active-ingredient field) resolves most of them, but exists only from
2014Q3 -- it covers 97.8% of faers_modern rows and 0% of everything earlier.

Resolution ladder, most to least reliable:

  1 prod_ai          FDA's active ingredient, split on the backslash separator
                     it uses for combination products (SACUBITRIL\\VALSARTAN)
  2 exact backfill   the same verbatim string, matched to the prod_ai it maps to
                     elsewhere in the dataset
  3 relaxed backfill as above after stripping dose, form and packaging detail
                     (TOPROL-XL, HUMIRA 40 MG/0.8 ML PEN)
  4 unresolved       kept, identified by its normalised verbatim string and
                     flagged, so it still participates in report counts and its
                     share is visible rather than silently dropped

Level 2 is the significant one and needs no external resource: the 59M modern
rows constitute an FDA-curated drugname->ingredient lookup, and the same
verbatim strings recur in the earlier eras. It backfills 90.1% of LAERS rows and
87.6% of faers_early rows, taking overall coverage to 96.4% before any relaxed
matching.

Salt and hydrate forms are stripped from the ingredient itself. Without this,
ATORVASTATIN and ATORVASTATIN CALCIUM are two different drugs and every
statin-interaction count is split across them. The stripping is deliberately
conservative: only recognised trailing salt/hydrate tokens are removed, and only
while a token remains.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys

import duckdb

from faers_ddi import config as cfg

log = logging.getLogger("normalize_drugs")

# Trailing tokens that denote a salt, ester or hydrate rather than a distinct
# active moiety. Stripped repeatedly, so "FUMARATE DIHYDRATE" reduces fully.
SALT_TOKENS = {
    "HYDROCHLORIDE", "HCL", "HYDROBROMIDE", "HYDROIODIDE", "SODIUM", "DISODIUM",
    "POTASSIUM", "DIPOTASSIUM", "CALCIUM", "MAGNESIUM", "SULFATE", "SULPHATE",
    "PHOSPHATE", "DIPHOSPHATE", "TARTRATE", "BITARTRATE", "MALEATE", "FUMARATE",
    "SUCCINATE", "CITRATE", "ACETATE", "MESYLATE", "MESILATE", "BESYLATE",
    "BESILATE", "TOSYLATE", "NITRATE", "BROMIDE", "IODIDE", "LACTATE",
    "GLUCONATE", "CARBONATE", "OXALATE", "PAMOATE", "EMBONATE", "XINAFOATE",
    "FUROATE", "VALERATE", "PROPIONATE", "DIPROPIONATE", "ENANTATE",
    "ENANTHATE", "DECANOATE", "PALMITATE", "STEARATE", "BENZOATE",
    "TROMETHAMINE", "MEGLUMINE", "OLAMINE", "DIOLAMINE", "MONOHYDRATE",
    "DIHYDRATE", "TRIHYDRATE", "HEMIHYDRATE", "HYDRATE", "ANHYDROUS",
    "MICRONIZED", "MICRONISED", "CHLORIDE", "BICARBONATE", "FLUORIDE",
}

# Compounds where the "salt" IS the conventional ingredient name, because the
# head token is an element rather than a drug. Stripping these turns calcium
# carbonate, magnesium sulfate and ferrous sulfate into bare CALCIUM, MAGNESIUM
# and FERROUS, collapsing unrelated products into a single high-volume node that
# would then surface in the screen as a meaningless "drug".
#
# The original token list stripped CARBONATE but not CHLORIDE, so CALCIUM
# CARBONATE collapsed while SODIUM CHLORIDE survived -- inconsistent in either
# direction. CHLORIDE is now stripped for genuine drugs and these compounds are
# protected by name.
#
# LITHIUM CARBONATE is deliberately NOT protected: lithium is the active moiety
# and lithium citrate is the same drug, so it should reduce to LITHIUM.
PROTECTED_COMPOUNDS = {
    "SODIUM CHLORIDE", "SODIUM BICARBONATE", "SODIUM CITRATE", "SODIUM PHOSPHATE",
    "SODIUM ACETATE", "SODIUM SULFATE", "SODIUM LACTATE", "SODIUM FLUORIDE",
    "POTASSIUM CHLORIDE", "POTASSIUM CITRATE", "POTASSIUM PHOSPHATE",
    "POTASSIUM ACETATE", "POTASSIUM BICARBONATE", "POTASSIUM IODIDE",
    "CALCIUM CARBONATE", "CALCIUM CHLORIDE", "CALCIUM ACETATE", "CALCIUM CITRATE",
    "CALCIUM GLUCONATE", "CALCIUM LACTATE", "CALCIUM PHOSPHATE",
    "MAGNESIUM SULFATE", "MAGNESIUM SULPHATE", "MAGNESIUM CHLORIDE",
    "MAGNESIUM CITRATE", "MAGNESIUM CARBONATE", "MAGNESIUM LACTATE",
    "FERROUS SULFATE", "FERROUS SULPHATE", "FERROUS GLUCONATE", "FERROUS FUMARATE",
    "ZINC SULFATE", "ZINC ACETATE", "ZINC GLUCONATE", "ZINC CHLORIDE",
    "AMMONIUM CHLORIDE", "AMMONIUM LACTATE", "BARIUM SULFATE",
}

# Dose, form and packaging noise to remove before a relaxed match.
DOSE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:MG|MCG|UG|G|GM|ML|L|IU|IE|U|%|MEQ|MMOL|KG)\b(?:\s*/\s*\S+)?",
    re.IGNORECASE,
)
FORM_TOKENS = {
    "TABLET", "TABLETS", "TAB", "TABS", "CAPSULE", "CAPSULES", "CAP", "CAPS",
    "CAPLET", "CAPLETS", "INJECTION", "INJECTABLE", "SOLUTION", "SUSPENSION",
    "SYRUP", "CREAM", "OINTMENT", "GEL", "PATCH", "SPRAY", "INHALER", "DISKUS",
    "PEN", "VIAL", "AMPOULE", "AMPULE", "SYRINGE", "KIT", "PACK", "POWDER",
    "GRANULES", "DROPS", "LOTION", "FOAM", "SHAMPOO", "SUPPOSITORY", "ELIXIR",
    "CONCENTRATE", "EMULSION", "AEROSOL", "IMPLANT", "PATCHES", "PREFILLED",
    "ORAL", "TOPICAL", "IV", "SC", "IM",
    # Release-modifier suffixes: the same moiety in a different formulation.
    "XL", "XR", "SR", "ER", "CR", "LA", "SRT", "MR", "ODT", "DS", "HFA",
}
# Bare unit tokens left behind when a compound dose like "40 MG/0.8 ML" is only
# partly consumed by DOSE_RE.
UNIT_TOKENS = {"MG", "MCG", "UG", "G", "GM", "ML", "L", "IU", "IE", "U",
               "MEQ", "MMOL", "KG", "MGML"}
PAREN_RE = re.compile(r"\([^)]*\)")
NONWORD_RE = re.compile(r"[^A-Z0-9 ]+")
SPACE_RE = re.compile(r"\s+")


def normalise_name(value: str) -> str:
    """Uppercase, collapse whitespace. The key used for an exact backfill."""
    return SPACE_RE.sub(" ", value.upper().strip())


def relax_name(value: str) -> str:
    """Strip dose, form and packaging detail for a relaxed backfill."""
    text = PAREN_RE.sub(" ", value.upper())
    text = DOSE_RE.sub(" ", text)
    text = NONWORD_RE.sub(" ", text)
    tokens = [t for t in text.split()
              if t and t not in FORM_TOKENS and t not in UNIT_TOKENS and not t.isdigit()]
    return " ".join(tokens).strip()


def strip_salts(ingredient: str) -> str:
    """Remove trailing salt/ester/hydrate tokens from an active ingredient."""
    tokens = normalise_name(NONWORD_RE.sub(" ", ingredient.upper())).split()
    while len(tokens) > 1 and tokens[-1] in SALT_TOKENS:
        if " ".join(tokens) in PROTECTED_COMPOUNDS:
            break
        tokens.pop()
    return " ".join(tokens)


def build(con: duckdb.DuckDBPyConnection) -> list[dict]:
    parquet = cfg.path("parquet") / "drug" / "*.parquet"
    con.execute(f"""
        CREATE OR REPLACE VIEW drug_rows AS
        SELECT d.era, d.report_id, d.drug_seq, upper(trim(d.role_cod)) AS role_cod,
               trim(d.drugname) AS drugname, trim(d.prod_ai) AS prod_ai
        FROM read_parquet('{parquet}', union_by_name=true) d
        SEMI JOIN cases_deduped c ON c.era = d.era AND c.report_id = d.report_id
    """)

    con.create_function("norm_name", normalise_name, ["VARCHAR"], "VARCHAR")
    con.create_function("relax_name", relax_name, ["VARCHAR"], "VARCHAR")
    con.create_function("strip_salts", strip_salts, ["VARCHAR"], "VARCHAR")

    # Lookups are built over the DISTINCT strings, not over 74M rows: there are
    # ~853k of the former.
    con.execute("""
        CREATE OR REPLACE TABLE name_keys AS
        SELECT drugname, norm_name(drugname) AS name_key,
               relax_name(drugname) AS relaxed_key
        FROM (SELECT DISTINCT drugname FROM drug_rows WHERE drugname <> '')
    """)

    # Where one verbatim string maps to several prod_ai values, take the most
    # frequent -- disagreement is rare and usually a data-entry variant.
    con.execute("""
        CREATE OR REPLACE TABLE exact_lookup AS
        SELECT name_key, arg_max(prod_ai, n) AS prod_ai FROM (
            SELECT k.name_key, d.prod_ai, count(*) AS n
            FROM drug_rows d JOIN name_keys k USING (drugname)
            WHERE d.prod_ai <> '' GROUP BY 1, 2
        ) GROUP BY 1
    """)
    con.execute("""
        CREATE OR REPLACE TABLE relaxed_lookup AS
        SELECT relaxed_key, arg_max(prod_ai, n) AS prod_ai FROM (
            SELECT k.relaxed_key, d.prod_ai, count(*) AS n
            FROM drug_rows d JOIN name_keys k USING (drugname)
            WHERE d.prod_ai <> '' AND k.relaxed_key <> '' GROUP BY 1, 2
        ) GROUP BY 1
    """)

    con.execute("""
        CREATE OR REPLACE TABLE drug_resolved AS
        SELECT
            d.era, d.report_id, d.drug_seq, d.role_cod, d.drugname,
            CASE WHEN d.prod_ai <> '' THEN 1
                 WHEN e.prod_ai IS NOT NULL THEN 2
                 WHEN r.prod_ai IS NOT NULL THEN 3
                 ELSE 4 END AS resolution_level,
            coalesce(nullif(d.prod_ai, ''), e.prod_ai, r.prod_ai,
                     nullif(k.relaxed_key, ''), k.name_key) AS ingredient_raw
        FROM drug_rows d
        LEFT JOIN name_keys k USING (drugname)
        LEFT JOIN exact_lookup e ON e.name_key = k.name_key
        LEFT JOIN relaxed_lookup r ON r.relaxed_key = k.relaxed_key
        WHERE d.drugname <> '' OR d.prod_ai <> ''
    """)

    # One row per (report, drug entry, ingredient): combination products carry
    # several ingredients and each must count toward its own drug.
    con.execute(r"""
        CREATE OR REPLACE TABLE drug_ingredients AS
        SELECT era, report_id, drug_seq, role_cod, resolution_level,
               strip_salts(part) AS ingredient
        FROM (
            SELECT era, report_id, drug_seq, role_cod, resolution_level,
                   unnest(string_split(ingredient_raw, '\')) AS part
            FROM drug_resolved
        )
        WHERE trim(part) <> '' AND strip_salts(part) <> ''
    """)

    rows: list[dict] = []
    for era, level, n in con.execute("""
        SELECT era, resolution_level, count(*) FROM drug_resolved
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall():
        rows.append({"era": era, "resolution_level": level, "drug_rows": n})

    totals = con.execute("""
        SELECT era,
               count(*) AS n,
               count(*) FILTER (WHERE resolution_level <= 3) AS resolved
        FROM drug_resolved GROUP BY 1 ORDER BY 1
    """).fetchall()
    for era, n, resolved in totals:
        log.info("%-13s %12s rows, %5.1f%% resolved to an ingredient",
                 era, f"{n:,}", 100 * resolved / n)
    overall_n, overall_resolved = con.execute("""
        SELECT count(*), count(*) FILTER (WHERE resolution_level <= 3) FROM drug_resolved
    """).fetchone()
    log.info("OVERALL       %12s rows, %5.1f%% resolved",
             f"{overall_n:,}", 100 * overall_resolved / overall_n)

    distinct_before, distinct_after = con.execute("""
        SELECT (SELECT count(DISTINCT ingredient_raw) FROM drug_resolved),
               (SELECT count(DISTINCT ingredient) FROM drug_ingredients)
    """).fetchone()
    log.info("distinct ingredient strings: %s raw -> %s after splitting and salt-stripping",
             f"{distinct_before:,}", f"{distinct_after:,}")
    return rows


def check_controls(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Acceptance test: every drug named in the control set must be findable.

    Aggregate coverage can look excellent while the specific drugs the study
    depends on are missing or split across spellings, so check them by name.
    """
    path = cfg.resolve(cfg.load_config()["controls"]["positive_file"])
    names: set[str] = set()
    with path.open() as fh:
        for row in csv.DictReader(fh):
            names.add(row["drug_a"].strip().upper())
            names.add(row["drug_b"].strip().upper())

    findings = []
    for name in sorted(names):
        reports, rows_matched = con.execute("""
            SELECT count(DISTINCT (era, report_id)), count(*)
            FROM drug_ingredients WHERE ingredient = ?
        """, [name]).fetchone()
        variants = con.execute("""
            SELECT count(DISTINCT ingredient) FROM drug_ingredients
            WHERE ingredient LIKE ? AND ingredient <> ?
        """, [name + " %", name]).fetchone()[0]
        findings.append({
            "drug": name, "reports": reports, "drug_rows": rows_matched,
            "unmerged_variants": variants,
            "status": "OK" if reports > 0 else "MISSING",
        })
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="10GB")
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "normalize_drugs.log"),
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

    coverage = build(con)
    out_dir = cfg.path("tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "drug_normalization_coverage.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["era", "resolution_level", "drug_rows"])
        writer.writeheader()
        writer.writerows(coverage)

    controls = check_controls(con)
    with (out_dir / "control_drug_coverage.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["drug", "reports", "drug_rows", "unmerged_variants", "status"])
        writer.writeheader()
        writer.writerows(controls)

    missing = [c["drug"] for c in controls if c["status"] == "MISSING"]
    log.info("control drugs: %d checked, %d missing", len(controls), len(missing))
    for control in controls:
        log.info("  %-22s reports=%-10s variants=%s",
                 control["drug"], f"{control['reports']:,}", control["unmerged_variants"])
    con.close()
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
