"""Every figure reported in the manuscript must match `canonical_numbers.json`.

This exists because it failed. The analysis stages were run separately and
re-run as bugs were fixed, and the write-ups accumulated figures from different
generations of the pipeline: a 6.2% false-positive rate against 6.6% on disk, a
calibrated threshold of +0.305 in config against +0.374 in the table it came
from, 11/16 positive controls against 12/16. Each was true when written.

`run_analysis.py` produces every number in one uninterrupted pass. These tests
assert the prose agrees with it, so a stale figure fails the suite rather than
surviving into a paper.
"""

from __future__ import annotations

import json
import re

import pytest

from faers_ddi import config as cfg

CANONICAL = cfg.PROJECT_ROOT / "results" / "canonical_numbers.json"
MANUSCRIPT = cfg.PROJECT_ROOT / "paper" / "manuscript.md"
README = cfg.PROJECT_ROOT / "README.md"


@pytest.fixture(scope="module")
def numbers() -> dict:
    if not CANONICAL.exists():
        pytest.skip("run `python -m faers_ddi.run_analysis` first")
    return json.loads(CANONICAL.read_text())


@pytest.fixture(scope="module")
def manuscript() -> str:
    """The manuscript, with typographic minus signs normalised to ASCII.

    Prose uses U+2212 MINUS SIGN; `f"{-0.63:.2f}"` produces U+002D HYPHEN-MINUS.
    Without this, changing the typography of a correct number fails the test and
    changing the number does not — exactly backwards. Digits are untouched.
    """
    return MANUSCRIPT.read_text().replace("−", "-")


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text()


# --- the canonical file itself ---------------------------------------------


def test_canonical_numbers_are_internally_consistent(numbers):
    tier_c = numbers["tier_c"]
    assert tier_c["n_signalled"] <= tier_c["n_pairs_tested"]
    assert sum(tier_c["by_era_count"].values()) == tier_c["n_signalled"]
    assert tier_c["era_stable"]["n_pairs"] == tier_c["by_era_count"]["3"]
    assert numbers["n_event_cases"] < numbers["n_cases"]
    assert numbers["tier_a"]["recovered_powered"] <= numbers["tier_a"]["n_powered"]
    assert numbers["tier_a"]["n_powered"] <= numbers["tier_a"]["n_controls"]


def test_band_counts_sum_to_pairs_tested(numbers):
    bands = numbers["tier_c"]["bands_pooled"]
    tested = sum(v["tested"] for k, v in bands.items() if isinstance(v, dict))
    assert tested == numbers["tier_c"]["n_pairs_tested"]


def test_era_stable_is_a_subset_of_signalled(numbers):
    stable = numbers["tier_c"]["era_stable"]["bands"]
    pooled = numbers["tier_c"]["bands_pooled"]
    for band, values in stable.items():
        if isinstance(values, dict):
            assert values["signalled"] <= pooled[band]["signalled"]


# --- the configured threshold must be the calibrated one -------------------


def test_config_threshold_matches_calibration(numbers):
    configured = cfg.load_config()["analysis"]["omega"]["signal_threshold"]
    assert configured == pytest.approx(
        numbers["tier_b"]["calibrated_threshold"], abs=1e-3)


# --- the manuscript ---------------------------------------------------------


def _all_numbers(text: str, pattern: str) -> list[str]:
    return re.findall(pattern, text)


def test_manuscript_reports_the_case_count(manuscript, numbers):
    assert f"{numbers['n_cases']:,}" in manuscript
    assert f"{numbers['n_event_cases']:,}" in manuscript


def test_manuscript_reports_tier_a_recovery(manuscript, numbers):
    a = numbers["tier_a"]
    assert f"{a['recovered_additive']}/{a['n_controls']}" in manuscript
    assert f"{a['recovered_powered']}/{a['n_powered']}" in manuscript
    assert f"{a['recovered_multiplicative']}/{a['n_controls']}" in manuscript


def test_manuscript_reports_the_false_positive_rate(manuscript, numbers):
    rate = numbers["tier_b"]["strata"]["all"]["fpr_additive"]
    assert f"{100 * rate:.1f}%" in manuscript


def test_manuscript_reports_the_calibrated_threshold(manuscript, numbers):
    assert f"{numbers['tier_b']['calibrated_threshold']:+.3f}" in manuscript


def test_manuscript_reports_screen_totals(manuscript, numbers):
    c = numbers["tier_c"]
    assert f"{c['n_pairs_tested']:,}" in manuscript
    assert f"{c['n_signalled']:,}" in manuscript


def test_manuscript_reports_era_stable_counts(manuscript, numbers):
    stable = numbers["tier_c"]["era_stable"]
    assert str(stable["n_pairs"]) in manuscript
    enrichment = stable["bands"]["known_pair"]["enrichment"]
    assert f"{enrichment:.2f}" in manuscript or f"{enrichment:.1f}" in manuscript


def test_manuscript_does_not_contain_superseded_figures(manuscript, numbers):
    """Explicitly ban figures from earlier generations of the pipeline."""
    threshold = numbers["tier_b"]["calibrated_threshold"]
    superseded = ["+0.305", "+0.374", "+0.394", "+0.092", "+0.423"]
    for value in superseded:
        if abs(float(value) - threshold) > 1e-3:
            assert value not in manuscript, f"superseded threshold {value}"


def test_manuscript_reports_the_leave_one_out_validation(manuscript, numbers):
    """The estimand was chosen on the evaluation set; the cross-validation of
    that choice must be reported, not just the switch."""
    loo = numbers["tier_a"]["leave_one_out"]
    assert f"{loo['folds_selecting_additive']}/{loo['n_folds']}" in manuscript
    assert "optimism" in manuscript.lower()


def test_manuscript_reports_the_correlation_with_n_ci_and_p(manuscript, numbers):
    """Reporting r alone was the original defect."""
    c = numbers["tier_a"]["omega_vs_marginal_product"]
    assert f"{c['r']:.2f}" in manuscript
    assert f"n = {c['n']}" in manuscript
    assert f"{c['p_value']:.3f}" in manuscript
    assert f"{c['ci_low']:.2f}" in manuscript


def test_manuscript_reports_era_stability_validated_on_negatives(manuscript, numbers):
    """The filter promoted as the main contribution had never been applied to
    the negative controls. Its false-positive rate must appear."""
    ev = numbers["era_stability_validation"]
    assert f"{ev['pass_era_stability']}" in manuscript
    assert f"{100 * ev['era_stable_fpr']:.3f}%" in manuscript
    assert "not distinguishable from chance" in manuscript.lower()


def test_no_figure_carries_hardcoded_data(numbers):
    """Round 20+2. Figure 5's fourteen values were literals in figures.py --
    the stale-Table-1 defect relocated into the one medium the table provenance
    guard did not look at. The values were exactly right, which is precisely why
    nothing caught them: only their provenance was wrong, and the paper claims
    in Data and code availability that every figure is generated from the
    canonical file.

    Round 20's guard was scoped to the MEDIUM the defect was found in (markdown
    tables) rather than to the defect (numbers without provenance). This one is
    scoped to the defect: no figure function may contain a literal numeric
    sequence, because that is what hand-entered data looks like in plotting code.
    """
    import re as _re

    source = (cfg.PROJECT_ROOT / "src" / "faers_ddi" / "figures.py").read_text()
    offenders = []
    for match in _re.finditer(r"^\s*(\w+)\s*=\s*\[([^\]]*)\]", source, _re.M):
        name, body = match.group(1), match.group(2)
        # a sequence of two or more bare numeric literals
        literals = _re.findall(r"(?<![\w.])-?\d+\.?\d*(?![\w.])", body)
        if len(literals) >= 2 and not _re.search(r"[A-Za-z_]\w*\s*[\[(]", body):
            offenders.append((name, body[:70]))
    assert not offenders, (
        "figures.py contains hardcoded numeric data; figures must be derived "
        "from canonical_numbers.json or the shipped tables: "
        + "; ".join(f"{n} = [{b}...]" for n, b in offenders))

    # and the band data the figure now uses must actually be in the canonical file
    pb = numbers["audit"]["polypharmacy_bands"]
    assert len(pb["bands"]) >= 5
    assert abs(sum(b["share_of_pairs"] for b in pb["bands"]) - 100.0) < 0.5, (
        "band shares must sum to 100%")
    above = [b for b in pb["bands"] if b["band"] in ("21-30", "31-50", "51+")]
    assert abs(sum(b["share_of_pairs"] for b in above)
               - pb["above_cap_share_of_pairs"]) < 0.15


def test_polypharmacy_reversal_is_disclosed(manuscript, numbers):
    """Round 20+2. The '4x enriched event rate' aggregate hides a reversal: the
    51+ band contributes the largest share of pairs of any band while running
    far BELOW background. Figure 5 shows it; the text did not mention it."""
    pb = numbers["audit"]["polypharmacy_bands"]
    top = next(b for b in pb["bands"] if b["band"] == "51+")
    assert top["event_rate"] < pb["background_event_rate"], (
        "this guard assumes the 51+ band is depleted; if that changed, the "
        "prose it protects needs rewriting rather than the guard relaxing")
    flat = " ".join(manuscript.split())
    assert f"{top['event_rate']:.2f}%" in flat, (
        f"the 51+ band event rate {top['event_rate']:.2f}% must be stated, not "
        f"folded into the aggregate")
    assert "below the 0.207% background" in flat or "below" in flat.lower(), (
        "the reversal must be described, not merely tabulated")


def test_figures_do_not_plot_retracted_quantities(numbers, manuscript):
    """Round 21. Figure 3 plotted the any-endpoint, all-pairs era-stable
    enrichment -- 13.31x, interval excluding unity, the largest effect in the
    paper -- in the same colour as the results that survive. §4.6 retracts it:
    corrected for endpoint-relevance and control drugs it is 0/142, nothing.
    A reader who skims figures saw the artefact the paper exists to warn about,
    presented as a finding.

    Guards the figure's DATA rather than its rendering, which is why
    figures.figure_3_entries exists as a separate function.
    """
    from faers_ddi import figures

    lr = numbers.get("label_reference") or {}
    if not lr.get("era_stable"):
        pytest.skip("no era-stable label-reference block")
    retracted = float(lr["era_stable"]["enrichment"])

    plotted = [float(v) for _, v, _, _ in figures.figure_3_entries(numbers)]
    assert retracted not in plotted, (
        f"Figure 3 plots {retracted}, the era-stable enrichment that §4.6 "
        f"retracts; it must not appear beside the results that survive")

    # and every point it DOES plot must be an annotation scope or the band
    labels = [lbl for lbl, _, _, _ in figures.figure_3_entries(numbers)]
    for lbl in labels:
        flat = " ".join(lbl.split()).lower()
        assert ("pooled" in flat or "no control drug" in flat
                or "plausible band" in flat), (
            f"Figure 3 point {lbl!r} is neither an annotation scope nor the "
            f"discovery band; the caption describes only those")

    # the caption must say how many points there are, and mean it
    flat_ms = " ".join(manuscript.split())
    words = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven"}
    assert f"{words[len(labels)]} points" in flat_ms, (
        f"Figure 3 plots {len(labels)} points; the caption does not say so")


