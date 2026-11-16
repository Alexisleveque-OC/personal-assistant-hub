"""Équivalences insolites du jour (ROADMAP Étape 3, demande du 16/11) : 4 par jour, une par famille,
une référence différente chaque jour, aucune répétition avant d'avoir épuisé la réserve de la famille."""
from datetime import date, timedelta

import pytest

from app.core.sport_equivalences import FAMILIES, REFERENCES, daily_equivalences, equivalence_for, reference_index


def _ref(family: str, ref_id: str):
    return next(r for r in REFERENCES[family] if r.id == ref_id)


def test_four_equivalences_per_day_one_per_family():
    facts = daily_equivalences(total_km=904.0, total_dplus=5940, day=date(2026, 11, 16))
    assert [f.category for f in facts] == list(FAMILIES) == ["vertical", "geo", "energy", "animal"]
    assert all(f.headline and f.detail and f.text and f.icon for f in facts)
    assert facts == daily_equivalences(total_km=904.0, total_dplus=5940, day=date(2026, 11, 16))  # stable dans la journée


@pytest.mark.parametrize("family", ["vertical", "geo", "energy", "animal"])
def test_each_pool_is_big_enough_and_every_reference_shows_up_once_per_cycle(family):
    size = len(REFERENCES[family])
    assert size >= 7
    first = date(2026, 1, 1)
    while first.toordinal() % size:
        first += timedelta(days=1)
    for cycle in range(3):
        start = first + timedelta(days=cycle * size)
        picks = [reference_index(family, start + timedelta(days=i)) for i in range(size)]
        assert sorted(picks) == list(range(size)), picks


@pytest.mark.parametrize("family", ["vertical", "geo", "energy", "animal"])
def test_never_the_same_reference_two_days_in_a_row(family):
    day = date(2026, 1, 1)
    previous = reference_index(family, day)
    for _ in range(3 * 365):
        day += timedelta(days=1)
        current = reference_index(family, day)
        assert current != previous, day
        previous = current


def test_families_do_not_rotate_in_lockstep():
    days = [date(2026, 11, 16) + timedelta(days=i) for i in range(10)]
    assert [reference_index("vertical", d) for d in days] != [reference_index("geo", d) for d in days]


def test_ratio_headlines_like_the_mockup():
    eiffel = equivalence_for(_ref("vertical", "eiffel"), total_km=904.0, total_dplus=5940)
    assert (eiffel.headline, eiffel.detail) == ("19,8 × la tour Eiffel", "5 940 m de D+ cumulés, la tour Eiffel en fait 300")
    assert eiffel.text == "19,8 × la tour Eiffel (5 940 m de D+ cumulés, la tour Eiffel en fait 300) !"
    everest = equivalence_for(_ref("vertical", "everest"), total_km=904.0, total_dplus=5940)
    assert everest.headline == "67 % de l'Everest"
    gr20 = equivalence_for(_ref("geo", "gr20"), total_km=904.0, total_dplus=0)
    assert (gr20.headline, gr20.detail) == ("5 × le GR20", "904 km au total, le GR20 en fait 180")


def test_energy_counts_items_from_burned_calories():
    croissants = equivalence_for(_ref("energy", "croissant"), total_km=904.0, total_dplus=0)
    assert (croissants.headline, croissants.detail) == ("235 croissants", "environ 58 760 kcal brûlées, ≈ 250 kcal le croissant")


def test_animal_references():
    tern = equivalence_for(_ref("animal", "sterne"), total_km=904.0, total_dplus=0)
    assert tern.headline == "1,3 % de la migration d'une sterne arctique"
    cheetah = equivalence_for(_ref("animal", "guepard"), total_km=904.0, total_dplus=0)
    assert cheetah.headline == "9 h 02 pour un guépard"
    snail = equivalence_for(_ref("animal", "escargot"), total_km=904.0, total_dplus=0)
    assert snail.headline == "28,7 ans pour un escargot"


def test_nothing_to_compare_without_kilometres_or_climbing():
    assert daily_equivalences(total_km=0.0, total_dplus=0, day=date(2026, 11, 16)) == []
    facts = daily_equivalences(total_km=12.0, total_dplus=0, day=date(2026, 11, 16))
    assert [f.category for f in facts] == ["geo", "energy", "animal"]
