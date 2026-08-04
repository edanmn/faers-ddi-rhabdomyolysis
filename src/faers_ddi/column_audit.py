"""Phase 1a -- audit the real column layout of every table in every quarter.

FDA documentation describes three schema eras. Across 90 quarters spanning 22
years that description is an expectation, not a fact: columns get added,
renamed, and reordered, and at least one table (STAT) exists only in the legacy
era. Parsing 90 quarters against a hardcoded layout fails silently -- columns
shift by one and every downstream count is wrong without anything raising.

So: read the header line of every member of every archive, and let the observed
headers drive the parser. Reads only the first line of each member, so the whole
audit runs in seconds without extracting anything.

Outputs, all in results/tables/:
  column_audit_long.csv      one row per (quarter, table): the observed columns
  column_presence_matrix.csv table x column x quarter presence grid
  schema_changepoints.csv    quarters where a table's column set changed
  audit_vs_config.csv        where the observed schema contradicts config.yaml
  archive_members.csv        every member of every archive, incl. non-table files
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from faers_ddi import config as cfg

log = logging.getLogger("column_audit")

# DEMO04Q1.TXT, drug14q3.txt, STAT11Q4.TXT -- table name, 2-digit year, quarter.
# The trailing [A-Z0-9_]* is not decoration: 2018Q1 ships its demographics as
# DEMO18Q1_new.txt. Anchoring on "Q<digit>.TXT" classified that as documentation
# and dropped an entire quarter of DEMO without raising anything -- the quarter
# simply parsed 6 tables instead of 7.
MEMBER_RE = re.compile(
    r"(?P<table>DEMO|DRUG|REAC|OUTC|RPSR|THER|INDI|STAT)"
    r"(?P<yy>\d{2})Q(?P<q>\d)(?P<suffix>[A-Z0-9_]*)\.TXT$",
    re.IGNORECASE,
)


def _decode(raw: bytes) -> str:
    """FAERS text is inconsistently encoded; latin-1 never raises."""
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def read_header(zf: zipfile.ZipFile, member: str, delimiter: str) -> list[str]:
    """Read only the first line of a zip member and split it into columns."""
    with zf.open(member) as fh:
        buf = b""
        while b"\n" not in buf:
            chunk = fh.read(1 << 16)
            if not chunk:
                break
            buf += chunk
            if len(buf) > (1 << 20):  # no newline in 1 MB: not a header
                break
    line = _decode(buf.split(b"\n", 1)[0]).strip("\r\n")
    return [c.strip().lower() for c in line.split(delimiter)]


def classify_member(name: str) -> tuple[str | None, str]:
    """Return (table_name, kind) for an archive member."""
    if name.endswith("/"):
        return None, "directory"
    base = Path(name).name
    if not base:
        return None, "directory"
    match = MEMBER_RE.search(base)
    if match:
        return match.group("table").lower(), "table"
    # Match on the whole path, and on the stem "delet" rather than "deleted".
    # FDA uses at least five conventions for these files across the archives:
    #   deleted/ADR19Q1DeletedCases.txt   DELETED/...   Deleted/...
    #   Deleted/20Q4DeletedCases.txt      (ADR prefix dropped, 2020q4)
    #   Deleted/DELETE22Q1.txt            (2021q4 onward -- no "deleted" at all)
    # A basename test for "deleted" silently reclassifies the last form as
    # documentation, which is what made 19 quarters look as though they shipped
    # no deletion list.
    lowered = name.lower()
    if "delet" in lowered:
        return None, "deleted_cases"
    if lowered.endswith((".doc", ".pdf", ".docx", ".txt")):
        return None, "documentation"
    return None, "other"


def audit_quarter(quarter: str, delimiter: str) -> tuple[list[dict], list[dict]]:
    """Returns (table_rows, member_rows) for one quarter."""
    zpath = cfg.zip_path(quarter)
    era = cfg.era_of(quarter)
    table_rows: list[dict] = []
    member_rows: list[dict] = []

    if not zpath.exists():
        log.warning("%s: archive missing, skipping", quarter)
        return table_rows, member_rows

    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            table, kind = classify_member(info.filename)
            member_rows.append({
                "quarter": quarter,
                "era": era,
                "member": info.filename,
                "kind": kind,
                "table": table or "",
                "uncompressed_bytes": info.file_size,
            })
            if kind != "table":
                continue
            columns = read_header(zf, info.filename, delimiter)
            table_rows.append({
                "quarter": quarter,
                "era": era,
                "table": table,
                "member": info.filename,
                "n_columns": len(columns),
                "columns": ";".join(columns),
                "uncompressed_bytes": info.file_size,
            })
    return table_rows, member_rows


def find_changepoints(table_rows: list[dict]) -> list[dict]:
    """Quarters where a table's column set differs from the previous quarter."""
    by_table: dict[str, list[dict]] = defaultdict(list)
    for row in table_rows:
        by_table[row["table"]].append(row)

    changepoints: list[dict] = []
    for table, rows in sorted(by_table.items()):
        rows.sort(key=lambda r: cfg.quarter_index(r["quarter"]))
        previous: set[str] | None = None
        prev_quarter = ""
        for row in rows:
            current = set(row["columns"].split(";")) if row["columns"] else set()
            if previous is None:
                changepoints.append({
                    "table": table, "quarter": row["quarter"], "era": row["era"],
                    "change": "first_observed", "added": ";".join(sorted(current)),
                    "removed": "", "n_columns": len(current),
                    "previous_quarter": "",
                })
            elif current != previous:
                changepoints.append({
                    "table": table, "quarter": row["quarter"], "era": row["era"],
                    "change": "columns_changed",
                    "added": ";".join(sorted(current - previous)),
                    "removed": ";".join(sorted(previous - current)),
                    "n_columns": len(current),
                    "previous_quarter": prev_quarter,
                })
            previous, prev_quarter = current, row["quarter"]
    return changepoints