def test_tables_that_declare_a_source_match_it(manuscript, numbers):
    """Round 20's structural guard: a table may declare its source, and every
    numeric cell in it is then verified against that source record.

    Two weaker designs were tried and measured first, and both were discarded:

    * membership in a corpus of every value in canonical_numbers.json plus every
      shipped CSV. That corpus renders 470,526 strings from 178,563 values and
      covers **100% of all one-decimal numbers from 0.0 to 99.9**, so the check
      cannot fail for any percentage. It passed both mutations. Decorative.
    * requiring every number in a table row to come from one flat record. Too
      strict: 46 legitimate rows combine a count, a rate, an enrichment and an
      interval that live in different parts of the canonical file.

    So provenance is declared per table, in an HTML comment the builder ignores:

        <!-- source: tier_a_results.csv tier=core policy=primary -->

    Tables without a declaration are not checked here; the count of undeclared
    tables is asserted so that this guard's coverage cannot silently shrink, and
    declarations should be added as tables are touched.
    """
    import csv as _csv, itertools as _it, re as _re

    tables = _re.findall(
        r"<!--\s*source:\s*(\S+)([^>]*)-->\s*\n+((?:^\|.*\|\s*$\n)+)",
        manuscript, _re.M)
    assert tables, "no table declares a source; the pair-level table must"

    for filename, opts, block in tables:
        filters = dict(_re.findall(r"(\w+)=(\S+)", opts))

        # A table may instead declare a path into the canonical file. The scope
        # is one sub-object, so unlike a corpus-membership check this has real
        # power -- a wrong digit will not be found in a dozen sibling values.
        if filename.startswith("canonical:"):
            node = numbers
            for key in filename.split(":", 1)[1].split("."):
                assert key in node, f"canonical path {filename} breaks at {key!r}"
                node = node[key]
            leaves = []

            def _collect(o):
                if isinstance(o, dict):
                    for v in o.values():
                        _collect(v)
                elif isinstance(o, list):
                    for v in o:
                        _collect(v)
                elif isinstance(o, (int, float)) and not isinstance(o, bool):
                    leaves.append(float(o))

            _collect(node)
            derivable = set()
            for v in leaves:
                derivable |= {f"{v:g}", f"{v:.0f}", f"{v:.1f}", f"{v:.2f}",
                              f"{100 * v:.0f}", f"{100 * v:.1f}", f"{100 * v:.2f}"}
                # Signed values render with a leading minus or a Unicode
                # en-dash in the prose, and the cell scanner reads the digits
                # without the sign. Admit the unsigned form too.
                derivable |= {f"{abs(v):g}", f"{abs(v):.1f}", f"{abs(v):.2f}"}
                if abs(v) >= 1000 and v == int(v):
                    derivable.add(f"{int(v):,}")
            lines = block.strip().split("\n")
            # The first line is the header; numbers in it are label text ("95% CI"),
            # not data. Every remaining row is checked cell by cell.
            for line in lines[1:]:
                if _re.match(r"^\|[\s\-:|]+\|$", line):
                    continue
                # Skip the first cell: it is the row label, and labels legitimately
                # contain numbers that are thresholds rather than data ("expected
                # joint rate > 5%"). The CSV branch already skips it; this branch
                # did not, and flagged a correct table.
                cells = [c for c in line.strip("|").split("|")]
                body_cells = " | ".join(cells[1:]) if len(cells) > 1 else ""
                for num in _re.findall(r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)", body_cells):
                    assert num in derivable or num.replace(",", "") in derivable, (
                        f"{num} in row {line.strip()!r} is not derivable from "
                        f"{filename}")
            continue

        path = cfg.path("tables") / filename
        assert path.exists(), f"declared source {filename} does not exist"
        with open(path) as handle:
            records = [r for r in _csv.DictReader(handle)
                       if all(r.get(k) == v for k, v in filters.items())]
        assert records, f"{filename} has no rows matching {filters}"

        for line in block.strip().split("\n"):
            if _re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            label = cells[0].lower()
            names = _re.findall(r"[a-z][a-z ]+", label)
            match = None
            for rec in records:
                drugs = f"{rec.get('drug_a','')} {rec.get('drug_b','')}".lower()
                if all(n.strip() in drugs for n in names if n.strip()):
                    match = rec
                    break
            if match is None:
                continue                      # header row, or a non-pair row
            nums = []
            for value in match.values():
                try:
                    nums.append(float(value))
                except (TypeError, ValueError):
                    pass
            derivable = set()
            for v in nums:
                derivable |= {f"{v:g}", f"{v:.0f}", f"{v:.1f}", f"{v:.2f}"}
            for a, b in _it.permutations(nums, 2):
                if b:
                    derivable |= {f"{100 * a / b:.0f}", f"{100 * a / b:.1f}",
                                  f"{100 * a / b:.2f}"}
            for cell in cells[1:]:
                for num in _re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", cell):
                    assert num in derivable, (
                        f"{label.strip()}: {num} is not derivable from the "
                        f"declared source {filename} ({filters}); the row reads "
                        f"{line.strip()}")

    total = len(_re.findall(r"((?:^\|.*\|\s*$\n){2,})", manuscript, _re.M))
    declared = len(tables)
    assert declared >= 1, "the pair-level table lost its source declaration"
    assert total - declared <= 25, (
        f"{total - declared} tables carry no source declaration; add one when "
        f"you touch a table rather than letting coverage shrink")


def test_document_defines_both_estimands(manuscript):
    """Round 19. The whole paper is a comparison of two nulls, and it defined
    neither. Both estimands were written out only in paper_a.md, so retiring it
    in round 18 deleted the formulae and left the additive null described in
    prose that omitted the cap at 1 and the conversion from risk to count. No
    guard noticed, because none asserted that a formula existed.

    Assert the structure rather than an exact string: a display equation for
    each null, the shrinkage constant, and the three risk terms.
    """
    flat = " ".join(manuscript.split())
    assert flat.count("$$") >= 4, (
        "expected display equations for both estimands; found "
        f"{flat.count('$$') // 2} display block(s)")
    for token, why in (
        (r"\log_2", "the log2 ratio defining Omega"),
        (r"E^{\mathrm{mult}}", "the multiplicative expectation"),
        (r"E^{\mathrm{add}}", "the additive expectation"),
        (r"n_{11\cdot}", "the co-report count the additive risk is applied to"),
        (r"\alpha", "the shrinkage constant"),
        (r"\min", "the cap at 1, which binds in the drug-dominant regime"),
        (r"\max", "the floor at the larger single-drug risk"),
    ):
        assert token in flat, f"manuscript does not state {why} ({token})"
    for term in ("p_A", "p_B"):
        assert term in flat, f"manuscript does not define {term}"


def test_era_stable_chance_expectation_is_the_point_estimate(manuscript, numbers):
    """Round 19. The chance expectation quoted against the 19 observed pairs
    must be the POINT estimate (rate x pairs screened), not the upper
    confidence limit.

    The pipeline stored the upper limit under a key named
    `expected_era_stable_by_chance` -- 33.2 where the expectation is 16.1. The
    prose was always right, but nothing asserted the key, so a reader or a
    future guard taking it at its name would have concluded that 19 observed
    falls far below chance. Derived here from the rate and the screen size so
    it holds whatever the key is called.
    """
    ev = numbers["era_stability_validation"]
    tested = numbers["tier_c"]["n_pairs_tested"]
    point = ev["era_stable_fpr"] * tested
    assert f"{point:.1f}" in manuscript, (
        f"manuscript must quote the point expectation {point:.1f} "
        f"({100 * ev['era_stable_fpr']:.4f}% x {tested:,})")
    upper = ev.get("expected_era_stable_at_upper_bound",
                   ev.get("expected_era_stable_by_chance"))
    if upper is not None:
        assert upper > point, "the upper limit must exceed the point estimate"
        # The upper limit may appear, but only as an interval bound.
        import re as _re
        flat = " ".join(manuscript.split())
        for sentence in _re.split(r"(?<=[.!?])\s+", flat):
            if f"{upper:.1f}" in sentence and f"{point:.1f}" not in sentence:
                assert "CI" in sentence or "interval" in sentence.lower(), (
                    f"{upper:.1f} is the upper confidence limit, not the "
                    f"expectation ({point:.1f}): {sentence[:160]}")


def test_manuscript_reports_the_independent_annotation(manuscript, numbers):
    """Pooled enrichment is circular; the de-circularised figure must be given
    and must be presented as the honest one."""
    ind = numbers["independent_annotation"]
    assert f"{ind['enrichment']:.2f}" in manuscript
    assert f"{ind['enrichment_ci'][0]:.2f}" in manuscript
    assert f"{ind['enrichment_ci'][1]:.2f}" in manuscript
    lowered = manuscript.lower()
    assert "not independent of the control set" in lowered
    assert "indistinguishable from unity" in lowered


def test_manuscript_reports_confidence_intervals(manuscript, numbers):
    """No bare point estimates for the headline proportions."""
    a = numbers["tier_a"]
    assert f"{100 * a['recovered_powered_ci'][0]:.0f}" in manuscript
    assert f"{100 * a['recovered_powered_ci'][1]:.0f}" in manuscript
    for band in ("plausible", "known_pair"):
        ci = numbers["tier_c"]["bands_pooled"][band]["enrichment_ci"]
        assert f"{ci[0]:.2f}" in manuscript and f"{ci[1]:.2f}" in manuscript


def test_manuscript_does_not_use_binomial_p_for_inference(manuscript):
    """Pair outcomes are dependent; the permutation test is the valid one."""
    lowered = manuscript.lower()
    assert "permutation" in lowered
    assert "binomial tests are **not** used for inference" in lowered


def test_manuscript_has_a_related_work_section(manuscript):
    assert "## 2. Related work" in manuscript
    for author in ("Norén", "Thakrar", "Rothman", "Banda", "Phansalkar"):
        assert author in manuscript, author
    # Citations are unverified; that must be stated rather than implied.
    # Every citation must now carry a verified identifier, and the one
    # exception (a paywalled primary, corroborated by two secondary sources)
    # must be stated rather than glossed.
    assert "Verification status" in manuscript
    assert "## 8. References" in manuscript
    for identifier in ("PMID 18344185", "PMID 27193236", "PMID 22539083",
                       "PMID 22422992", "doi:10.1002/pds.677",
                       "doi:10.1007/s002280050466", "doi:10.1002/sim.3247"):
        assert identifier in manuscript, identifier
    assert "paywalled and has not been read" in manuscript
    # A citation that could not be verified must be removed, not softened.
    assert "Khaleel" not in manuscript


def test_reference_list_is_complete_and_ordered(manuscript):
    references = manuscript.split("## 8. References")[1]
    for author in ("Bate A", "Banda JM", "DuMouchel W", "Evans SJW",
                   "Fusaroli M", "Norén GN", "Phansalkar S", "Rothman KJ",
                   "Tatonetti NP", "Thakrar BT"):
        assert author in references, author
    # Every author cited in the body must appear in the reference list.
    body = manuscript.split("## 8. References")[0]
    for surname in ("Norén", "Thakrar", "Rothman", "Banda", "Phansalkar",
                    "Tatonetti", "Fusaroli", "DuMouchel", "Evans", "Bate"):
        if surname in body:
            assert surname in references, f"{surname} cited but not listed"


def test_diana_coverage_benchmark_is_reported(manuscript):
    """An independent external check on ingredient resolution: DiAna reports
    98.94% on 74.1M entries; this pipeline 98.0% on 74.0M."""
    assert "98.94" in manuscript
    assert "74,143,411" in manuscript


def test_figures_exist_and_are_referenced(manuscript):
    figures = sorted((cfg.PROJECT_ROOT / "results" / "figures").glob("*.png"))
    assert len(figures) >= 5, "at least five figures required"
    for figure in figures:
        assert figure.stem in manuscript, f"{figure.stem} not referenced"


def test_abstract_case_count_matches_the_analysis_population(manuscript, numbers):
    """The abstract previously gave the deduplication output as if it were the
    analysis population, a 19,005-case discrepancy."""
    abstract = manuscript.split("## 1. Introduction")[0]
    assert f"{numbers['n_cases']:,}" in abstract
    assert f"{numbers['n_event_cases']:,}" in abstract


def test_fusidic_acid_is_not_presented_as_validation(manuscript):
    """It sits in the `plausible` band, which the paper shows is not enriched.
    Presenting it as validation contradicts the paper's own result."""
    lowered = manuscript.lower()
    if "fusidic" in lowered:
        assert "rediscovers established interactions it was never given" not in lowered


def test_manuscript_discloses_the_estimand_change(manuscript):
    """Non-negotiable: the switch away from the pre-specified measure must be
    in the abstract, not only the methods."""
    abstract = manuscript.split("## 1. Introduction")[0].lower()
    assert "pre-specified" in abstract
    assert "additive" in abstract
    assert "failed" in abstract


def test_manuscript_states_the_negative_result(manuscript):
    lowered = manuscript.lower()
    assert "no enrichment" in lowered
    assert "not demonstrate" in lowered or "does not" in lowered


# --- the readme -------------------------------------------------------------


def test_readme_agrees_with_canonical_tier_a(readme, numbers):
    a = numbers["tier_a"]
    assert f"{a['recovered_powered']}/{a['n_powered']}" in readme


def test_readme_agrees_with_canonical_fpr(readme, numbers):
    rate = numbers["tier_b"]["strata"]["all"]["fpr_additive"]
    assert f"{100 * rate:.1f}%" in readme


def test_readme_reports_the_era_stability_negative_result(readme, numbers):
    """The README previously promoted era-stability enrichment as a headline.
    Validation against negative controls showed the count is not distinguishable
    from chance, so the README must report that instead."""
    ev = numbers["era_stability_validation"]
    assert f"{100 * ev['era_stable_fpr']:.3f}%" in readme
    assert str(ev["observed_era_stable"]) in readme
    lowered = readme.lower()
    assert "not distinguishable from" in lowered
    assert "negative result" in lowered


# --- the independent reference and the alpha sensitivity -------------------


def test_independent_reference_exists_and_is_sensitive(numbers):
    """An annotation the authors did not write. Useless if it misses the known
    interactions, so its sensitivity on the control set is asserted."""
    lr = numbers.get("label_reference")
    assert lr, "run faers_ddi.label_reference then faers_ddi.run_analysis"
    assert lr["n_documented_pairs"] > 500
    assert lr["positive_controls_captured"] == lr["n_positive_controls"]


