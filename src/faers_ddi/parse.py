"""Phase 2 -- parse every quarterly archive into Parquet.

Driven by the Phase 1a audit rather than by a hardcoded layout: each table's
column names are read from its own header line and then harmonised, so the
2012Q4 anomalies (a UTF-8 BOM on DRUG's first column, `outc_code`, `lot_nbr`)
and the LAERS/FAERS identity-column split are handled by data rather than by
branching on the quarter.

Three things are deliberately measured rather than assumed, and land in
results/tables/parse_manifest.csv:

  rows_skipped   lines whose field count did not match the header. FAERS free
                 text occasionally contains an embedded newline, which splits
                 one record into two unparseable lines. Counted by comparing
                 parsed rows against raw line count, so it cannot be silently
                 zero.
  id_nulls       report/case ids that failed to cast to integer. Should be
                 zero; anything else means an id column is not what we think.
  decode_errors  bytes that are not valid in the assumed encoding.

Everything is read as string and cast explicitly. Letting pandas infer types
across 90 quarters invites a column being float in one quarter and object in
another, which then silently breaks a concatenation much later.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from faers_ddi import config as cfg
from faers_ddi.column_audit import MEMBER_RE, classify_member

log = logging.getLogger("parse")

BOM = "﻿"
ID_COLUMNS = ("report_id", "case_id", "caseversion")
# Surplus fields to absorb beyond the declared header. Trailing delimiters
# account for one; the pad leaves room without masking a real mismatch.
EXTRA_FIELD_PAD = 5
# A shifted column fails to cast almost everywhere, so the tolerance only has
# to admit genuinely dirty individual values.
ID_NULL_TOLERANCE = 0.01


def harmonised_columns(raw_header: str, quarter: str, delimiter: str) -> list[str]:
    """Turn a raw header line into the canonical column names for this study."""
    conf = cfg.load_config()["harmonization"]
    era = cfg.era_of(quarter)
    identity = conf["identity"][era]
    renames = conf["rename"]

    columns = []
    for name in raw_header.split(delimiter):
        name = name.strip()
        if conf.get("strip_bom", True):
            name = name.lstrip(BOM)
        name = name.strip().lower()
        name = renames.get(name, name)
        columns.append(name)

    # Identity columns get era-neutral names so no later stage branches on era.
    # `era` itself is carried on every row, because legacy `case` and modern
    # `caseid` are distinct id spaces until Phase 3 verifies the bridge.
    reverse_identity = {source: target for target, source in identity.items()}
    columns = [reverse_identity.get(c, c) for c in columns]

    if len(columns) != len(set(columns)):
        duplicates = [c for c in set(columns) if columns.count(c) > 1]
        raise ValueError(f"{quarter}: duplicate columns after harmonisation: {duplicates}")
    return columns


def _decode(raw: bytes) -> tuple[str, int]:
    """Decode FAERS text, reporting how many bytes had to be replaced."""
    try:
        return raw.decode("utf-8"), 0
    except UnicodeDecodeError:
        pass
    text = raw.decode("cp1252", errors="replace")
    return text, text.count("�")


def parse_member(
    zf: zipfile.ZipFile, member: str, table: str, quarter: str, delimiter: str
) -> tuple[pd.DataFrame, dict]:
    raw = zf.read(member)
    text, decode_errors = _decode(raw)
    del raw

    header, _, body = text.partition("\n")
    columns = harmonised_columns(header.rstrip("\r"), quarter, delimiter)

    # Raw record count, for the skipped-row comparison below. Trailing blank
    # lines are not records.
    raw_lines = sum(1 for line in body.split("\n") if line.strip())

    # Several tables end every data line with a trailing delimiter while their
    # header does not -- LAERS REAC is "ISR$PT" over rows like
    # "4204616$ABDOMINAL PAIN$", i.e. three fields against two names. Given
    # fewer names than fields, pandas silently promotes the surplus leading
    # columns to the index, shifting every column left by one: report_id ends up
    # holding the PT text and the real id disappears. No bad-line is reported
    # and no error is raised.
    #
    # So: always pass index_col=False, and pad the name list with placeholders
    # to absorb any surplus fields. The placeholders are then checked for
    # content before being dropped, so a table that genuinely carries more data
    # than its header declares is reported rather than discarded.
    placeholders = [f"__extra_{i}" for i in range(EXTRA_FIELD_PAD)]
    frame = pd.read_csv(
        io.StringIO(body),
        # Pass the delimiter literally. re.escape("$") gives "\$", which pandas
        # reads as a multi-character separator and therefore as a regex, which
        # the fast C engine refuses.
        sep=delimiter,
        engine="c",
        names=columns + placeholders,
        header=None,
        index_col=False,
        dtype=str,
        na_filter=False,
        on_bad_lines="skip",
        quoting=csv.QUOTE_NONE,
        skip_blank_lines=True,
    )
    del text, body

    rows_with_trailing_field = 0
    surplus_values = 0
    for position, name in enumerate(placeholders):
        column = frame[name]
        present = column.notna()
        populated = present & (column.fillna("").str.strip() != "")
        if position == 0:
            rows_with_trailing_field = int(present.sum())
        surplus_values += int(populated.sum())
    if surplus_values:
        log.warning(
            "%s %s: %d values found beyond the %d declared columns",
            quarter, table, surplus_values, len(columns),
        )
    frame = frame.drop(columns=placeholders)

    stats = {
        "rows_parsed": len(frame),
        "rows_raw": raw_lines,
        "rows_skipped": max(0, raw_lines - len(frame)),
        "decode_errors": decode_errors,
        "n_columns": len(columns),
        "rows_with_trailing_field": rows_with_trailing_field,
        "surplus_values": surplus_values,
        "columns": ";".join(columns),
    }

    for column in frame.columns:
        frame[column] = frame[column].fillna("").str.strip()

    id_nulls = 0
    for column in ID_COLUMNS:
        if column not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        nulls = int(numeric.isna().sum())
        # A column shift shows up here as a near-total failure to cast, which is
        # exactly how the trailing-delimiter bug was caught. Fail the quarter
        # rather than writing plausible-looking but misaligned parquet.
        if len(frame) and nulls / len(frame) > ID_NULL_TOLERANCE:
            raise ValueError(
                f"{quarter} {table}: {nulls:,}/{len(frame):,} values in '{column}' "
                f"are not integers -- columns are probably misaligned. "
                f"First values: {frame[column].head(3).tolist()}"
            )
        id_nulls += nulls
        frame[column] = numeric.astype("Int64")
    stats["id_nulls"] = id_nulls

    frame["quarter"] = quarter
    frame["era"] = cfg.era_of(quarter)
    return frame, stats


def _relative_output(destination: Path) -> Path:
    """Project-relative path for the manifest, falling back to absolute.

    Output can legitimately sit outside the project root -- tests redirect it to
    a temporary directory -- and a manifest field is not worth raising over.
    """
    try:
        return destination.relative_to(cfg.PROJECT_ROOT)
    except ValueError:
        return destination


def parse_quarter(quarter: str) -> list[dict]:
    conf = cfg.load_config()
    delimiter = conf["data"]["delimiter"]
    ignore = set(conf["harmonization"].get("ignore_tables", []))
    wanted = set(conf["data"]["tables"]) - ignore
    out_root = cfg.path("parquet")

    rows: list[dict] = []
    with zipfile.ZipFile(cfg.zip_path(quarter)) as zf:
        for info in zf.infolist():
            table, kind = classify_member(info.filename)
            if kind != "table" or table not in wanted:
                continue
            frame, stats = parse_member(zf, info.filename, table, quarter, delimiter)

            destination = out_root / table / f"{table}_{quarter}.parquet"
            destination.parent.mkdir(parents=True, exist_ok=True)
            table_arrow = pa.Table.from_pandas(frame, preserve_index=False)
            pq.write_table(table_arrow, destination, compression="zstd")

            rows.append({
                "quarter": quarter,
                "era": cfg.era_of(quarter),
                "table": table,
                "member": info.filename,
                "output": str(_relative_output(destination)),
                "output_bytes": destination.stat().st_size,
                **stats,
            })
            del frame, table_arrow

    # A table that fails to match the member pattern is not an error anywhere
    # above -- it is simply never seen, and the quarter quietly produces fewer
    # tables. That is how 2018Q1 lost its entire DEMO table to a file named
    # DEMO18Q1_new.txt. Missing input must fail loudly.
    produced = [r["table"] for r in rows]
    missing = wanted - set(produced)
    if missing:
        members = [i.filename for i in zipfile.ZipFile(cfg.zip_path(quarter)).infolist()]
        raise ValueError(
            f"{quarter}: no member matched for table(s) {sorted(missing)}. "
            f"Archive contains: {sorted(members)}"
        )
    duplicates = {t for t in produced if produced.count(t) > 1}
    if duplicates:
        raise ValueError(f"{quarter}: multiple members matched table(s) {sorted(duplicates)}")
    return rows


def extract_deleted_cases() -> dict:
    """Collect every deleted case id shipped in the archives.

    Five naming conventions across 30 quarters -- see config. Matching is on the
    substring "delet" in the full path, because from 2021Q4 the basename is
    DELETEnnQn.txt and contains no "deleted" at all.
    """
    conf = cfg.load_config()["deleted_cases"]
    pattern = re.compile(conf["member_pattern"])
    records: list[dict] = []
    all_ids: set[int] = set()

    for quarter in cfg.all_quarters():
        with zipfile.ZipFile(cfg.zip_path(quarter)) as zf:
            for info in zf.infolist():
                if info.filename.endswith("/") or not pattern.search(info.filename):
                    continue
                text, _ = _decode(zf.read(info.filename))
                ids = {int(line) for line in text.split() if line.strip().isdigit()}
                cumulative = info.filename == conf["cumulative_file"]["member"]
                records.append({
                    "quarter": quarter,
                    "member": info.filename,
                    "is_cumulative": cumulative,
                    "n_case_ids": len(ids),
                })
                all_ids |= ids

    destination = cfg.path("parquet").parent / "deleted_cases.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({"case_id": pa.array(sorted(all_ids), type=pa.int64())}),
        destination,
        compression="zstd",
    )
    return {"records": records, "n_unique": len(all_ids), "output": destination}


def _write_manifest(rows: list[dict]) -> Path:
    out_dir = cfg.path("tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "parse_manifest.csv"
    fields = [
        "quarter", "era", "table", "member", "output", "output_bytes",
        "rows_raw", "rows_parsed", "rows_skipped", "id_nulls",
        "decode_errors", "rows_with_trailing_field", "surplus_values",
        "n_columns", "columns",
    ]
    rows = sorted(rows, key=lambda r: (r["table"], cfg.quarter_index(r["quarter"])))
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarters", nargs="*")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-deleted", action="store_true")
    args = parser.parse_args(argv)

    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.FileHandler(log_dir / "parse.log"),
                  logging.StreamHandler(sys.stdout)],
        force=True,
    )

    quarters = args.quarters or cfg.all_quarters()
    log.info("parsing %d quarters with %d workers", len(quarters), args.workers)

    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(parse_quarter, q): q for q in quarters}
        for done, future in enumerate(as_completed(futures), start=1):
            quarter = futures[future]
            try:
                quarter_rows = future.result()
            except Exception as exc:  # noqa: BLE001 - report and keep going
                log.error("%s: FAILED (%s: %s)", quarter, type(exc).__name__, exc)
                continue
            rows.extend(quarter_rows)
            skipped = sum(r["rows_skipped"] for r in quarter_rows)
            log.info(
                "%s: %d tables, %s rows, %d skipped  [%d/%d]",
                quarter, len(quarter_rows),
                f"{sum(r['rows_parsed'] for r in quarter_rows):,}",
                skipped, done, len(quarters),
            )

    manifest = _write_manifest(rows)
    log.info("manifest -> %s", manifest)
    log.info(
        "total: %s rows across %d table-quarters, %s skipped, %s id nulls, %s decode errors",
        f"{sum(r['rows_parsed'] for r in rows):,}", len(rows),
        f"{sum(r['rows_skipped'] for r in rows):,}",
        f"{sum(r['id_nulls'] for r in rows):,}",
        f"{sum(r['decode_errors'] for r in rows):,}",
    )

    if not args.skip_deleted:
        deleted = extract_deleted_cases()
        log.info(
            "deleted cases: %s unique ids from %d files -> %s",
            f"{deleted['n_unique']:,}", len(deleted["records"]), deleted["output"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
