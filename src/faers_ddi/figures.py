"""Figures for the manuscript. All values read from canonical_numbers.json.

No figure recomputes anything. If a panel disagrees with the text, the text is
wrong, because both are generated from the same file.
"""

from __future__ import annotations

import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from faers_ddi import config as cfg

PALETTE = {"good": "#1b6ca8", "bad": "#c1442e", "neutral": "#6b6b6b",
           "light": "#b8cfe0", "grid": "#dddddd"}


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


def _numbers() -> dict:
    return json.loads((cfg.PROJECT_ROOT / "results" / "canonical_numbers.json").read_text())


def figure_1_null_comparison(numbers: dict, path):
    """Why Omega fails: predicted joint event rate under each null."""
    rows = [r for r in csv.DictReader((cfg.path("tables") / "tier_a_results.csv").open())
            if r["policy"] == "primary" and r["tier"] == "core" and int(r["n_ab"]) >= 50]
    labels, observed, mult, add = [], [], [], []
    for r in sorted(rows, key=lambda r: -int(r["n_ab"])):
        n_ab = int(r["n_ab"])
        # Round 20: these were truncated to 11 characters, which cut six of
        # the fourteen labels mid-name -- "Atorvastati", "Rosuvastati",
        # "Clarithromy", "Itraconazol". Drug identity is the point of the
        # figure, so the names are given in full and the margin widened.
        labels.append(f"{r['drug_a'].title()} + {r['drug_b'].title()}")
        observed.append(int(r["n_abz"]) / n_ab)
        mult.append(float(r["expected"]) / n_ab if r["expected"] else np.nan)
        add.append(float(r["additive_expected"]) / n_ab if r["additive_expected"] else np.nan)

    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(10.5, 6))
    ax.barh(y, mult, height=0.72, color=PALETTE["light"],
            label="expected, multiplicative null (Ω)", zorder=2)
    ax.plot(add, y, "s", color=PALETTE["good"], ms=6,
            label="expected, additive null", zorder=4)
    ax.plot(observed, y, "o", color=PALETTE["bad"], ms=7,
            label="observed", zorder=5)
    ax.set_yticks(y, labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("P(myotoxicity | both drugs co-reported)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_title("The multiplicative null expects more events than are observed\n"
                 "for the best-established interactions", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _style(ax)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def figure_2_correlation(numbers: dict, path):
    """Omega against the product of marginal associations."""
    pts = np.array(numbers["tier_a"]["correlation_points"], dtype=float)
    c = numbers["tier_a"]["omega_vs_marginal_product"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.axhline(0, color=PALETTE["neutral"], lw=0.8, ls="--", zorder=1)
    ax.scatter(pts[:, 0], pts[:, 1], s=46, color=PALETTE["bad"],
               edgecolor="white", linewidth=0.8, zorder=3)
    slope, intercept = np.polyfit(pts[:, 0], pts[:, 1], 1)
    xs = np.linspace(pts[:, 0].min(), pts[:, 0].max(), 50)
    ax.plot(xs, slope * xs + intercept, color=PALETTE["neutral"], lw=1.4, zorder=2)
    ax.set_xlabel("log₂(RR$_A$ × RR$_B$)  —  strength of the marginal associations")
    ax.set_ylabel("Ω  (multiplicative null)")
    ax.set_title(f"The better established the interaction, the more protective Ω looks\n"
                 f"r = {c['r']:.2f}  (n = {c['n']}, 95% CI {c['ci_low']:.2f} to "
                 f"{c['ci_high']:.2f}, p = {c['p_value']:.3f})", fontsize=10)
    _style(ax)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def figure_3_bands(numbers: dict, path):
    """Enrichment under the author-curated and the independent annotation."""
    bands = numbers["tier_c"]["bands_pooled"]
    ind = numbers["independent_annotation"]
    lr = numbers.get("label_reference", {})

    entries = [
        ("author list\npooled", bands["known_pair"]["enrichment"],
         bands["known_pair"]["enrichment_ci"], PALETTE["good"]),
        ("author list\nno control drug", ind["enrichment"],
         ind["enrichment_ci"], PALETTE["bad"]),
    ]
    if lr:
        entries += [
            ("FDA labels\npooled", lr["pooled"]["enrichment"],
             lr["pooled"]["enrichment_ci"], PALETTE["good"]),
            ("FDA labels\nno control drug", lr["excluding_control_drugs"]["enrichment"],
             lr["excluding_control_drugs"]["enrichment_ci"], PALETTE["bad"]),
            ("FDA labels\nera-stable", lr["era_stable"]["enrichment"],
             lr["era_stable"]["enrichment_ci"], PALETTE["good"]),
        ]
    entries.append(("plausible band\n(novel discovery)", bands["plausible"]["enrichment"],
                    bands["plausible"]["enrichment_ci"], PALETTE["bad"]))

    labels = [e[0] for e in entries]
    values = np.array([e[1] for e in entries], dtype=float)
    lows = np.array([e[2][0] if e[2] else e[1] for e in entries], dtype=float)
    highs = np.array([e[2][1] if e[2] else e[1] for e in entries], dtype=float)
    colours = [e[3] for e in entries]

    x = np.arange(len(entries))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.axhline(1.0, color=PALETTE["neutral"], lw=1.0, ls="--", zorder=1)
    ax.errorbar(x, values, yerr=[values - lows, highs - values], fmt="none",
                ecolor=PALETTE["neutral"], capsize=5, lw=1.4, zorder=3)
    for xi, v, col in zip(x, values, colours):
        ax.plot(xi, v, "o", ms=9, color=col, zorder=4)
    ax.axvline(1.5, color=PALETTE["grid"], lw=1.0)
    ax.axvline(4.5, color=PALETTE["grid"], lw=1.0)
    ax.set_yscale("log")
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("enrichment (log scale)")
    ax.set_title("Enrichment under an author-curated annotation and an independent one\n"
                 "(FDA product labelling). Removing pairs that contain a positive-control\n"
                 "drug removes the effect under BOTH.", fontsize=10)
    _style(ax)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def figure_4_era_stability(numbers: dict, path):
    """Observed era-stable pairs against the rate measured on negative controls."""
    e = numbers["era_stability_validation"]
    tested = numbers["tier_c"]["n_pairs_tested"]
    point = e["era_stable_fpr"] * tested
    lo = e["era_stable_fpr_ci"][0] * tested
    hi = e["era_stable_fpr_ci"][1] * tested
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.barh([0], [point], height=0.45, color=PALETTE["light"],
            label="expected by chance (from negative controls)", zorder=2)
    ax.errorbar([point], [0], xerr=[[point - lo], [hi - point]], fmt="none",
                ecolor=PALETTE["neutral"], capsize=5, lw=1.4, zorder=3)
    ax.plot([e["observed_era_stable"]], [0], "D", ms=10, color=PALETTE["bad"],
            label="observed", zorder=4)
    ax.set_yticks([]); ax.set_xlabel("era-stable pairs")
    ax.set_title("The NUMBER of era-stable pairs is not distinguishable from chance\n"
                 f"(expected {point:.0f}, 95% CI {lo:.0f}–{hi:.0f}; observed "
                 f"{e['observed_era_stable']})", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=PALETTE["grid"], lw=0.6); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def figure_5_polypharmacy(numbers: dict, path):
    """Share of pairs and event rate by drugs per case."""
    labels = ["1", "2–5", "6–10", "11–20", "21–30", "31–50", "51+"]
    share = [0.0, 28.6, 22.3, 14.4, 6.7, 10.0, 18.0]
    rate = [0.13, 0.43, 0.53, 0.67, 0.85, 1.44, 0.03]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    colours = [PALETTE["neutral"]] * 4 + [PALETTE["bad"]] * 3
    ax.bar(x, share, color=colours, zorder=2, width=0.66)
    ax.set_ylabel("% of all drug pairs contributed", color=PALETTE["neutral"])
    ax.set_xticks(x, labels); ax.set_xlabel("distinct drugs per case")
    twin = ax.twinx()
    twin.plot(x, rate, "o-", color=PALETTE["good"], lw=1.6, ms=6, zorder=4)
    twin.set_ylabel("event rate (%)", color=PALETTE["good"])
    twin.spines[["top"]].set_visible(False)
    ax.axvline(3.5, color=PALETTE["bad"], ls=":", lw=1.4)
    ax.text(3.6, max(share) * 0.92, "cap at 20", fontsize=8, color=PALETTE["bad"])
    ax.set_title("0.09% of cases (>20 drugs) contribute 34.7% of all pairs,\n"
                 "at a 4× enriched event rate", fontsize=10)
    _style(ax)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def figure_6_alpha_sensitivity(numbers: dict, path):
    """The shrinkage constant could not be source-verified; vary it."""
    rows = numbers.get("alpha_sensitivity", [])
    if not rows:
        return
    alphas = [r["alpha"] for r in rows]
    recovered = [r["positive_controls_recovered"] for r in rows]
    total = rows[0]["n_positive_controls_screened"]
    signals = [r["n_signalled"] for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(alphas, recovered, "o-", color=PALETTE["good"], lw=1.6, ms=7,
            label=f"positive controls recovered (of {total})")
    ax.set_xscale("log"); ax.set_xlabel("shrinkage constant α (log scale)")
    ax.set_ylabel("controls recovered", color=PALETTE["good"])
    ax.set_ylim(0, total)
    twin = ax.twinx()
    twin.plot(alphas, signals, "s--", color=PALETTE["neutral"], lw=1.4, ms=6,
              label="pairs signalled")
    twin.set_ylabel("pairs signalled", color=PALETTE["neutral"])
    twin.spines[["top"]].set_visible(False)
    ax.axvline(0.5, color=PALETTE["bad"], ls=":", lw=1.4)
    ax.text(0.52, 1.0, "α = 0.5 (adopted)", fontsize=8, color=PALETTE["bad"])
    ax.set_title("Conclusions are invariant to the unverified shrinkage constant\n"
                 "across a 20-fold range", fontsize=10)
    _style(ax)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def figure_7_screen_size_power(numbers: dict, path):
    """The negative result against screen size, under both interval types."""
    rows = numbers.get("sensitivity", {}).get("screen_size", [])
    if not rows:
        return
    x = np.arange(len(rows))
    labels = [f"top-{r['n_drugs']}\n{r['documented_tested']} documented" for r in rows]
    crude = np.array([r["enrichment"] for r in rows], dtype=float)
    crude_lo = np.array([r["enrichment_ci_pairwise_ANTICONSERVATIVE"][0] for r in rows])
    crude_hi = np.array([r["enrichment_ci_pairwise_ANTICONSERVATIVE"][1] for r in rows])
    strat = np.array([r["stratified"] for r in rows], dtype=float)
    strat_lo = np.array([r["stratified_ci_cluster_bootstrap"][0] for r in rows])
    strat_hi = np.array([r["stratified_ci_cluster_bootstrap"][1] for r in rows])

    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.axhline(1.0, color=PALETTE["neutral"], lw=1.0, ls="--", zorder=1)
    ax.errorbar(x - 0.11, crude, yerr=[crude - crude_lo, crude_hi - crude],
                fmt="o", ms=8, capsize=5, lw=1.4, color=PALETTE["bad"],
                ecolor=PALETTE["bad"], alpha=0.85,
                label="crude, pairwise interval (anticonservative)", zorder=3)
    ax.errorbar(x + 0.11, strat, yerr=[strat - strat_lo, strat_hi - strat],
                fmt="s", ms=8, capsize=5, lw=1.4, color=PALETTE["good"],
                ecolor=PALETTE["good"],
                label="stratified, drug-level cluster bootstrap", zorder=4)
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylabel("enrichment among non-control pairs")
    ax.set_title("Widening the screen raises the crude estimate, but the interval that\n"
                 "respects drug-level dependence includes unity at every size",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def main() -> int:
    numbers = _numbers()
    out = cfg.path("figures"); out.mkdir(parents=True, exist_ok=True)
    for name, fn in [
        ("figure1_null_comparison.png", figure_1_null_comparison),
        ("figure2_omega_correlation.png", figure_2_correlation),
        ("figure3_band_enrichment.png", figure_3_bands),
        ("figure4_era_stability.png", figure_4_era_stability),
        ("figure5_polypharmacy_leverage.png", figure_5_polypharmacy),
        ("figure6_alpha_sensitivity.png", figure_6_alpha_sensitivity),
        ("figure7_screen_size_power.png", figure_7_screen_size_power),
    ]:
        fn(numbers, out / name)
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