def test_manuscript_reports_the_independent_reference(manuscript, numbers):
    lr = numbers["label_reference"]
    assert f"{lr['n_documented_pairs']:,}" in manuscript
    assert f"{lr['positive_controls_captured']}/{lr['n_positive_controls']}" in manuscript
    for scope in ("pooled", "excluding_control_drugs"):
        assert f"{lr[scope]['enrichment']}" in manuscript
    lowered = manuscript.lower()
    assert "independent of the authors but not of faers" in lowered or \
           "independent of the authors, not of faers" in lowered or \
           "not independent of faers" in lowered


def test_negative_result_holds_under_both_annotations(numbers):
    """The paper's central negative claim must not rest on one reference."""
    author = numbers["independent_annotation"]["enrichment_ci"]
    label = numbers["label_reference"]["excluding_control_drugs"]["enrichment_ci"]
    assert author[0] <= 1.0 <= author[1], "author-curated CI must span unity"
    assert label[0] <= 1.0 <= label[1], "label-based CI must span unity"


def test_alpha_sensitivity_is_reported_and_conclusions_are_stable(manuscript, numbers):
    """alpha could not be source-verified; the paper must show it does not
    drive any conclusion."""
    rows = numbers["alpha_sensitivity"]
    assert len(rows) >= 5
    alphas = [r["alpha"] for r in rows]
    assert max(alphas) / min(alphas) >= 20, "must span at least a 20-fold range"

    recovered = [r["positive_controls_recovered"] for r in rows]
    assert max(recovered) - min(recovered) <= 3, "recovery must not swing wildly"
    signals = [r["n_signalled"] for r in rows]
    assert (max(signals) - min(signals)) / min(signals) < 0.15

    assert "§4.8" in manuscript or "4.8" in manuscript
    for row in rows:
        assert f"{row['alpha']}" in manuscript


def test_alpha_sensitivity_reproduces_the_main_run_at_the_adopted_value(numbers):
    """A self-consistency check: at alpha = 0.5 the sensitivity analysis must
    reproduce the headline threshold and signal count. It did not initially --
    the loop was silently scoring one era bin."""
    adopted = [r for r in numbers["alpha_sensitivity"] if r["alpha"] == 0.5]
    assert adopted, "alpha = 0.5 must be among the sensitivity values"
    row = adopted[0]
    assert row["n_signalled"] == numbers["tier_c"]["n_signalled"]
    assert abs(row["calibrated_threshold"]
               - numbers["tier_b"]["calibrated_threshold"]) < 0.01


def test_endpoint_specific_reference_is_used(numbers):
    """A label documents that two drugs interact, not that they cause THIS
    event. 82% of name-matched pairs are documented for another endpoint."""
    e = numbers.get("endpoint_specific_reference")
    assert e, "run faers_ddi.label_reference then faers_ddi.run_analysis"
    assert e["positive_controls_captured"] == 16, "must not lose sensitivity"
    assert e["n_pairs"] < numbers["label_reference"]["n_documented_pairs"], \
        "endpoint filter must be a strict subset"


def test_enrichment_is_reported_stratified_on_power(numbers):
    """Documented pairs are co-reported ~3x more often, and co-report count
    drives power, so the crude ratio confounds validity with power."""
    e = numbers["endpoint_specific_reference"]
    for scope in ("all_pairs", "excluding_control_drugs"):
        assert e[scope]["stratified_enrichment"] is not None


def test_negative_result_survives_every_correction(numbers):
    """The central claim must hold under: the author list, an independent
    reference, an endpoint-specific reference, and power stratification."""
    author = numbers["independent_annotation"]["enrichment_ci"]
    assert author[0] <= 1.0 <= author[1]
    label = numbers["label_reference"]["excluding_control_drugs"]["enrichment_ci"]
    assert label[0] <= 1.0 <= label[1]
    endpoint = numbers["endpoint_specific_reference"]["excluding_control_drugs"]
    assert endpoint["crude_enrichment_ci"][0] <= 1.0 <= endpoint["crude_enrichment_ci"][1]
    assert 0.7 <= endpoint["stratified_enrichment"] <= 1.4, \
        "stratified enrichment among non-control pairs must be near unity"


def test_manuscript_reports_the_endpoint_and_power_corrections(manuscript, numbers):
    e = numbers["endpoint_specific_reference"]
    assert f"{e['n_pairs']}" in manuscript
    assert f"{e['excluding_control_drugs']['stratified_enrichment']}" in manuscript
    lowered = manuscript.lower()
    assert "unrelated endpoint" in lowered
    assert "mantel-haenszel" in lowered or "stratif" in lowered
    assert "omeprazole + warfarin" in lowered


def test_manuscript_states_the_negative_result_as_a_bound(manuscript, numbers):
    """142 documented non-control pairs gives 57% power at RR 2.0. The claim
    that can be supported is an upper bound, not absence."""
    e = numbers["endpoint_specific_reference"]["excluding_control_drugs"]
    lowered = manuscript.lower()
    assert "power" in lowered
    assert f"{e['crude_enrichment_ci'][1]}" in manuscript
    assert "upper bound" in lowered or "no enrichment above" in lowered


def test_manuscript_discloses_selection_on_the_outcome(manuscript):
    """Screened drugs are chosen by co-reporting WITH the event."""
    lowered = manuscript.lower()
    assert "selected on the outcome" in lowered or \
           "selection on the dependent variable" in lowered


# --- sensitivity analyses ---------------------------------------------------


@pytest.fixture(scope="module")
def sensitivity(numbers) -> dict:
    s = numbers.get("sensitivity")
    if not s:
        pytest.skip("run `python -m faers_ddi.sensitivity` first")
    return s


def test_negative_result_survives_the_power_increase(sensitivity):
    """The bound rested on 142 documented pairs. Extending the reference to 800
    drugs raises it to ~440; the conclusion must not flip."""
    sizes = sensitivity["screen_size"]
    assert len(sizes) >= 3
    assert sizes[-1]["documented_tested"] > 2 * sizes[0]["documented_tested"]
    for row in sizes:
        assert row["stratified_excludes_unity"] is False, (
            f"top-{row['n_drugs']} stratified interval excludes unity")


def test_cluster_bootstrap_is_wider_than_the_pairwise_interval(sensitivity):
    """Pairs share drugs, so the pairwise interval is anticonservative. If the
    bootstrap were ever narrower, the clustering would not be working."""
    for row in sensitivity["screen_size"]:
        pairwise = row["enrichment_ci_pairwise_ANTICONSERVATIVE"]
        cluster = row["stratified_ci_cluster_bootstrap"]
        assert (cluster[1] - cluster[0]) > (pairwise[1] - pairwise[0]) * 0.8


def test_outcome_based_selection_does_not_drive_the_result(sensitivity):
    both = sensitivity["drug_selection"]
    for key in ("by_event_coreporting", "by_total_volume"):
        ci = both[key]["stratified_ci_cluster_bootstrap"]
        assert ci[0] <= 1.0 <= ci[1], f"{key} interval excludes unity"


def test_era_stable_count_is_an_artefact_of_bin_choice(sensitivity):
    counts = [r["n_stable"] for r in sensitivity["era_bins"]]
    assert max(counts) > 5 * min(counts), (
        "if the count were robust to bin choice the era result would stand")


def test_ingredient_resolution_accuracy_is_bounded(sensitivity):
    ia = sensitivity["ingredient_accuracy"]
    assert ia["names_examined"] > 10_000
    assert ia["modal_agreement"] > 0.95


def test_demographic_strata_are_reported(sensitivity, manuscript):
    strata = sensitivity["demographic_strata"]
    assert {r["stratum"] for r in strata} == {"female", "male"}
    assert "demographic strata" in manuscript.lower()


def test_manuscript_reports_the_aeolus_benchmark(manuscript, audit):
    """Deduplication benchmarked against published practice.

    The previous version of this test asserted that two hardcoded literals
    appeared in prose containing the same two literals -- it would have passed
    with both wrong, and the count was not derivable from anything shipped. It
    now checks the figure the pipeline actually produces.
    """
    bench = audit["provenance"]["aeolus_benchmark"]
    assert bench["window"] == "2004q1-2015q2"
    assert f"{bench['this_pipeline_cases']:,}" in manuscript
    assert f"{bench['aeolus_published_cases']:,}" in manuscript
    # A benchmark is only a benchmark if the two are close.
    assert abs(bench["difference_fraction"]) < 0.15


def test_quoted_pipeline_statistics_have_provenance(manuscript, audit):
    """The availability statement claims every quoted figure is generated and
    asserted. Eleven of eighteen checked during review were absent from the
    canonical file; these are the ones that had to be persisted for the claim
    to hold."""
    p = audit["provenance"]
    for key in ("raw_demo_rows", "pt_vocabulary_size",
                "polypharmacy_excluded_cases", "hospital_context_excluded_cases",
                "hospitalisation_outcome_reports", "cross_era_bridge_identifiers"):
        assert key in p, f"provenance missing {key}"
        assert f"{p[key]:,}" in manuscript, (
            f"{key} = {p[key]:,} is persisted but not quoted in the manuscript")
    # Recomputing this surfaced 189.2 in the prose against 189.54 in the table.
    named = p["simvastatin_amiodarone"]
    assert f"{named['expected_multiplicative']:.1f}" in manuscript
    assert named["source"].endswith("tier_a_results.csv")
    assert "AEOLUS" in manuscript


def test_manuscript_reports_alpha_corroboration(manuscript):
    lowered = manuscript.lower()
    assert "corroborated by secondary sources" in lowered
    assert "paywalled" in lowered


# --- round-4 additions ------------------------------------------------------


def test_sensitivity_section_is_marked_post_hoc(manuscript):
    """None of §4.9 was pre-planned; a reader must be told."""
    lowered = manuscript.lower()
    assert "these analyses are post-hoc" in lowered
    assert "no correction has been applied" in lowered


def test_independent_control_set_recovery_is_reported(manuscript, numbers):
    """86% recovery is on author-chosen controls. The label-selected estimate is
    much lower and must appear, in Results rather than Limitations."""
    ipc = numbers["sensitivity"]["independent_positive_controls"]
    assert ipc["n_pairs"] > 100
    assert str(ipc["n_pairs"]) in manuscript
    assert str(ipc["recovered_additive"]) in manuscript
    results = manuscript.split("## 5. Discussion")[0]
    assert "controls the authors did not choose" in results.lower()
    # Superseded by a stronger statement: the two figures bracket the
    # sensitivity rather than either being it.
    lowered = manuscript.lower()
    assert ("neither 86% nor 12%" in lowered
            or "neither figure is the sensitivity" in lowered)


def test_generalization_to_a_second_event_is_reported(manuscript, numbers):
    g = numbers.get("generalization")
    assert g, "run `python -m faers_ddi.generalization` first"
    tq = g["torsade_qt"]
    assert tq["recovered_additive"] > tq["recovered_multiplicative"], (
        "the additive null must outperform on the replication event too")
    corr = tq["omega_vs_marginal_product"]
    assert corr["p_value"] < 0.05, "the correlation must replicate"
    assert f"{corr['r']:.2f}" in manuscript
    assert "torsade" in manuscript.lower()


def test_conditional_claim_is_not_overstated(manuscript):
    """The phenomenon replicates; the CONDITION has no negative case."""
    lowered = manuscript.lower()
    assert "remains a hypothesis" in lowered
    assert "condition does not yet have a negative case" in lowered or \
           "negative case" in lowered


def test_figures_have_standalone_captions(manuscript):
    figures = sorted((cfg.PROJECT_ROOT / "results" / "figures").glob("*.png"))
    section = manuscript.split("## Figures")[1]
    for figure in figures:
        assert figure.name in section, figure.name
    # A caption is more than a filename and a clause.
    assert len(section) > 2000, "captions too terse for standalone reading"


def test_computational_environment_is_specified(manuscript):
    lowered = manuscript.lower()
    for token in ("python 3.14", "duckdb", "memory", "no gpu"):
        assert token in lowered, token


def test_recovery_gap_is_explained_not_hedged(manuscript, numbers):
    """The 86%-vs-12% gap was first written as two unresolved readings. It is
    measurable: the gap is not power, it is the event rate among co-reports."""
    lowered = manuscript.lower()
    assert "not statistical power" in lowered
    assert "class warning" in lowered or "class* warning" in lowered
    # Sourced from audit.provenance rather than hardcoded: recomputing this
    # showed the previously quoted 137.8x was stale.
    gap = numbers["audit"]["provenance"]["recovery_gap"]
    assert str(gap["author_selected"]["vs_baseline"]) in manuscript
    # The claim is that the gap is the event rate, not power: an order of
    # magnitude separates the two control sets (observed ratio ~40x).
    assert gap["author_selected"]["vs_baseline"] > 10 * gap["label_selected"]["vs_baseline"]
    assert gap["label_selected"]["top_decile_vs_baseline"] < 1.0, (
        "the top decile of label-documented pairs must sit below baseline")
    assert "neither 86% nor 12%" in lowered or "neither figure is the sensitivity" in lowered


