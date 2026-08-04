"""Configuration loading, path resolution, and FAERS quarter arithmetic.

Every pipeline stage imports from here so that the project root, the quarter
list, and the download URLs are defined in exactly one place.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


@functools.lru_cache(maxsize=1)
def load_config() -> dict:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def resolve(relative: str) -> Path:
    """Resolve a config-declared relative path against the project root."""
    return PROJECT_ROOT / relative


def path(key: str) -> Path:
    """Resolve one of the entries under the config's `paths` block."""
    return resolve(load_config()["paths"][key])


# --- quarter arithmetic ----------------------------------------------------
# Quarters are the strings FDA uses in filenames: "2004q1", "2026q2".


def parse_quarter(q: str) -> tuple[int, int]:
    q = q.strip().lower()
    year, _, quarter = q.partition("q")
    return int(year), int(quarter)


def format_quarter(year: int, quarter: int) -> str:
    return f"{year}q{quarter}"


def quarter_index(q: str) -> int:
    """Monotonic integer index, so quarters can be compared and subtracted."""
    year, quarter = parse_quarter(q)
    return year * 4 + (quarter - 1)


def quarter_range(start: str, end: str) -> list[str]:
    """Inclusive list of quarters from `start` to `end`."""
    if quarter_index(start) > quarter_index(end):
        raise ValueError(f"start quarter {start} is after end quarter {end}")
    out = []
    year, quarter = parse_quarter(start)
    while quarter_index(format_quarter(year, quarter)) <= quarter_index(end):
        out.append(format_quarter(year, quarter))
        quarter += 1
        if quarter > 4:
            year, quarter = year + 1, 1
    return out


def all_quarters() -> list[str]:
    """Every quarter in the configured study window."""
    cfg = load_config()["data"]
    return quarter_range(cfg["start_quarter"], cfg["end_quarter"])


def is_legacy(q: str) -> bool:
    """True for the LAERS-era quarters, which use the `aers_ascii_` prefix."""
    cfg = load_config()["data"]
    return quarter_index(q) <= quarter_index(cfg["legacy_last_quarter"])


def zip_name(q: str) -> str:
    cfg = load_config()["data"]
    prefix = cfg["legacy_prefix"] if is_legacy(q) else cfg["modern_prefix"]
    return f"{prefix}{q}.zip"


def zip_url(q: str) -> str:
    cfg = load_config()["data"]
    return f"{cfg['base_url'].rstrip('/')}/{zip_name(q)}"


def zip_path(q: str) -> Path:
    return path("raw") / zip_name(q)


def era_of(q: str) -> str:
    """Name of the configured era a quarter falls into.

    The era blocks in config.yaml record *expected* schemas. Phase 1a audits the
    real column headers and is authoritative where the two disagree.
    """
    idx = quarter_index(q)
    for name, era in load_config()["eras"].items():
        if quarter_index(era["start"]) <= idx <= quarter_index(era["end"]):
            return name
    raise ValueError(f"quarter {q} falls outside every configured era")
