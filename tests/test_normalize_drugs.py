"""Tests for drug-name normalisation and salt stripping.

Salt stripping is the step that decides whether ATORVASTATIN and ATORVASTATIN
CALCIUM are one drug or two. Getting it wrong splits every statin-interaction
count across spellings, which would quietly halve the signal this study exists
to measure -- so the control-set drugs are asserted by name.
"""

from __future__ import annotations

import pytest

from faers_ddi.normalize_drugs import (
    PROTECTED_COMPOUNDS,
    SALT_TOKENS,
    normalise_name,
    relax_name,
    strip_salts,
)


# --- basic normalisation ---------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  simvastatin  ", "SIMVASTATIN"),
        ("SIMVASTATIN", "SIMVASTATIN"),
        ("Simva   statin", "SIMVA STATIN"),
        ("\tsimvastatin\n", "SIMVASTATIN"),
    ],
)
def test_normalise_name(raw, expected):
    assert normalise_name(raw) == expected


# --- salt and hydrate stripping --------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ATORVASTATIN CALCIUM", "ATORVASTATIN"),
        ("ROSUVASTATIN CALCIUM", "ROSUVASTATIN"),
        ("AMIODARONE HYDROCHLORIDE", "AMIODARONE"),
        ("DILTIAZEM HYDROCHLORIDE", "DILTIAZEM"),
        ("VERAPAMIL HYDROCHLORIDE", "VERAPAMIL"),
        ("OXYCODONE HYDROCHLORIDE", "OXYCODONE"),
        ("METOPROLOL SUCCINATE", "METOPROLOL"),
        # Repeated stripping: salt then hydrate.
        ("FORMOTEROL FUMARATE DIHYDRATE", "FORMOTEROL"),
        ("EMTRICITABINE PHOSPHATE MONOHYDRATE", "EMTRICITABINE"),
        # Nothing to strip.
        ("SIMVASTATIN", "SIMVASTATIN"),
        ("COLCHICINE", "COLCHICINE"),
        ("GEMFIBROZIL", "GEMFIBROZIL"),
    ],
)
def test_salt_forms_reduce_to_the_active_moiety(raw, expected):
    assert strip_salts(raw) == expected


def test_stripping_never_empties_the_name():
    """A bare salt token must survive rather than reducing to nothing."""
    for token in ("SODIUM", "CALCIUM", "HYDROCHLORIDE"):
        assert strip_salts(token) == token


@pytest.mark.parametrize("compound", sorted(PROTECTED_COMPOUNDS))
def test_mineral_compounds_are_not_stripped(compound):
    """The head token is an element, so stripping produces a meaningless node.

    Reducing CALCIUM CARBONATE to CALCIUM merges antacids, supplements and
    phosphate binders into one high-volume pseudo-drug that would then appear in
    the screen.
    """
    assert strip_salts(compound) == compound


def test_lithium_carbonate_is_deliberately_not_protected():
    """Lithium IS the active moiety; lithium citrate is the same drug."""
    assert strip_salts("LITHIUM CARBONATE") == "LITHIUM"
    assert strip_salts("LITHIUM CITRATE") == "LITHIUM"


def test_chloride_is_stripped_from_genuine_drugs():
    """CHLORIDE was missing from the token list while CARBONATE was present, so
    CALCIUM CARBONATE collapsed and SODIUM CHLORIDE did not."""
    assert strip_salts("TIOTROPIUM CHLORIDE") == "TIOTROPIUM"
    assert strip_salts("SODIUM CHLORIDE") == "SODIUM CHLORIDE"


def test_every_protected_compound_actually_ends_in_a_salt_token():
    """Guards against a protected entry that the stripper would never touch,
    which would be dead configuration rather than a real exemption."""
    for compound in PROTECTED_COMPOUNDS:
        assert compound.split()[-1] in SALT_TOKENS, compound


def test_punctuation_is_normalised_away():
    assert strip_salts("ATORVASTATIN-CALCIUM") == "ATORVASTATIN"
    assert strip_salts("AMIODARONE  HCL") == "AMIODARONE"


# --- relaxed matching ------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("TOPROL-XL", "TOPROL"),
        ("HUMIRA 40 MG/0.8 ML PEN", "HUMIRA"),
        ("ADVAIR DISKUS 100/50", "ADVAIR"),
        ("ALEVE (CAPLET)", "ALEVE"),
        ("DURAGESIC-100", "DURAGESIC"),
        ("ACETYLSALICYLIC ACID SRT", "ACETYLSALICYLIC ACID"),
        ("DIANEAL LOW CALCIUM (ULTRABAG)", "DIANEAL LOW CALCIUM"),
        ("SIMVASTATIN 20MG TABLET", "SIMVASTATIN"),
    ],
)
def test_relax_name_strips_dose_form_and_packaging(raw, expected):
    assert relax_name(raw) == expected


def test_relax_name_keeps_the_drug_when_everything_else_is_noise():
    assert relax_name("SIMVASTATIN") == "SIMVASTATIN"
    assert relax_name("simvastatin 40 mg") == "SIMVASTATIN"


def test_relax_name_can_return_empty_for_pure_noise():
    """Callers fall back to the exact key, so an empty relaxed key is safe."""
    assert relax_name("100 MG") == ""
    assert relax_name("(TABLET)") == ""


# --- the drugs this study depends on ---------------------------------------


CONTROL_DRUGS = [
    "SIMVASTATIN", "ATORVASTATIN", "ROSUVASTATIN", "LOVASTATIN",
    "AMIODARONE", "CLARITHROMYCIN", "ITRACONAZOLE", "GEMFIBROZIL",
    "CYCLOSPORINE", "DILTIAZEM", "VERAPAMIL", "COLCHICINE",
]


@pytest.mark.parametrize("drug", CONTROL_DRUGS)
def test_control_drugs_are_stable_under_normalisation(drug):
    """Each control drug must be a fixed point, and its common salt form must
    reduce to it rather than forming a second drug."""
    assert strip_salts(drug) == drug
    assert normalise_name(drug.lower()) == drug
    for salt in ("CALCIUM", "HYDROCHLORIDE", "SODIUM"):
        assert strip_salts(f"{drug} {salt}") == drug