def test_residual_duplication_is_bounded(manuscript, numbers):
    rd = numbers["sensitivity"]["residual_near_duplicates"]
    assert rd["cases_removable_by_fuzzy_rule"] > 0
    assert rd["share_of_event_cases"] < 0.05, "residual must be small to be dismissible"
    assert str(rd["cases_removable_by_fuzzy_rule"]) in manuscript


def test_external_validation_limit_is_evidence_based(manuscript):
    """'No access' was an assumption. The public VigiBase interface exposes
    single-drug counts only and cannot express a drug pair at all."""
    lowered = manuscript.lower()
    assert "vigiaccess" in lowered
    assert "no facility for drug pairs" in lowered
    assert "uppsala monitoring centre" in lowered


# --- round 7: the inference layer -------------------------------------------
# Round 7 of review attacked the statistics rather than the pipeline. Four of
# its findings had slipped past the existing tests because those tests asserted
# PROPERTIES ("the bound must still include unity") rather than the printed
# values, so a table regenerated by an older run passed unnoticed. These assert
# the values.

@pytest.fixture(scope="module")
def audit(numbers):
    a = numbers.get("audit")
    if not a:
        pytest.skip("run `python -m faers_ddi.audit` first")
    return a


def test_screen_size_table_values_match_canonical(manuscript, sensitivity):
    """The manuscript's screen-size table was stale for a full round of review:
    53,396/320 against a canonical 53,229/321. Assert every printed cell."""
    for row in sensitivity["screen_size"]:
        assert f"{row['n_pairs']:,}" in manuscript, (
            f"top-{row['n_drugs']} pair count {row['n_pairs']:,} not in manuscript")
        assert str(row["documented_tested"]) in manuscript
        lo, hi = row["stratified_ci_cluster_bootstrap"]
        assert f"{lo}" in manuscript and f"{hi}" in manuscript, (
            f"top-{row['n_drugs']} cluster interval ({lo}-{hi}) not in manuscript")


def test_the_marginal_gradient_is_reported_for_both_nulls(manuscript, numbers, audit):
    """r(Omega, marginals) was reported for the multiplicative null alone and
    read as diagnostic of it. The additive null shows the same gradient."""
    ic = audit["induced_correlation"]
    assert ic["both_nulls_show_the_gradient"]
    # The additive gradient is at least as strong, so it cannot separate them.
    assert ic["r_omega_additive"] <= ic["r_omega_multiplicative"] + 0.05
    assert "-0.65" in manuscript or "−0.65" in manuscript, "Omega_add gradient absent"
    assert "+0.12" in manuscript, "flat observed-rate correlation absent"
    # And the artifact check must be reported, not just the point estimate.
    assert "induced" in manuscript.lower()


def test_the_gradient_survives_the_artifact_check(audit):
    """Being partly mechanical is not the same as being an artifact. The
    simulated null must be centred near zero and exclude the observed value,
    otherwise the manuscript may not call the gradient real."""
    ic = audit["induced_correlation"]
    for null in (ic["null_r_multiplicative"], ic["null_r_additive"]):
        assert abs(null["median"]) < 0.15, "induced null should centre near zero"
    assert ic["multiplicative_exceeds_null"] and ic["additive_exceeds_null"]


def test_threshold_is_validated_out_of_sample(manuscript, audit):
    """A quantile of the pool it is measured on returns the target by
    construction. The held-out rate is the measurement."""
    hc = audit["heldout_calibration"]
    assert hc["n_splits"] >= 100
    lo, hi = hc["heldout_fpr_ci"]
    assert lo <= hc["target_fpr"] <= hi, "held-out FPR interval must cover the target"
    assert f"{100 * hc['heldout_fpr_mean']:.2f}%" in manuscript


def test_expected_by_chance_uses_the_heldout_rate(manuscript, numbers, audit):
    """869 was the nominal 5% restated. The reported figure must come from the
    measured rate and must carry an interval."""
    expected = round(audit["heldout_calibration"]["heldout_fpr_mean"]
                     * numbers["tier_c"]["n_pairs_tested"])
    assert f"{expected:,}" in manuscript or str(expected) in manuscript


def test_reference_blindness_is_quantified(manuscript, audit):
    """17.2% of ingredients have no FDA label at all, and the gap is
    concentrated on the endpoint's own drug classes."""
    rc = audit["reference_coverage"]
    assert rc["share_without_label"] > 0
    assert rc["endpoint_relevant_without_label"], "expected unlabelled implicated drugs"
    assert f"{100 * rc['share_without_label']:.1f}%" in manuscript
    # Derived from the counts, not from the stored share. Round 19: the
    # stored share was rounded to 4dp, so formatting it gave 9.8% while
    # 1712/17375 = 9.853% -> 9.9%. A guard that re-rounds the same rounded
    # value cannot catch a rounding error.
    exact = 100 * rc["pairs_touching_an_unlabelled_drug"] / rc["pairs_total"]
    assert f"{exact:.1f}%" in manuscript, (
        f"manuscript must report {exact:.1f}% "
        f"({rc['pairs_touching_an_unlabelled_drug']}/{rc['pairs_total']})")
    for drug in ("CERIVASTATIN", "FUSIDIC ACID"):
        assert drug.lower() in manuscript.lower()


def test_negative_result_survives_the_coverage_correction(manuscript, audit):
    """Restricting to pairs whose two labels both exist must not flip it."""
    rc = audit["reference_coverage"]
    lo, hi = rc["stratified_ci_cluster_bootstrap"]
    assert lo <= 1.0 <= hi, "coverage-restricted interval excludes unity"
    assert str(rc["stratified"]) in manuscript


def test_multiplicity_is_addressed(manuscript, audit):
    """17,375 tests with no correction. BH must be reported, and the shrinkage
    rule must be the conservative one for the conclusion to be unaffected."""
    f = audit["fdr"]
    assert f["overlap_with_shrinkage_signals"] == f["n_signalled_by_shrinkage_threshold"], (
        "some shrinkage signals are not BH discoveries; the rules disagree")
    assert f["n_discoveries"] >= f["n_signalled_by_shrinkage_threshold"]
    assert f"{f['n_discoveries']:,}" in manuscript
    assert "benjamini" in manuscript.lower()


def test_both_nulls_scored_at_the_same_threshold(manuscript, sensitivity):
    """The held-out control table compared Omega_025>0 against Omega_add,025 >
    +0.436 and printed it beside a row where both are at 0."""
    ipc = sensitivity["independent_positive_controls"]
    for key in ("at_threshold_zero", "at_calibrated_threshold"):
        arm = ipc[key]
        assert str(arm["additive"]) in manuscript
        assert str(arm["multiplicative"]) in manuscript
        assert arm["additive"] > arm["multiplicative"], (
            f"{key}: direction must hold at a matched threshold")


def test_polypharmacy_cap_choice_is_disclosed(manuscript, audit):
    """20 was chosen because it improved recovery AND the false-positive rate,
    i.e. on the evaluation set. The sweep must be published."""
    sweep = {r["cap"]: r for r in audit["cap_sweep"]}
    assert None in sweep, "the uncapped arm must genuinely be uncapped"
    assert sweep[None]["n_cases"] > sweep[20]["n_cases"], (
        "uncapped must retain more cases than cap=20; None means 'use config'")
    assert sweep[20]["recovered_additive"] > sweep[None]["recovered_additive"], (
        "the cap is only justified if it improves recovery")
    for cap in (10, 20, None):
        assert f"{sweep[cap]['n_cases']:,}" in manuscript


def test_era_stable_composition_uses_the_endpoint_specific_reference(manuscript, numbers):
    """The one surviving positive claim ran on the any-endpoint reference that
    section 4.5 discredits, unstratified. Under the endpoint-specific reference
    with control drugs removed, no era-stable pair is documented."""
    e = numbers["endpoint_specific_reference"]
    assert "era_stable" in e, "endpoint-specific era-stable scope missing"
    assert e["era_stable_excluding_control_drugs"]["documented_signalled"] == 0
    assert "0/142" in manuscript


def test_the_top_ranked_pair_is_discussed(manuscript, audit):
    """The screen's highest-event-rate pair outranks every positive control and
    was absent from the manuscript entirely."""
    top = audit["top_ranked"]["top"][0]
    best_control = audit["top_ranked"]["best_positive_control"]
    assert top["event_rate"] > best_control["event_rate"]
    name = top["pair"].replace("+", " + ").lower()
    assert name in manuscript.lower(), f"{top['pair']} not discussed"
    assert f"{100 * top['event_rate']:.1f}%" in manuscript


def test_torsade_pt_list_is_endpoint_specific(numbers):
    """The replication used a PT list including CARDIAC ARREST, tripling the
    event rate relative to the event it was replicating."""
    t = numbers["generalization"]["torsade_qt"]
    assert "CARDIAC ARREST" not in t["pts_used"]
    assert abs(t["event_rate"] - numbers["event_rate"]) < 0.002, (
        "curated replication event should sit near the primary event rate")
    assert t["recovered_additive"] > t["recovered_multiplicative"]


def test_no_invalid_statistic_ships_in_the_canonical_artifact(numbers):
    """A binomial p-value assuming pair independence was shipped under an
    _INVALID suffix. Labelling it did not stop it being quotable."""
    assert "INVALID" not in json.dumps(numbers)


def test_typeset_manuscript_is_generated_not_maintained(manuscript):
    """paper/manuscript.tex must be derivable from manuscript.md.

    A hand-maintained .tex beside the .md is the same defect as
    tier_a_results.csv being written by a different run than
    canonical_numbers.json: two artifacts, one truth, free to drift.
    """
    tex = cfg.PROJECT_ROOT / "paper" / "manuscript.tex"
    if not tex.exists():
        pytest.skip("run `python paper/build.py` first")
    header = tex.read_text(errors="ignore")[:2000]
    assert "generated from" in header.lower(), (
        "manuscript.tex must carry the generated-file banner from preamble.tex")
    # Every figure the markdown captions must be embedded in the typeset copy.
    body = tex.read_text(errors="ignore")
    for name in re.findall(r"`(figure\d+_[a-z_0-9]+\.png)`", manuscript):
        assert f"includegraphics" in body and name in body, f"{name} not embedded"


def test_all_pipeline_stages_have_run(numbers):
    """run_analysis rewrites canonical_numbers.json wholesale.

    Re-running it alone silently drops the `sensitivity`, `generalization` and
    `audit` blocks, and the tests that read them then SKIP rather than fail —
    so a partial pipeline looks green. This turns that into a failure.
    """
    stages = set(numbers.get("stages", []))
    missing = {"run_analysis", "sensitivity", "generalization", "audit"} - stages
    assert not missing, (
        f"stages not re-run after run_analysis: {sorted(missing)}. "
        f"Run them in that order; see README.")


# --- round 8: control sets, specification space, confounder instruments ------


def test_specification_grid_is_published(manuscript, numbers):
    """Four tier x role-policy arms were computed and one was reported. The
    unreported broad/sensitivity arm erases the additive advantage entirely."""
    grid = numbers.get("specification_grid")
    assert grid, "run `python -m faers_ddi.run_analysis` first"
    assert grid["n_arms"] == 4
    assert sum(a["pre_specified"] for a in grid["arms"]) == 1, "exactly one arm is pre-specified"
    # Row-level, not substring-level: "6/16" also occurs inside "16/16", so a
    # bare `in manuscript` check passes even with the row deleted.
    lines = [" ".join(line.split()) for line in manuscript.splitlines()]
    for arm in grid["arms"]:
        wanted = (arm["tier"], arm["policy"],
                  f"{arm['recovered_additive']}/{arm['n_controls']}",
                  f"{arm['recovered_multiplicative']}/{arm['n_controls']}")
        assert any(all(token in line for token in wanted) for line in lines), (
            f"no table row reports tier={arm['tier']} policy={arm['policy']} "
            f"({wanted[2]} additive, {wanted[3]} multiplicative)")
    # If any arm nullifies the contrast the manuscript must say so, not bury it.
    if grid["min_additive_advantage"] <= 0:
        lowered = manuscript.lower()
        assert "advantage disappears" in lowered or "null in the fourth" in lowered