def check_against_config(table_rows: list[dict]) -> list[dict]:
    """Flag every place the observed columns contradict config.yaml's eras."""
    eras = cfg.load_config()["eras"]
    observed = {(r["quarter"], r["table"]): set(r["columns"].split(";")) for r in table_rows}
    findings: list[dict] = []

    for quarter in cfg.all_quarters():
        era_name = cfg.era_of(quarter)
        era = eras[era_name]

        demo = observed.get((quarter, "demo"))
        if demo is not None:
            expected_sex = era["sex_col"]
            if expected_sex not in demo:
                alternatives = {"sex", "gndr_cod"} & demo
                findings.append({
                    "quarter": quarter, "era": era_name, "table": "demo",
                    "expectation": f"sex column '{expected_sex}'",
                    "observed": ";".join(sorted(alternatives)) or "neither sex nor gndr_cod",
                    "severity": "error",
                })
            for key in ("report_key", "case_key"):
                if era[key] not in demo:
                    findings.append({
                        "quarter": quarter, "era": era_name, "table": "demo",
                        "expectation": f"{key} '{era[key]}'",
                        "observed": "absent",
                        "severity": "error",
                    })

        drug = observed.get((quarter, "drug"))
        if drug is not None:
            has_ai = "prod_ai" in drug
            if has_ai != era["has_prod_ai"]:
                findings.append({
                    "quarter": quarter, "era": era_name, "table": "drug",
                    "expectation": f"has_prod_ai={era['has_prod_ai']}",
                    "observed": f"has_prod_ai={has_ai}",
                    "severity": "error",
                })
    return findings


def _write(rows: list[dict], name: str, fieldnames: list[str]) -> Path:
    out_dir = cfg.path("tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out


def write_presence_matrix(table_rows: list[dict]) -> Path:
    """Grid of which columns exist in which quarters, one block per table."""
    quarters = [q for q in cfg.all_quarters()
                if any(r["quarter"] == q for r in table_rows)]
    by_table: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for row in table_rows:
        by_table[row["table"]][row["quarter"]] = set(row["columns"].split(";"))

    out = cfg.path("tables") / "column_presence_matrix.csv"
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["table", "column", "n_quarters_present",
                         "first_quarter", "last_quarter", *quarters])
        for table in sorted(by_table):
            per_quarter = by_table[table]
            all_columns = sorted(set().union(*per_quarter.values()))
            for column in all_columns:
                flags = ["1" if column in per_quarter.get(q, set()) else ""
                         for q in quarters]
                present = [q for q, f in zip(quarters, flags) if f]
                writer.writerow([
                    table, column, len(present),
                    present[0] if present else "",
                    present[-1] if present else "",
                    *flags,
                ])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarters", nargs="*")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)], force=True,
    )
    delimiter = cfg.load_config()["data"]["delimiter"]
    quarters = args.quarters or cfg.all_quarters()

    table_rows: list[dict] = []
    member_rows: list[dict] = []
    for quarter in quarters:
        t, m = audit_quarter(quarter, delimiter)
        table_rows.extend(t)
        member_rows.extend(m)

    if not table_rows:
        log.error("no archives found -- has the download finished?")
        return 1

    _write(table_rows, "column_audit_long.csv",
           ["quarter", "era", "table", "member", "n_columns", "columns",
            "uncompressed_bytes"])
    _write(member_rows, "archive_members.csv",
           ["quarter", "era", "member", "kind", "table", "uncompressed_bytes"])
    changepoints = find_changepoints(table_rows)
    _write(changepoints, "schema_changepoints.csv",
           ["table", "quarter", "era", "change", "added", "removed",
            "n_columns", "previous_quarter"])
    findings = check_against_config(table_rows)
    _write(findings, "audit_vs_config.csv",
           ["quarter", "era", "table", "expectation", "observed", "severity"])
    write_presence_matrix(table_rows)

    tables = sorted({r["table"] for r in table_rows})
    log.info("audited %d quarters, tables observed: %s", len(quarters), ", ".join(tables))
    log.info("%d schema changepoints", len(changepoints))
    log.info("%d disagreements between observed schema and config.yaml", len(findings))
    kinds = defaultdict(int)
    for row in member_rows:
        kinds[row["kind"]] += 1
    log.info("archive members by kind: %s", dict(kinds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
