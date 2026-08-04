"""Phase 1 -- download every quarterly FAERS/LAERS archive from the FDA.

Resumable: the FDA server honours HTTP range requests, so an interrupted
download continues from where it stopped rather than restarting. Each file is
written to a `.part` sibling and atomically renamed only after the archive's
central directory parses, so a partial file can never be mistaken for a complete
one by a later stage.

Emits results/tables/download_manifest.csv with a sha256 per archive. That
manifest is what makes the study reproducible: FDA silently re-issues quarterly
files when cases are corrected, so "FAERS 2019Q2" is not by itself a
identification of the data that produced a result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

from faers_ddi import config as cfg

CHUNK = 1 << 20  # 1 MiB
# (connect, read). The read timeout is generous because the FDA host regularly
# stalls mid-transfer on the larger modern archives; a short timeout throws away
# a connection that is slow but still alive. Partial progress survives either
# way -- the .part file is resumed via a range request -- but reconnecting is
# expensive enough that waiting is cheaper.
TIMEOUT = (30, 300)
USER_AGENT = "faers-ddi-research/0.1 (academic pharmacovigilance study)"

log = logging.getLogger("download")


def _setup_logging(verbose: bool = True) -> None:
    log_dir = cfg.path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(log_dir / "download.log")]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
        force=True,
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def verify_archive(path: Path) -> tuple[bool, list[str], str]:
    """Parse the zip central directory. Returns (ok, member_names, error)."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
        if not names:
            return False, [], "archive contains no members"
        return True, names, ""
    except zipfile.BadZipFile as exc:
        return False, [], f"bad zip: {exc}"
    except Exception as exc:  # noqa: BLE001 - report whatever went wrong
        return False, [], f"{type(exc).__name__}: {exc}"


def _download_once(session: requests.Session, url: str, dest: Path) -> None:
    """Fetch `url` into `dest`, resuming from an existing `.part` if present."""
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0

    # Accept-Encoding must be identity. requests defaults to "gzip, deflate",
    # and the FDA host hangs mid-response rather than refusing when asked to
    # content-encode a zip -- reproducibly, while an otherwise identical request
    # with identity returns in ~2s. Requesting gzip on an already-compressed
    # archive buys nothing and also muddies Content-Length and range semantics.
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if have:
        headers["Range"] = f"bytes={have}-"

    with session.get(url, headers=headers, stream=True, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        # If we asked to resume but the server ignored it and sent the whole
        # body, discard what we had rather than concatenating two copies.
        if have and resp.status_code != 206:
            log.warning("%s: server ignored range request, restarting", dest.name)
            have = 0
        mode = "ab" if have else "wb"
        with part.open(mode) as fh:
            for chunk in resp.iter_content(CHUNK):
                if chunk:
                    fh.write(chunk)

    ok, _, err = verify_archive(part)
    if not ok:
        part.unlink(missing_ok=True)  # corrupt; do not leave it to be resumed
        raise OSError(f"{dest.name}: {err}")
    part.replace(dest)


def fetch_quarter(quarter: str, retries: int, force: bool) -> dict:
    """Download one quarter, retrying with backoff. Returns a manifest row."""
    dest = cfg.zip_path(quarter)
    url = cfg.zip_url(quarter)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        ok, names, err = verify_archive(dest)
        if ok:
            log.info("%s: already present (%d members), skipping", dest.name, len(names))
            return _manifest_row(quarter, dest, url, names, ok=True, error="", cached=True)
        log.warning("%s: present but unreadable (%s); re-downloading", dest.name, err)
        dest.unlink(missing_ok=True)

    session = requests.Session()
    part = dest.with_suffix(dest.suffix + ".part")
    last_error = ""
    attempt = 0
    stalled = 0  # consecutive attempts that transferred nothing new

    # A failed attempt that still moved bytes is progress, not a failure, so it
    # does not consume the retry budget. Only genuinely stalled attempts do.
    # Without this, a large archive over a flaky link exhausts its retries while
    # steadily downloading.
    while stalled < retries:
        attempt += 1
        before = part.stat().st_size if part.exists() else 0
        try:
            started = time.monotonic()
            _download_once(session, url, dest)
            mb = dest.stat().st_size / 1e6
            log.info(
                "%s: %.1f MB, done in %.0fs (attempt %d)",
                dest.name, mb, time.monotonic() - started, attempt,
            )
            ok, names, err = verify_archive(dest)
            return _manifest_row(quarter, dest, url, names, ok=ok, error=err, cached=False)
        except Exception as exc:  # noqa: BLE001 - retry on anything transient
            last_error = f"{type(exc).__name__}: {exc}"
            after = part.stat().st_size if part.exists() else 0
            gained = after - before
            if gained > 0:
                stalled = 0
                log.info(
                    "%s: interrupted after +%.1f MB (%.1f MB held), resuming",
                    dest.name, gained / 1e6, after / 1e6,
                )
                backoff = 2
            else:
                stalled += 1
                backoff = min(120, 5 * 2**stalled)
                log.warning(
                    "%s: no progress, stall %d/%d (%s); retrying in %ds",
                    dest.name, stalled, retries, last_error, backoff,
                )
            time.sleep(backoff)

    log.error("%s: giving up after %d attempts (%s)", dest.name, attempt, last_error)
    return {
        "quarter": quarter,
        "era": cfg.era_of(quarter),
        "filename": cfg.zip_name(quarter),
        "url": url,
        "bytes": 0,
        "sha256": "",
        "n_members": 0,
        "members": "",
        "zip_ok": False,
        "cached": False,
        "error": last_error,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _manifest_row(quarter, dest, url, names, *, ok, error, cached) -> dict:
    return {
        "quarter": quarter,
        "era": cfg.era_of(quarter),
        "filename": dest.name,
        "url": url,
        "bytes": dest.stat().st_size if dest.exists() else 0,
        "sha256": sha256_of(dest) if dest.exists() else "",
        "n_members": len(names),
        "members": ";".join(sorted(names)),
        "zip_ok": ok,
        "cached": cached,
        "error": error,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


FIELDS = [
    "quarter", "era", "filename", "url", "bytes", "sha256",
    "n_members", "zip_ok", "cached", "error", "retrieved_utc", "members",
]


def write_manifest(rows: list[dict]) -> Path:
    out_dir = cfg.path("tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "download_manifest.csv"
    rows = sorted(rows, key=lambda r: cfg.quarter_index(r["quarter"]))
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarters", nargs="*", help="subset, e.g. 2004q1 2020q3")
    parser.add_argument("--workers", type=int, default=3,
                        help="parallel downloads; keep modest, the FDA host is slow")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args(argv)

    _setup_logging()
    quarters = args.quarters or cfg.all_quarters()
    log.info("downloading %d quarters with %d workers", len(quarters), args.workers)

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(fetch_quarter, q, args.retries, args.force): q for q in quarters
        }
        for i, fut in enumerate(as_completed(futures), start=1):
            rows.append(fut.result())
            log.info("progress: %d/%d complete", i, len(quarters))

    manifest = write_manifest(rows)
    failed = [r["quarter"] for r in rows if not r["zip_ok"]]
    total_gb = sum(r["bytes"] for r in rows) / 1e9
    log.info("manifest written to %s", manifest)
    log.info("%d/%d archives OK, %.2f GB total", len(rows) - len(failed), len(rows), total_gb)
    if failed:
        log.error("FAILED quarters: %s", ", ".join(sorted(failed)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