def test_tier_a_interval_respects_control_clustering(manuscript, numbers):
    """16 controls are 5 victim drugs; simvastatin is in 7. A binomial interval
    on 14 'independent' trials is too narrow."""
    c = numbers["tier_a"]["recovered_powered_clustered"]
    assert c["n_clusters"] < c["n"], "controls must be clustered by victim drug"
    naive = c["naive_binomial_ci_ANTICONSERVATIVE"]
    cluster = c["cluster_ci"]
    assert (cluster[1] - cluster[0]) > (naive[1] - naive[0]), (
        "the clustered interval must be wider than the naive one")
    assert f"{100 * cluster[0]:.0f}" in manuscript
    assert "resampling the victim drug" in manuscript.lower()


def test_positive_controls_are_verified_not_asserted(numbers):
    """Every control carried citation_status 'to_verify' and never was."""
    v = numbers.get("positive_control_verification")
    assert v, "run `python -m faers_ddi.verify_controls` first"
    assert v["n_endpoint_relevant"] == v["n_controls"], (
        "every control must be label-documented for THIS endpoint")
    assert "to_verify" not in json.dumps(v["summary"])
    controls = cfg.PROJECT_ROOT / "config" / "positive_controls.csv"
    assert "to_verify" not in controls.read_text(), (
        "citation_status must record the outcome of the check, not the intent")


def test_inpatient_confounding_uses_the_reported_outcome(manuscript, audit):
    """A 30-drug proxy touching 1.4% of cases cannot exclude a confounder.
    FAERS records hospitalisation directly and it was already parsed."""
    strata = audit["inpatient_stratification"]["strata"]
    assert len(strata) == 2
    smaller = min(s["n_cases"] for s in strata)
    assert smaller > 1_000_000, "both strata must be large enough to be informative"
    # The result must reproduce in BOTH strata, not just overall.
    for s in strata:
        assert s["bands"]["plausible"]["enrichment"] < 1.0, (
            f"plausible band not below unity in {s['stratum']}")
        assert f"{s['n_cases']:,}" in manuscript


def test_band_enrichment_is_adjusted_for_marginal_strength(manuscript, audit):
    """Section 4.1 proves marginal strength drives the expectation; the bands
    differ on it by 1.3 units and were compared unadjusted."""
    b = audit["band_by_marginal_strength"]
    medians = b["median_strength_by_band"]
    assert medians["plausible"] > medians["unsupported"], (
        "bands must actually differ on the covariate for this to be needed")
    plausible = b["plausible"]
    assert plausible["stratified_on_marginal_strength"] < 1.0
    assert str(plausible["stratified_on_marginal_strength"]) in manuscript
    for bound in plausible["stratified_ci_cluster_bootstrap"]:
        assert str(bound) in manuscript


def test_anaphylaxis_arm_is_labelled_design_invalid(manuscript, numbers):
    """It was reported as underpowered. It is invalid: no interaction exists in
    the control pairs, so no sample size would help."""
    arm = numbers["generalization"]["anaphylaxis"]
    assert arm.get("design_valid") is False
    lowered = manuscript.lower()
    assert "invalid by construction" in lowered or "design-invalid" in lowered
    assert "at any sample size" in lowered or "no additional data" in lowered
    # The fixed-dose combination product must be gone from the control set.
    gen = (cfg.PROJECT_ROOT / "src" / "faers_ddi" / "generalization.py").read_text()
    controls = gen.split('"anaphylaxis"')[1].split("}")[0]
    assert "CLAVULANATE" not in controls, (
        "co-amoxiclav is a combination product, not a drug-drug interaction")


def test_era_filter_semantics_are_documented(manuscript):
    """Each third-sized era bin is scored against the full-data threshold, so
    the filter selects on co-report count as well as temporal persistence."""
    lowered = manuscript.lower()
    assert "third-power data" in lowered or "third of the cases" in lowered
    assert "selects on co-report count" in lowered


def test_inpatient_proxy_is_not_presented_as_exclusionary(manuscript):
    """1.4% of cases removed; the earlier text read as if that settled it, and
    as if 275,205 were the analysed set rather than the excluded one."""
    lowered = manuscript.lower()
    assert "removes 275,205 cases" in lowered or "removes\n275,205 cases" in lowered
    assert "it is not evidence of that" in lowered


# --- the restructured paper (RETIRED) ---------------------------------------
# paper.md was retired in round 11 and moved to paper/archive/. Its tests were
# removed rather than left to skip: four permanently-skipping tests are four
# lines of green that assert nothing, and this suite has twice been fooled by
# guards that did not guard. `test_retired_documents_are_not_built_and_are_
# labelled` covers what remains checkable.
#
# Removed with the document: test_paper_headline_numbers_match_canonical, test_paper_reports_the_specification_grid, test_paper_keeps_the_clustered_interval_and_negative_findings, test_paper_marks_missing_information_rather_than_inventing_it


# --- the conference papers, retired in round 18 ------------------------------
# paper_a (estimand) and paper_b (evaluation) were split out of manuscript.md
# and merged back into it. Their claims live on below, rescoped to the
# manuscript; the documents themselves are in paper/archive/.


def _read(path):
    if not path.exists():
        pytest.skip(f"{path.name} not present")
    return path.read_text().replace("−", "-")


# --- round 18: the two conference papers were merged back into the manuscript.
# Every assertion below used to be scoped to paper_a.md or paper_b.md. The
# documents are retired, but the CLAIMS are not -- they moved into the
# manuscript, so the guards move with them rather than being deleted. A guard
# deleted alongside the document it happened to be pointed at is how a
# correction gets lost.


def test_calibration_numbers_match_canonical(manuscript, numbers):
    a, b = numbers["tier_a"], numbers["tier_b"]
    for value in (f"{numbers['n_cases']:,}", f"{numbers['n_event_cases']:,}",
                  f"{a['recovered_powered']}/{a['n_powered']}",
                  f"{100 * b['strata']['all']['fpr_additive']:.1f}%",
                  f"{b['n_pairs']:,}"):
        assert value in manuscript, f"{value} missing from manuscript.md"
    assert f"{a['recovered_additive']} of {a['n_controls']}" in manuscript or \
           f"{a['recovered_additive']}/{a['n_controls']}" in manuscript
    lo, hi = a["recovered_powered_clustered"]["cluster_ci"]
    assert f"{100 * lo:.0f}" in manuscript and f"{100 * hi:.0f}" in manuscript


def test_evaluation_numbers_match_canonical(manuscript, numbers):
    c = numbers["tier_c"]
    ind = numbers["independent_annotation"]
    for value in (f"{c['n_pairs_tested']:,}", f"{c['n_signalled']:,}",
                  f"{numbers['n_cases']:,}", f"{ind['enrichment']:.2f}"):
        assert value in manuscript, f"{value} missing from manuscript.md"
    assert f"{c['bands_pooled']['known_pair']['enrichment']:.2f}" in manuscript


def test_document_carries_the_specification_grid(manuscript, numbers):
    """The arm that nullifies the contrast belongs in the document that makes
    the contrast. Previously asserted separately of paper_a and paper_b."""
    lines = [" ".join(line.split()) for line in manuscript.splitlines()]
    for arm in numbers["specification_grid"]["arms"]:
        wanted = (arm["tier"], arm["policy"],
                  f"{arm['recovered_additive']}/{arm['n_controls']}")
        assert any(all(tok in line for tok in wanted) for line in lines), (
            f"manuscript.md omits arm {arm['tier']}/{arm['policy']}")


def test_document_keeps_the_findings_that_qualify_it(manuscript):
    """Union of what paper_a and paper_b were each required to keep."""
    lowered = manuscript.lower()
    for phrase in ("not robust to widening", "invalid by construction",
                   "was incorrect", "not diagnostic",
                   "fusidic acid", "post-hoc", "anticonservative"):
        assert phrase in lowered, f"manuscript.md drops: {phrase}"
    assert "1.4%" in lowered and "cannot exclude a confounder" in lowered, (
        "manuscript.md must state that the 1.4% exclusion cannot exclude a "
        "confounder")


def test_document_marks_missing_information(manuscript):
    """The submission tripwire. It lived in the two conference papers; when they
    were retired the manuscript had no author block at all, so one was added
    rather than letting the guard lapse. Delete this test -- do not weaken it --
    when the author list is genuinely supplied."""
    assert "[TODO" in manuscript, "expected explicit TODO markers"


def test_blindness_is_reported_over_the_screened_set(manuscript, audit):
    """138/800 (17.2%) was reported as the screen's reference blindness. 800 is
    the label CACHE; the screen covers 200, so the figure is 11/200 = 5.5%."""
    rc = audit["reference_coverage"]
    assert rc["screened_ingredients"] == 200
    correct = f"{100 * rc['screened_share_without_label']:.1f}%"
    stale = f"{100 * rc['share_without_label']:.1f}%"
    assert correct in manuscript, f"must report {correct}, the screened-set figure"
    # Derived from the counts, not from the stored share. Round 19: the
    # stored share was rounded to 4dp, so formatting it gave 9.8% while
    # 1712/17375 = 9.853% -> 9.9%. A guard that re-rounds the same rounded
    # value cannot catch a rounding error.
    exact = 100 * rc["pairs_touching_an_unlabelled_drug"] / rc["pairs_total"]
    assert f"{exact:.1f}%" in manuscript, (
        f"manuscript must report {exact:.1f}% "
        f"({rc['pairs_touching_an_unlabelled_drug']}/{rc['pairs_total']})")
    # Round 19: this used to check that the qualifying phrase appeared ANYWHERE
    # in the document. It did -- in §4.5 -- while the Abstract and Limitations
    # each carried "17.2% of ingredients ... including cerivastatin, the
    # fibrates", the round-10 withdrawn claim, one of them asserting it of
    # "screened ingredients" outright. A document-level co-occurrence check
    # cannot bind a claim to its qualification. Bind them per SENTENCE.
    import re as _re
    flat = " ".join(manuscript.split())
    for sentence in _re.split(r"(?<=[.!?])\s+", flat):
        if stale not in sentence:
            continue
        assert ("800" in sentence or "cache" in sentence.lower()), (
            f"the cache-wide figure {stale} appears in a sentence that does not "
            f"identify it as the 800-ingredient cache: {sentence[:160]}")
        assert "screened ingredient" not in sentence.lower(), (
            f"{stale} is the cache-wide share, not the screened share "
            f"({correct}); this sentence asserts it of the screened set: "
            f"{sentence[:160]}")


def test_drugs_cited_as_blind_were_actually_screened(manuscript, audit):
    """Four of the five drugs once cited as evidence were never in the screen."""
    rc = audit["reference_coverage"]
    assert rc["cited_but_not_screened"], "expected drugs cited but never screened"
    # Round 19: also per-sentence. The document-level version passed while the
    # Abstract cited cerivastatin and the fibrates as evidence of the SCREEN's
    # blindness, with the disclaimer sitting 700 lines away in §4.5.
    import re as _re
    flat = " ".join(manuscript.split()).lower()
    sentences = _re.split(r"(?<=[.!?])\s+", flat)
    for drug in rc["cited_but_not_screened"]:
        for sentence in sentences:
            if drug.lower() not in sentence:
                continue
            assert ("never" in sentence or "not bear on" in sentence
                    or "800" in sentence or "wider" in sentence), (
                f"{drug} was never screened, but appears in a sentence that "
                f"does not say so: {sentence[:160]}")
    assert "fusidic acid" in flat, "the one valid example must remain"


def test_non_drug_vocabulary_is_disclosed(manuscript, audit):
    """Four placeholder terms and one triplicated moiety enter the screen as
    drugs. Impact is small but must not be silent."""
    vh = audit["vocabulary_hygiene"]
    assert vh["invalid_pairs"] > 0
    assert "unspecified ingredient" in manuscript.lower()
    assert f"{vh['invalid_pairs']}" in manuscript
    for band in ("known_pair", "plausible"):
        for scope in ("as_specified", "excluding_invalid_pairs"):
            assert str(vh[scope][band]["enrichment"]) in manuscript, (
                f"manuscript must report {scope} {band} enrichment")
    assert vh["excluding_invalid_pairs"]["plausible"]["enrichment"] < 1.0


def test_document_states_the_environment_and_seeds(manuscript):
    """It claims byte-identical reruns; it must state versions and seeds."""
    lowered = manuscript.lower()
    assert "python 3" in lowered, "no language version"
    assert "duckdb" in lowered, "no database version"
    assert "seed" in lowered, "no mention of seeds"
    assert "byte-identical" in lowered


