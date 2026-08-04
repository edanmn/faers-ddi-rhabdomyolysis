"""An interaction reference derived from FDA product labelling, via openFDA.

Why this exists
---------------
The evaluation had a circularity: pairs were annotated "known interaction" using
a 64-drug list written by the same authors who chose the 16 positive controls,
and every control drug was on that list. Pooled enrichment was 2.02x; restricted
to pairs containing no control drug it fell to 1.12x (95% CI 0.69-1.81), i.e.
the apparent validation was the circularity. DrugBank would resolve this but was
unavailable.

FDA product labelling is an alternative that is independent of the authors. For
each drug we retrieve the DRUG INTERACTIONS and CONTRAINDICATIONS sections of
its most recent label and record which other screened ingredients are named in
them. A pair is `label_documented` when either drug's label names the other.

What this is and is not
-----------------------
INDEPENDENT OF: the authors' curation, the positive control set, and any choice
made during this analysis. That is the specific circularity under repair.

NOT INDEPENDENT OF: FAERS itself. Labelling is informed by post-marketing
surveillance, and some interaction warnings originate in spontaneous reports.
This reference therefore cannot establish that a signal was discovered
independently of the data; it can only establish that the annotation was not
authored by us. That distinction is stated in the manuscript.

Known insensitivity: labels frequently warn by CLASS ("strong CYP3A4
inhibitors") rather than naming each agent, so a genuine documented interaction
can go unmatched. The resulting annotation is specific but under-sensitive,
which biases measured enrichment DOWNWARD -- the conservative direction for a
claim that enrichment exists.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time

import requests

from faers_ddi import config as cfg

log = logging.getLogger("label_reference")

ENDPOINT = "https://api.fda.gov/drug/label.json"
SECTIONS = ("drug_interactions", "contraindications", "warnings_and_cautions")

# A label documents that two drugs interact; it does not say the interaction
# causes THIS event. Of 1,400 pairs matched on drug name alone, 82% are
# documented for an unrelated endpoint -- omeprazole + warfarin is a real
# CYP2C19 interaction affecting INR and was being counted as a hit in a
# myotoxicity screen.
#
# An endpoint-specific reference additionally requires a myotoxicity term within
# PROXIMITY_CHARS of the partner drug's name.
MYOTOXICITY_TERMS = re.compile(
    r"RHABDOMYOL|MYOPATH|MYOSITIS|CREATINE (PHOSPHO)?KINASE|\bCPK\b|"
    r"MUSCLE|MYALG|MYOGLOBIN")
PROXIMITY_CHARS = 600
# openFDA permits 240 requests/minute without a key; stay well inside it.
REQUEST_PAUSE = 0.3
TIMEOUT = (15, 60)


def cache_dir():
    path = cfg.PROJECT_ROOT / "data" / "reference" / "openfda_labels"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch_label(ingredient: str, session: requests.Session) -> dict | None:
    """Most recent label for an ingredient, cached on disk.

    Cached so the reference is reproducible: openFDA content changes as labels
    are revised, and a rerun months later must not silently alter the
    evaluation.
    """
    safe = re.sub(r"[^A-Z0-9]+", "_", ingredient.upper()).strip("_")
    path = cache_dir() / f"{safe}.json"
    if path.exists():
        return json.loads(path.read_text())

    query = f'openfda.generic_name:"{ingredient.lower()}"'
    try:
        response = session.get(
            ENDPOINT, params={"search": query, "limit": 1}, timeout=TIMEOUT)
        if response.status_code == 404:
            payload = {"ingredient": ingredient, "found": False}
        else:
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                payload = {"ingredient": ingredient, "found": False}
            else:
                record = results[0]
                payload = {
                    "ingredient": ingredient, "found": True,
                    "text": " ".join(
                        " ".join(record.get(section, [])) for section in SECTIONS
                    ).upper(),
                }
    except Exception as exc:  # noqa: BLE001 - a miss must not abort the build
        log.warning("%s: %s", ingredient, exc)
        return None

    path.write_text(json.dumps(payload))
    time.sleep(REQUEST_PAUSE)
    return payload


def build(ingredients: list[str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Map each ingredient to the other ingredients its label names.

    Returns (any_interaction, myotoxicity_specific).
    """
    session = requests.Session()
    texts: dict[str, str] = {}
    for i, ingredient in enumerate(ingredients, start=1):
        payload = fetch_label(ingredient, session)
        if payload and payload.get("found"):
            texts[ingredient] = payload["text"]
        if i % 50 == 0:
            log.info("  fetched %d/%d labels", i, len(ingredients))
    log.info("labels retrieved for %d/%d ingredients", len(texts), len(ingredients))

    # Word-boundary matching. Substring matching would let "NIACIN" match inside
    # unrelated words and would count a drug as naming itself.
    patterns = {
        name: re.compile(rf"\b{re.escape(name)}\b")
        for name in ingredients if len(name) >= 5
    }
    mentions: dict[str, set[str]] = {}
    endpoint_specific: dict[str, set[str]] = {}
    for source, text in texts.items():
        found, relevant = set(), set()
        for other, pattern in patterns.items():
            if other == source:
                continue
            for match in pattern.finditer(text):
                found.add(other)
                window = text[max(0, match.start() - PROXIMITY_CHARS):
                              match.end() + PROXIMITY_CHARS]
                if MYOTOXICITY_TERMS.search(window):
                    relevant.add(other)
                    break
        mentions[source] = found
        endpoint_specific[source] = relevant
    return mentions, endpoint_specific


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=200)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)], force=True)

    import duckdb
    from faers_ddi import contingency, screen
    db_path = cfg.path("duckdb")
    con = duckdb.connect(str(db_path))
    for pragma in ("SET memory_limit='10GB'", "SET preserve_insertion_order=false",
                   "SET enable_progress_bar=false"):
        con.execute(pragma)
    contingency.build_case_drugs(con, "primary")
    contingency.drug_marginals(con, cfg.load_config()["event"]["primary_tier"])
    ingredients = screen.screen_drugs(con, args.top_n)
    con.close()

    mentions, endpoint_specific = build(ingredients)
    for name, mapping in [("label_interaction_reference.csv", mentions),
                          ("label_myotoxicity_reference.csv", endpoint_specific)]:
        out = cfg.path("tables") / name
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["drug_a", "drug_b"])
            seen = set()
            for source, targets in sorted(mapping.items()):
                for target in sorted(targets):
                    key = tuple(sorted((source, target)))
                    if key not in seen:
                        seen.add(key)
                        writer.writerow(key)
        log.info("%5d pairs -> %s", len(seen), out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
