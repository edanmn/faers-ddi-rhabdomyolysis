"""Verify the positive control set against FDA labelling, and record the result.

Every row of `config/positive_controls.csv` carried `citation_status: to_verify`.
All sixteen. The field was created with an intent to check them and the check was
never run, so the paper's entire validation basis was self-declared unverified
while section 2 interrogated the *evaluation* reference at length.

This runs the check. For each control pair it asks the cached openFDA label text
-- the same cache the independent reference is built from -- three questions:

  named             does either drug's label name the other by name?
  endpoint_relevant is a myotoxicity term within PROXIMITY_CHARS of that mention?
  contraindicated   does the mention sit near contraindication or dose-limit
                    language, matching the `notes` column's claim?

A pair that passes the first two is documented by FDA labelling as an
interaction affecting this endpoint, which is exactly what `source: fda_label`
asserts. Pairs that fail are downgraded rather than dropped: removing a control
because it failed would be selection on the evaluation set all over again.

    python -m faers_ddi.verify_controls           # report only
    python -m faers_ddi.verify_controls --write   # update citation_status

The label cache is fixed on disk, so this is reproducible; it does not re-query
openFDA.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys

from faers_ddi import config as cfg
from faers_ddi import label_reference as lref

log = logging.getLogger("verify_controls")

# Language a label uses when the combination is barred or dose-capped, which is
# what the `notes` column claims for most of these pairs.
RESTRICTION = re.compile(
    r"CONTRAINDICAT|DO NOT (?:USE|EXCEED|ADMINISTER)|SHOULD NOT BE (?:USED|CO)|"
    r"AVOID|NOT RECOMMENDED|LIMIT|MAXIMUM DOSE|DOSE(?: | SHOULD )?(?:NOT )?EXCEED|"
    r"MG DAILY|REDUCE THE DOSE")


def _label_text(ingredient: str) -> str | None:
    safe = re.sub(r"[^A-Z0-9]+", "_", ingredient.upper()).strip("_")
    path = lref.cache_dir() / f"{safe}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return payload["text"] if payload.get("found") else None


def check_pair(drug_a: str, drug_b: str) -> dict:
    """Evidence for one control pair from the cached label text of both drugs."""
    evidence = {"named": False, "endpoint_relevant": False,
                "contraindicated_or_dose_limited": False,
                "labels_available": 0, "direction": []}
    for source, partner in ((drug_a, drug_b), (drug_b, drug_a)):
        text = _label_text(source)
        if text is None:
            continue
        evidence["labels_available"] += 1
        pattern = re.compile(rf"\b{re.escape(partner.upper())}\b")
        for match in pattern.finditer(text):
            evidence["named"] = True
            evidence["direction"].append(f"{source} label names {partner}")
            window = text[max(0, match.start() - lref.PROXIMITY_CHARS):
                          match.end() + lref.PROXIMITY_CHARS]
            if lref.MYOTOXICITY_TERMS.search(window):
                evidence["endpoint_relevant"] = True
            if RESTRICTION.search(window):
                evidence["contraindicated_or_dose_limited"] = True
            break
    evidence["direction"] = sorted(set(evidence["direction"]))
    return evidence


def status_for(evidence: dict) -> str:
    """The value `citation_status` should carry, given the evidence found."""
    if not evidence["labels_available"]:
        return "no_us_label"
    if evidence["endpoint_relevant"] and evidence["contraindicated_or_dose_limited"]:
        return "verified_label_restriction"
    if evidence["endpoint_relevant"]:
        return "verified_label_myotoxicity"
    if evidence["named"]:
        return "verified_label_interaction_other_endpoint"
    return "not_found_in_label"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="update citation_status in the control file")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)], force=True)

    path = cfg.resolve(cfg.load_config()["controls"]["positive_file"])
    with path.open() as fh:
        rows = list(csv.DictReader(fh))

    summary: dict[str, int] = {}
    verified = []
    for row in rows:
        if not row["drug_a"].strip():
            continue
        a, b = row["drug_a"].strip().upper(), row["drug_b"].strip().upper()
        evidence = check_pair(a, b)
        status = status_for(evidence)
        summary[status] = summary.get(status, 0) + 1
        row["citation_status"] = status
        verified.append({"pair": f"{a}+{b}", "status": status,
                         "source": row["source"],
                         "expected_strength": row["expected_strength"], **evidence})
        log.info("  %-34s %-42s labels=%d", f"{a}+{b}", status,
                 evidence["labels_available"])

    log.info("summary: %s", summary)

    canonical = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
    if canonical.exists():
        numbers = json.loads(canonical.read_text())
        numbers["positive_control_verification"] = {
            "note": "each control checked against the cached FDA label text; "
                    "citation_status in config/positive_controls.csv was "
                    "'to_verify' for all 16 and had never been checked",
            "summary": summary,
            "n_controls": len(verified),
            "n_endpoint_relevant": sum(v["endpoint_relevant"] for v in verified),
            "n_named": sum(v["named"] for v in verified),
            "n_no_us_label": summary.get("no_us_label", 0),
            "controls": verified,
        }
        canonical.write_text(json.dumps(numbers, indent=2, sort_keys=True) + "\n")
        log.info("verification -> %s", canonical)

    if args.write:
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        log.info("citation_status updated in %s", path)
    else:
        log.info("report only; pass --write to update %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