def test_control_table_rows_are_self_consistent(manuscript, numbers):
    """A row read 'n = 14 powered' while giving the multiplicative count /16."""
    a = numbers["tier_a"]
    assert f"4/{a['n_controls']}" in manuscript and f"12/{a['n_controls']}" in manuscript
    assert f"4/{a['n_powered']}" in manuscript and f"12/{a['n_powered']}" in manuscript
    # The label-selected rows are the invariant, not the notation. paper_a wrote
    # them as "55/349"; the manuscript tabulates the denominator in its own
    # column and the count with a percentage. Assert that the count and its
    # denominator appear on the SAME row, which is what "self-consistent"
    # actually means, rather than pinning one document's formatting.
    ipc = numbers["sensitivity"]["independent_positive_controls"]
    rows = [" ".join(line.split()) for line in manuscript.splitlines()]
    for arm in ("at_threshold_zero", "at_calibrated_threshold"):
        for null in ("additive", "multiplicative"):
            count, denom = str(ipc[arm][null]), str(ipc["n_pairs"])
            assert any(f"{count}/{denom}" in row
                       or (denom in row and count in row) for row in rows), (
                f"manuscript omits the label-selected {arm}/{null} count "
                f"{count} against its denominator {denom}")


def test_annotation_count_is_not_asserted_without_structure(manuscript):
    """'five progressively more independent annotation schemes' was not
    derivable from what the document reports."""
    assert "five progressively more independent" not in manuscript.lower()
    assert "three annotations" in manuscript.lower()


# --- round 11: error rates in the regime the study is about -----------------


@pytest.fixture(scope="module")
def regime(numbers):
    r = numbers.get("regime")
    if not r:
        pytest.skip("run `python -m faers_ddi.regime` first")
    return r


def test_in_regime_error_rates_are_reported(manuscript, regime):
    """The pooled false-positive rate was presented as though it described the
    regime where recovery is measured. The two populations barely overlap."""
    ir = regime["in_regime"]
    assert ir["negatives_reaching_positive_iqr"] / ir["negatives_total"] < 0.01, (
        "if the pools overlapped, the pooled rate would be adequate")
    for value in (f"{100 * ir['in_regime_fpr_additive']:.1f}%",
                  f"{100 * ir['in_regime_fpr_multiplicative']:.1f}%"):
        assert value in manuscript, f"must report the in-regime rate {value}"
    # Narrowed in round 18. The bare substring "essentially identical" also
    # matched an innocent sentence about hospitalisation strata, where two
    # enrichments genuinely are essentially identical. The withdrawn claim is
    # the FULL phrase, and it is policed -- in every phrasing found so far --
    # by test_no_maintained_document_carries_a_withdrawn_claim, so nothing is
    # lost by making this specific.
    assert "essentially identical false-positive" not in manuscript.lower(), (
        "the matched-FPR framing was withdrawn")


def test_event_definition_matches_the_pt_config(manuscript, numbers):
    """Round 24. The paper said the event was "23 PTs in 10 concepts" -- the
    whole curation -- while every primary result uses the `core` tier: 10 PTs in
    3 concepts. `core` admits 42,058 event cases and `broad` 339,063, so a
    reader applying the stated definition misses by eight-fold.

    This is the first guard here that runs from the CONFIG outward to the prose
    rather than from canonical_numbers.json outward. Round 23 noted that gap:
    every existing guard checks numbers the pipeline computed, none checked that
    the paper describes the inputs it actually used.
    """
    import csv as _csv

    with open(cfg.PROJECT_ROOT / "config" / "pt_sets" / "rhabdomyolysis.csv") as fh:
        rows = [r for r in _csv.DictReader(fh) if r["pt"].strip()]
    core = [r for r in rows if r["tier"].strip().lower() == "core"]
    ed = numbers["audit"]["event_definition"]

    # the canonical block must agree with the config it claims to describe
    assert ed["core_pts"] == len(core), (
        f"canonical says {ed['core_pts']} core PTs; the config has {len(core)}")
    assert ed["curated_pts"] == len(rows)
    assert ed["core_concepts"] == len({r["concept"].strip().lower() for r in core})

    # The prose must state the CORE counts *where it defines the event*. The
    # first version of this guard only required the core counts to appear
    # SOMEWHERE, and passed when the definitional sentence was corrupted back to
    # "23 PTs" because §3.5 still mentioned 10 elsewhere -- the round-19 distance
    # failure, in a guard written one round after that lesson was recorded.
    # Bind to the sentence that does the defining.
    import re as _re

    flat = " ".join(manuscript.split())
    defining = [s for s in _re.split(r"(?<=[.!?])\s+", flat)
                if _re.search(r"event was defined by|event is defined by", s)]
    assert defining, "no sentence defines the event"
    # Bind the PAIR, not membership. The second version of this guard asserted
    # that core_pts appeared among the sentence's numbers, and still passed the
    # mutation: core_pts is 10 and the wrong sentence says "in 10 concepts", so
    # the right number was present for the wrong reason. Two numeric
    # coincidences in two attempts is what a weak guard looks like.
    for sentence in defining:
        stated = _re.search(
            r"(\d+)\s+[^.]*?Preferred Terms\s+in\s+(\d+)\s+concepts", sentence)
        assert stated, (
            f"the defining sentence must read '<n> ... Preferred Terms in <m> "
            f"concepts' so the pair can be checked: {sentence[:150]}")
        pts, concepts = int(stated.group(1)), int(stated.group(2))
        assert (pts, concepts) == (ed["core_pts"], ed["core_concepts"]), (
            f"the event is defined as {pts} PTs in {concepts} concepts, but the "
            f"analysed (`core`) tier is {ed['core_pts']} in {ed['core_concepts']}. "
            f"The {ed['curated_pts']}-term curation admits "
            f"{ed['broad_event_cases']:,} event cases against core's "
            f"{ed['core_event_cases']:,} -- "
            f"{ed['broad_event_cases'] / ed['core_event_cases']:.0f}x.")

    for value in (f"{ed['core_event_cases']:,}", f"{ed['broad_event_cases']:,}"):
        assert value in flat, (
            f"the manuscript must give {value} so the two tiers cannot be "
            f"confused")


# Round 28. Cross-references that RESOLVE but point at the wrong section have
# now slipped past the round-19 existence check twice: §3.6-for-§3.7, and the
# Abstract citing §4.6 for the in-regime rates that §4.3 derives.
#
# Two general guards were written and MEASURED before this registry, and both
# were discarded:
#
#   * keyword overlap with the target section's title. Passes 37% of legitimate
#     citations -- titles like "Tier A and Tier B" and "Limitations" share no
#     vocabulary with the sentences citing them. 43 false positives.
#   * "a number in the citing sentence must appear in the cited section". Passes
#     98%, and catches the real defect, but the premise is false in general: a
#     sentence may cite a section for a qualitative claim while quoting figures
#     that belong elsewhere. 4 legitimate citations flagged, and whitelisting
#     them is the trap this project keeps falling into.
#
# So: an explicit registry, the same pattern as the withdrawn-claim and RETIRED
# registries. It only covers what is listed, which is honest about its scope --
# add an entry when a citation carries real weight.
# Round 30 renumbered §4 after three sections were inserted; these move with it.
CROSS_REFERENCE_BINDINGS = {
    "in regime the rates are": "4.4",
    "not by a binomial on the pair count": "4.4",
    "analysis to torsade": "4.4",
    "the analysis restricted to pairs whose two labels both exist": "4.8",
    "varied across a 20-fold range as a sensitivity analysis": "4.11",
    "with a control set drawn by FDA labelling": "4.13",
    # Round 31. Each contribution in the Introduction points at the section that
    # delivers it. Three of the six were wrong after round 30's renumbering: the
    # remap was applied by rule to the whole document, but these had been written
    # against the NEW numbering, so the rule moved them off target. The numbers
    # stayed unique and sequential throughout, so the round-30 guard passed --
    # a renumber can corrupt references without breaking the numbering.
    "The condition under which the choice of null stops mattering": "4.2",
    "The first calibrated error rates for both nulls": "4.4",
    "A one-line diagnostic for circular screen evaluation": "4.8",
    "An operating characteristic for DDI screening in this regime": "4.5",
    "A polypharmacy cap that improves sensitivity": "4.6",
}


def test_no_canonical_block_is_orphaned(numbers):
    """Round 32. Three blocks the paper depends on -- audit.nesting_condition,
    audit.top_ranked_pairs and regime.third_estimand -- were computed in
    throwaway scripts and merged into the canonical file by hand. No module
    produced them, and both stages assign their section WHOLESALE
    (`numbers["audit"] = results`), so the next documented pipeline run would
    have silently deleted all three while the paper went on quoting them.

    Same defect as round 22's hardcoded figure data, one level up: a number with
    no path from the code that is supposed to compute it. Cheap to check --
    every key in the canonical section must be assigned somewhere in the module
    that owns it.
    """
    import re as _re

    for section, module in (("audit", "audit.py"), ("regime", "regime.py")):
        source = (cfg.PROJECT_ROOT / "src" / "faers_ddi" / module).read_text()
        assigned = set(_re.findall(r'results\[\"(\w+)\"\]\s*=', source))
        assigned |= set(_re.findall(r'\"(\w+)\":', source))   # inline dict keys
        present = set(numbers.get(section, {}))
        orphans = sorted(k for k in present if k not in assigned)
        assert not orphans, (
            f"canonical['{section}'] contains {orphans} which {module} never "
            f"assigns; a pipeline run would drop them, and the paper quotes "
            f"them")


def test_section_numbers_are_unique_and_sequential(manuscript):
    """Round 30. Three sections were inserted into §4 without renumbering,
    producing two §4.2, two §4.4 and two §4.5. Every existing reference to
    those numbers then pointed at two different sections at once, and the
    round-28 existence check passed throughout -- the numbers all resolved,
    just not uniquely. This is the round-20 duplicate-table defect in a
    different medium.

    Numbering is structure, not decoration: a reader following §4.4 must arrive
    somewhere specific.
    """
    import re as _re
    from collections import Counter

    numbers = _re.findall(r"^#{2,4}\s+(\d+(?:\.\d+)*)\.?\s", manuscript, _re.M)
    duplicates = [n for n, c in Counter(numbers).items() if c > 1]
    assert not duplicates, (
        f"duplicate section numbers {sorted(duplicates)}; every reference to "
        f"them is ambiguous")

    # subsections of each chapter must run 1..n with no gaps
    from collections import defaultdict
    children = defaultdict(list)
    for n in numbers:
        if "." in n:
            parent, child = n.rsplit(".", 1)
            children[parent].append(int(child))
    for parent, kids in children.items():
        kids.sort()
        assert kids == list(range(1, len(kids) + 1)), (
            f"§{parent} subsections are {kids}, not sequential from 1; an "
            f"insertion or deletion did not renumber")


def test_load_bearing_cross_references_point_at_the_right_section(manuscript):
    """Each registered claim must cite the section that actually establishes it.

    See CROSS_REFERENCE_BINDINGS above for why this is a registry rather than a
    general rule, and what was measured before settling on one.
    """
    import re as _re

    # Blocks, not sentences. A numbered contribution runs several sentences and
    # carries its reference in the last one, so a sentence-scoped check found no
    # reference beside the phrase and skipped -- it passed its own mutation.
    # A block is a paragraph or a numbered list item.
    blocks = _re.split(r"\n\s*\n|\n(?=\d+\. \*\*)", manuscript)
    for phrase, expected in CROSS_REFERENCE_BINDINGS.items():
        for block in blocks:
            flat_block = " ".join(block.split())
            if phrase not in flat_block:
                continue
            refs = _re.findall(r"§(\d+(?:\.\d+)*)", flat_block)
            if not refs:
                continue
            assert expected in refs, (
                f"the claim {phrase!r} cites §{', §'.join(refs)} but is "
                f"established in §{expected}: {flat_block[:150]}")


def test_nesting_result_credits_prior_work(manuscript, numbers):
    """Round 29. The nesting implication was added as a lead contribution and a
    literature check found it already stated by Jung and Jung (2024). What is
    ours is the CONDITION -- both marginals elevated, since the expectations
    differ by (RR_A-1)(RR_B-1) -- and the demonstration that the unconditional
    form fails on real data. Claiming the implication itself would be a false
    novelty claim, which is worse than the framing problem this restructure was
    meant to fix.
    """
    flat = " ".join(manuscript.split())
    nc = numbers["audit"]["nesting_condition"]
    assert "Jung" in flat, (
        "the nesting implication is prior work and must be credited")
    assert f"{nc['violations_all']}" in flat and f"{nc['n_both_elevated']:,}" in flat, (
        "the paper must show where the unconditional form fails and where it "
        "does not, or it is claiming the prior result rather than refining it")
    assert nc["nesting_exact_when_both_elevated"], (
        "a both-elevated pair violates the nesting; the stated condition is wrong")


def test_null_nesting_claim_matches_the_data(manuscript, numbers):
    """Round 29. The paper's lead contribution is that E_mult >= E_add forces
    the multiplicative signal set inside the additive one, so the two nulls
    become one ordering at two thresholds.

    The implication is arithmetic given identical shrinkage, but the CLAIM the
    paper makes is empirical -- that the antecedent holds in the drug-dominant
    regime and not outside it, and that the data contain no counterexample.
    Assert the empirical part, and assert the direction, so a future run that
    reversed it would fail here rather than leaving a headline standing on
    numbers that no longer support it.
    """
    nn = numbers["audit"]["null_nesting"]

    assert nn["nesting_holds_where_expectations_ordered"], (
        "a pair signals under the multiplicative null but not the additive one "
        "while having E_mult >= E_add; that contradicts the shrinkage algebra "
        "and the paper's lead claim")
    assert nn["violations_with_expectation_reversed"] == nn["multiplicative_signals_not_additive"], (
        "some violation is not explained by reversed expectations, so the "
        "implication is not exhaustive as claimed")
    assert nn["share_ordered_high_expected_rate"] > nn["share_ordered_low_expected_rate"], (
        "the paper claims the expectation ordering is a property of the "
        "drug-dominant regime; that direction no longer holds")
    assert nn["share_ordered_high_expected_rate"] > 0.9

    flat = " ".join(manuscript.split())
    for value in (f"{100 * nn['share_ordered_high_expected_rate']:.1f}%",
                  f"{100 * nn['share_ordered_low_expected_rate']:.1f}%",
                  f"{nn['n_expectation_ordered']:,}"):
        assert value in flat, (
            f"the manuscript must report {value} for the nesting result")


def test_generalization_table_has_no_blank_cells(manuscript, numbers):
    """Round 27. The generalization table's `median marginal RR` column was
    populated for all three secondary events and blank for the primary one --
    the column that operationalises "drug-dominant", which is the paper's
    conditional, missing for the event the paper is about.

    Asserts every event block carries the comparative fields, so a future event
    added without them fails here rather than shipping an em dash.
    """
    g = numbers["generalization"]
    for name, block in g.items():
        for field in ("median_marginal_rr", "recovered_additive",
                      "recovered_multiplicative", "n_controls"):
            assert block.get(field) is not None, (
                f"generalization.{name} has no {field}; the table renders it as "
                f"a blank cell")
    flat = " ".join(manuscript.split())
    for name, block in g.items():
        value = f"{block['median_marginal_rr']:.1f}"
        assert value in flat, (
            f"the median marginal RR for {name} ({value}) is not in the "
            f"manuscript, so the table cannot be showing it")
    # the ordering is the paper's argument; assert it holds rather than assuming
    primary = g["rhabdomyolysis_primary"]["median_marginal_rr"]
    anaphylaxis = g.get("anaphylaxis", {}).get("median_marginal_rr")
    if anaphylaxis:
        assert primary > anaphylaxis, (
            "the paper argues the primary event is drug-dominant and anaphylaxis "
            "diffuse; if that ordering reversed, the conditional claim needs "
            "rewriting rather than this guard relaxing")


def test_in_regime_pool_ships_and_reproduces_its_rates(numbers):
    """Round 27. The pool carrying the two rates that make the calibration claim
    shipped nowhere, so a reviewer could not check them without a 154 GB
    rebuild. It ships now -- and must reproduce the rates exactly.

    The first export rounded the bounds to 3 dp, at which a value just above
    zero becomes 0.000 and the `> 0` test flips: the file gave 9.30% where the
    analysis gives 9.34%, one pair in 2,345. A table exported so a number can be
    rechecked has to return that number.
    """
    import csv as _csv

    path = cfg.path("tables") / "in_regime_pool.csv"
    if not path.exists():
        pytest.skip("in_regime_pool.csv not generated; run faers_ddi.regime")
    with path.open() as fh:
        rows = list(_csv.DictReader(fh))
    pool = numbers["regime"]["high_marginal_pool"]
    assert len(rows) == pool["n_pairs"], (
        f"shipped {len(rows):,} rows against a pool of {pool['n_pairs']:,}")

    strong = [r for r in rows if r["at_positive_control_strength"] == "1"]
    expected = pool["at_positive_control_strength"]
    assert len(strong) == expected["n"]

    for label, column, key in (("additive", "omega_add_lower", "fpr_additive"),
                               ("multiplicative", "omega_lower", "fpr_multiplicative")):
        from_bound = sum(1 for r in strong if float(r[column]) > 0) / len(strong)
        from_flag = sum(1 for r in strong if r[f"signals_{label}"] == "1") / len(strong)
        assert abs(from_bound - expected[key]) < 1e-4, (
            f"recomputing the in-regime {label} rate from the shipped bounds "
            f"gives {100 * from_bound:.2f}% against {100 * expected[key]:.2f}%; "
            f"the export has lost precision")
        assert abs(from_flag - expected[key]) < 1e-4, (
            f"the shipped signal flag for {label} disagrees with the rate")

    # and the marginal RRs behind Table 2 must ship too
    with (cfg.path("tables") / "tier_a_results.csv").open() as fh:
        controls = [r for r in _csv.DictReader(fh)
                    if r["tier"] == "core" and r["policy"] == "primary"]
    assert controls and all(r.get("rr_a") for r in controls), (
        "tier_a_results.csv must carry rr_a/rr_b, or Table 2's correlations "
        "cannot be recomputed from shipped artefacts")


def test_parse_validation_claims_match_the_validation_table(manuscript):
    """Round 26. The paper said "0 orphans across all 328,476,258 rows". That
    total is every parsed row across seven tables; the orphan check runs on the
    six CHILD tables, 303,663,833 rows, because DEMO is the parent of the
    relation and cannot orphan itself. An 8% overstatement of the scope of the
    paper's central parse-validation claim.

    It also quoted 104,186 withdrawn cases removed while the validation table
    reported 98,102 -- two shipped numbers for one quantity, unreconciled,
    because the check filtered to FAERS-era DEMO without saying so.

    Runs from the validation TABLE outward to the prose, the same direction as
    the tier-composition guard. Nothing here previously checked the artefacts
    that validate the parse.
    """
    import csv as _csv

    path = cfg.path("tables") / "parse_validation.csv"
    if not path.exists():
        pytest.skip("parse_validation.csv not generated")
    with path.open() as fh:
        rows = list(_csv.DictReader(fh))

    child = [r for r in rows if r["check"] == "child_resolves_to_demo"]
    assert child, "no orphan checks in the validation table"
    assert all(int(r["value"]) == 0 for r in child), "an orphan check is failing"
    child_rows = sum(int(r["denominator"]) for r in child)

    manifest = [r for r in rows if r["check"] == "rowcount_matches_manifest"]
    all_rows = sum(int(r["denominator"]) for r in manifest)
    assert all_rows > child_rows, "the child tables cannot be every parsed row"

    flat = " ".join(manuscript.split())
    assert f"{child_rows:,}" in flat, (
        f"the orphan claim must be scoped to the {child_rows:,} child-table rows "
        f"it actually covers, not the {all_rows:,} parsed in total")
    # The CLAIM sentence -- the one asserting a zero-orphan result -- must not
    # attach the all-tables total to it. Matching any sentence containing
    # "orphan" was too crude: the corrected prose explains that DEMO "cannot be
    # orphaned" and cites the manifest total in the same sentence, legitimately.
    import re as _re
    claims = [s for s in _re.split(r"(?<=[.!?])\s+", flat)
              if _re.search(r"\b(0|zero|no)\s+orphans?\b", s, _re.I)]
    assert claims, "no zero-orphan claim found; the parse validation is the "\
                   "paper's evidence that the delimiter bug did not bite"
    for sentence in claims:
        assert f"{child_rows:,}" in sentence, (
            f"the zero-orphan claim must state the {child_rows:,} child-table "
            f"rows it covers: {sentence[:170]}")
        assert f"{all_rows:,}" not in sentence, (
            f"the zero-orphan claim attributes the all-tables total "
            f"{all_rows:,} to a check that covers {child_rows:,}: "
            f"{sentence[:170]}")

    # both withdrawn-case counts must be reconciled where they appear
    either = [r for r in rows if r["check"] == "deleted_cases_match_demo_either_era"]
    faers = [r for r in rows if r["check"] == "deleted_cases_match_demo"]
    if either and faers:
        both, only_faers = int(either[0]["value"]), int(faers[0]["value"])
        # Triggered by the number the paper ALWAYS carries -- the attrition
        # removal count -- not by the one it might omit. The first version fired
        # only if 98,102 was present, so deleting the reconciliation deleted the
        # trigger and the guard passed. A guard whose precondition the defect
        # removes is not a guard.
        assert f"{both:,}" in flat, (
            f"the attrition table must report the {both:,} withdrawn cases "
            f"removed at stage 4")
        assert f"{only_faers:,}" in flat and f"{both - only_faers:,}" in flat, (
            f"the paper reports {both:,} withdrawn cases removed while "
            f"parse_validation.csv reports {only_faers:,} matching in FAERS-era "
            f"DEMO. Both must appear with the {both - only_faers:,} LAERS-only "
            f"difference, or the two shipped numbers read as a contradiction")


def test_every_tier_composition_statement_agrees_with_the_config(manuscript, numbers):
    """Round 25. Round 24 fixed the event definition in §3.5 and the Abstract,
    and left §4.3 saying the broad tier 'includes the two MedDRA concepts held
    out of the primary definition' -- so the paper stated two different
    compositions for one tier. The round-24 guard could not catch it: it binds
    the sentence that DEFINES the event, and this one merely CHARACTERISES a
    tier. Scoped to where the author was looking, again.

    This checks every sentence in the document that pairs a PT count with a
    concept count, and requires the pair to be one the config actually
    licenses: the full curation, the core tier, or the broad-only remainder.
    An invented or stale composition matches none of them.
    """
    import re as _re

    ed = numbers["audit"]["event_definition"]
    legitimate = {
        (ed["curated_pts"], ed["curated_concepts"]),
        (ed["core_pts"], ed["core_concepts"]),
        (ed["broad_only_pts"], ed["broad_only_concepts"]),
    }

    flat = " ".join(manuscript.split())
    # "<n> ... PTs|Preferred Terms ... in|across <m> concepts", tolerating the
    # markdown emphasis the prose uses around the numbers.
    pattern = _re.compile(
        r"\*{0,2}(\d+)\*{0,2}\s+(?:hand-curated\s+)?(?:MedDRA\s+)?"
        r"(?:PTs|Preferred Terms)[^.]{0,60}?(?:in|across)\s+\*{0,2}(\d+)\*{0,2}\s+concepts")
    found = [(int(a), int(b)) for a, b in pattern.findall(flat)]
    assert found, "no tier-composition statement found; the pattern has drifted"

    for pair in found:
        assert pair in legitimate, (
            f"the document states a tier as {pair[0]} PTs in {pair[1]} concepts, "
            f"which the config does not license. Valid compositions are "
            f"{sorted(legitimate)}: the full curation, the core tier (analysed), "
            f"and the broad-only remainder.")

    # the core composition must be among them -- a document that only ever
    # describes the curation has not said what was analysed
    assert (ed["core_pts"], ed["core_concepts"]) in found, (
        f"no statement gives the analysed (core) composition of "
        f"{ed['core_pts']} PTs in {ed['core_concepts']} concepts")


def test_shipped_negative_pool_is_the_pool_that_was_analysed(numbers):
    """Round 24. tier_b_pairs.csv shipped 2,000 rows against a 16,138-pair
    analysis -- a balanced sample from the superseded `n_pairs: 2000` regime,
    and the exact sampling §4.3 argues against. The calibrated threshold
    recomputed from the shipped file was +1.273 against the reported +0.436.

    It is also the only shipped table carrying rr_a/rr_b, so it is the route a
    reviewer takes to recompute the marginal-strength analyses without the
    154 GB database.
    """
    import csv as _csv

    path = cfg.path("tables") / "tier_b_pairs.csv"
    if not path.exists():
        pytest.skip("tier_b_pairs.csv not generated")
    with path.open() as fh:
        rows = list(_csv.DictReader(fh))
    assert len(rows) == numbers["tier_b"]["n_pairs"], (
        f"tier_b_pairs.csv ships {len(rows):,} rows against an analysis of "
        f"{numbers['tier_b']['n_pairs']:,}; the shipped pool must be the pool "
        f"that was analysed")

    from collections import Counter
    counts = Counter(r["stratum"] for r in rows)
    for stratum in ("easy", "hard"):
        assert counts[stratum] == numbers["tier_b"]["strata"][stratum]["n"], (
            f"{stratum} stratum: shipped {counts[stratum]}, analysed "
            f"{numbers['tier_b']['strata'][stratum]['n']}")

    # and it must actually reproduce the calibration
    import numpy as _np
    values = _np.array([float(r["omega_add_lower"]) for r in rows])
    recomputed = float(_np.percentile(values, 95))
    assert abs(recomputed - numbers["tier_b"]["calibrated_threshold"]) < 0.01, (
        f"the shipped pool gives a 5%-FPR threshold of {recomputed:+.3f} "
        f"against the reported "
        f"{numbers['tier_b']['calibrated_threshold']:+.3f}")


def test_in_regime_rates_carry_a_clustered_interval(manuscript, regime):
    """Round 23. The two rates carrying the calibration claim shipped as bare
    point estimates for six rounds, while Methods promised a cluster bootstrap
    for pair-aggregated quantities. The 2,345 pairs come from 478 drugs and each
    drug recurs across many, so the binomial interval is too narrow.

    Resampling drugs gives 1.24-3.34% (multiplicative) and 7.29-11.32%
    (additive). That is what makes the paper's central correction provable: the
    multiplicative interval COVERS the nominal 2.5% and the additive one
    excludes it, so the miscalibration is one-sided as claimed. A reviewer who
    recomputes will do exactly this.
    """
    strong = regime["high_marginal_pool"]["at_positive_control_strength"]
    flat = " ".join(manuscript.split())

    for null in ("multiplicative", "additive"):
        block = strong.get(f"fpr_{null}_clustered")
        assert block and block.get("cluster_ci"), (
            f"no clustered interval computed for the in-regime {null} rate")
        lo, hi = block["cluster_ci"]
        naive = block["naive_binomial_ci_ANTICONSERVATIVE"]
        assert (hi - lo) > (naive[1] - naive[0]), (
            f"the clustered interval for {null} is not wider than the binomial "
            f"one; that would mean the dependence correction did nothing")
        assert f"{100 * lo:.2f}" in flat and f"{100 * hi:.2f}" in flat, (
            f"the manuscript does not report the clustered interval "
            f"{100 * lo:.2f}-{100 * hi:.2f}% for the in-regime {null} rate")

    # the direction of the claim, asserted rather than assumed
    m = strong["fpr_multiplicative_clustered"]["cluster_ci"]
    a = strong["fpr_additive_clustered"]["cluster_ci"]
    assert m[0] <= 0.025 <= m[1], (
        "the multiplicative interval no longer covers the nominal 2.5%; the "
        "one-sided-miscalibration claim needs rewriting, not this guard")
    assert not (a[0] <= 0.025 <= a[1]), (
        "the additive interval now covers 2.5%; the claim that only the "
        "additive null is miscalibrated on error rate would no longer hold")


def test_matched_recovery_gap_is_reported(manuscript, regime):
    """The eight-pair gap at the conventional threshold is one to two pairs
    once the error rates are equalised."""
    mr = regime["matched_recovery"]
    assert mr["gap_as_published"] > mr["gap_matched_max"], (
        "the whole point is that the gap shrinks when rates are matched")
    for row in mr["rows"]:
        assert (f"{row['recovered_additive']}/16" in manuscript
                or f"{row['recovered_additive']} vs" in manuscript), (
            f"manuscript omits the {row['operating_point']} arm")
    assert mr["additive_wins_at_every_matched_rate"]


def test_purpose_built_negative_pool_exists_and_is_larger(manuscript, regime):
    """The standard generator excludes the configuration every positive control
    has, so it cannot produce a negative that resembles a positive."""
    pool = regime["high_marginal_pool"]
    strong = pool["at_positive_control_strength"]
    assert strong["n"] > 10 * regime["in_regime"]["in_regime_n"], (
        "the purpose-built pool must be substantially better powered")
    assert f"{pool['n_pairs']:,}" in manuscript
    assert f"{strong['n']:,}" in manuscript
    assert f"{100 * strong['fpr_additive']:.1f}%" in manuscript
    assert f"{100 * strong['fpr_multiplicative']:.1f}%" in manuscript


def test_torsade_replication_is_reported_as_failing_at_matched_rates(manuscript, regime):
    """At Omega_025 > 0 the additive null recovers 9/10 while running at a
    42.8% in-regime false-positive rate. Matched, the advantage vanishes."""
    t = regime["torsade_matched"]
    published, matched = t["matched_recovery"]["rows"][0], t["matched_recovery"]["rows"][1:]
    assert published["recovered_additive"] - published["recovered_multiplicative"] >= 5
    assert all(r["recovered_additive"] - r["recovered_multiplicative"] <= 1
               for r in matched), "expected the advantage to vanish at matched rates"
    assert f"{100 * t['in_regime']['in_regime_fpr_additive']:.1f}%" in manuscript
    lowered = manuscript.lower()
    assert "does not survive matched error rates" in lowered or \
           "failed replication" in lowered


def test_chance_baseline_is_strength_matched(manuscript, regime):
    """The pooled expectation assumes a constant rate; it varies 12-fold."""
    smc = regime["strength_matched_chance"]
    rates = smc["rate_by_quintile"]
    assert max(rates) / max(min(rates), 1e-9) > 5, "expected wide variation"
    assert f"{smc['total']['expected_matched']:,}" in manuscript
    assert smc["screen_below_chance_when_matched"], (
        "the strength-matched expectation exceeds the observed count")
    assert "fewer" in manuscript.lower()


def test_negative_control_exclusion_is_disclosed(manuscript):
    """The generator drops pairs where BOTH drugs are implicated -- which is
    what every positive control is."""
    lowered = manuscript.lower()
    assert "cannot produce a negative" in lowered or \
           "removes exactly the configuration" in lowered, (
        "must disclose the consequence of the exclusion rule")


def test_both_nulls_reported_by_stratum(manuscript, numbers):
    """Reporting the strata for one null only concealed a sign reversal."""
    strata = numbers["tier_b"]["strata"]
    for key in ("easy", "hard"):
        for null in ("fpr_additive", "fpr_multiplicative"):
            assert f"{100 * strata[key][null]:.2f}%" in manuscript, (
                f"manuscript omits {key}/{null}")


# --- every maintained document, not just the one being edited ---------------
# Round 11's corrections landed in paper_a and paper_b while manuscript.md kept
# the withdrawn claim, and the suite passed 328 because each round's guards were
# written against whichever documents were open at the time. These assert across
# the whole set.

MAINTAINED = {
    "manuscript": cfg.PROJECT_ROOT / "paper" / "manuscript.md",
}


@pytest.fixture(scope="module")
def maintained() -> dict:
    missing = [n for n, p in MAINTAINED.items() if not p.exists()]
    if missing:
        pytest.skip(f"missing documents: {missing}")
    return {n: p.read_text().replace("−", "-") for n, p in MAINTAINED.items()}


def test_no_maintained_document_carries_a_withdrawn_claim(maintained):
    """Claims retracted by a later round must not survive in any document."""
    withdrawn = {
        "essentially identical false-positive rate":
            "round 11: in-regime rates are 2.2% vs 9.3%, not 6.4% vs 6.7%",
        "138 of the 800 screened ingredients":
            "round 10: the screen covers 200; the figure is 11/200 = 5.5%",
        "137.8":
            "round 9: recomputed to 141.4x",
        "189.2 expected":
            "round 9: the Tier A table gives 189.5",
        "almost identical false-positive rate":
            "round 17: the same claim round 11 withdrew, surviving in "
            "manuscript.md behind a synonym -- the fifth time a guard here has "
            "been defeated by a surface detail rather than by an argument",
        "twice as conservative":
            "round 17: 2.5/2.2 = 1.13x, not 2x. The additive figure "
            "(9.3/2.5 = 3.7x) was right; this one was never computed",
        "does not rise with marginal strength at all":
            "round 17: r = +0.12 with CI -0.40 to +0.58 cannot exclude a "
            "moderate rise; the supported claim is 'far shallower than either "
            "null predicts'",
        "both disproportionality nulls are severely miscalibrated":
            "round 17: only the additive null is miscalibrated on error rate. "
            "Omega runs at 2.2% against a nominal 2.5% (52/2345, Jeffreys "
            "interval covers 2.5%, exact binomial p = 0.43) and at 2.0% on "
            "torsade (3/152, p = 1.00). It is disqualified by power, not size",
    }
    # Collapse whitespace first. The first version of this test matched
    # contiguous strings and missed "138 of the 800\nscreened ingredients" in
    # manuscript.md purely because the phrase spanned a line break -- the fourth
    # time in this project a guard has been defeated by a surface text detail.
    for name, text in maintained.items():
        flat = " ".join(text.split())
        for phrase, why in withdrawn.items():
            assert " ".join(phrase.split()) not in flat, (
                f"{name} still carries '{phrase}' — {why}")


def test_documents_report_the_in_regime_miscalibration_as_one_sided(maintained, regime):
    """Round 17. The registry above forbids the withdrawn wording; this asserts
    the replacement is actually present, because deleting a bad sentence and
    writing nothing passes a negative guard.

    The in-regime rates are 2.2% (multiplicative) and 9.3% (additive) against a
    nominal 2.5%. Only the second is a miscalibration: 52/2345 has a Jeffreys
    interval covering 2.5% and an exact binomial p of 0.43 against it, and the
    torsade replication is 3/152 (p = 1.00). Any document quoting BOTH rates is
    making the comparison and must say which way it runs.

    Both rates are read from the canonical file rather than hardcoded, so this
    guard follows the numbers if they move.
    """
    rates = regime["high_marginal_pool"]["at_positive_control_strength"]
    mult = f"{100 * rates['fpr_multiplicative']:.1f}%"
    add = f"{100 * rates['fpr_additive']:.1f}%"
    markers = ("advertised rate", "roughly as advertised", "one-sided",
               "different currencies", "disqualified by power",
               "power rather than size", "power, not size")
    for name, text in maintained.items():
        flat = " ".join(text.split())
        if mult not in flat or add not in flat:
            continue
        assert any(m in flat for m in markers), (
            f"{name} quotes the in-regime pair ({mult} multiplicative, {add} "
            f"additive) without stating that the miscalibration is one-sided; "
            f"at {mult} against a nominal 2.5% the multiplicative null is "
            f"correctly calibrated and fails on power instead")


def test_every_document_that_compares_nulls_reports_in_regime_rates(maintained, regime):
    """A document reporting 4/16 against 12/16 must also report the error rates
    that comparison is made at, or it repeats the withdrawn framing."""
    ir = regime["in_regime"]
    pool = regime["high_marginal_pool"]["at_positive_control_strength"]
    for name, text in maintained.items():
        if "4/16" not in text:
            continue
        assert (f"{100 * pool['fpr_additive']:.1f}%" in text
                or f"{100 * ir['in_regime_fpr_additive']:.1f}%" in text), (
            f"{name} compares the nulls without giving the in-regime rates")


def test_every_document_reporting_torsade_reports_the_matched_result(maintained, regime):
    t = regime["torsade_matched"]["in_regime"]
    for name, text in maintained.items():
        if "torsade" not in text.lower():
            continue
        assert f"{100 * t['in_regime_fpr_additive']:.1f}%" in text, (
            f"{name} reports torsade without the 42.8% in-regime rate that "
            f"makes the 9-vs-0 result an operating-point artefact")


def test_no_document_title_asserts_a_conclusion(maintained):
    """Titles describe what was studied; a title is not the place to make a
    claim the paper may later have to withdraw."""
    banned = ("fails", "is unusable", "are severely miscalibrated",
              "we show", "proves", "demonstrates that")
    for name, text in maintained.items():
        title = text.splitlines()[0].lower()
        assert title.startswith("# ")
        for phrase in banned:
            assert phrase not in title, f"{name} title asserts: '{phrase}'"


RETIRED = {
    "paper": "round 11: duplicated manuscript.md in a different section order",
    "paper_a": "round 18: merged back into manuscript.md",
    "paper_b": "round 18: merged back into manuscript.md",
}


def test_retired_documents_are_not_built_and_are_labelled():
    """Retired documents must be out of the build directory, out of build.py,
    and labelled where they are archived — not left as further things to keep
    in sync.

    Generalised in round 18. This test was written for paper.md and named for
    documents plural, but every assertion was hardcoded to that one file, so it
    would have passed unchanged while paper_a.md and paper_b.md rotted in the
    build directory. That is the round-16 defect in a test written to prevent
    the round-16 defect.
    """
    build = (cfg.PROJECT_ROOT / "paper" / "build.py").read_text()
    for name, why in RETIRED.items():
        live = cfg.PROJECT_ROOT / "paper" / f"{name}.md"
        assert not live.exists(), (
            f"{name}.md is back in the build directory ({why})")
        for artefact in (f"{name}.tex", f"{name}.pdf"):
            assert not (cfg.PROJECT_ROOT / "paper" / artefact).exists(), (
                f"stale {artefact} left behind by the retirement of {name}.md")
        archived = cfg.PROJECT_ROOT / "paper" / "archive" / f"{name}.md"
        if archived.exists():
            head = archived.read_text()[:800].lower()
            assert "archived" in head and "superseded" in head, (
                f"the archived copy of {name}.md must say so at the top")
        assert f'"{name}":' not in build, (
            f"build.py still lists the retired document {name}.md")
