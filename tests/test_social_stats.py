import pytest

from citiesai.social_stats import resident_population, social_index


def test_social_index_prefers_direct_0_100() -> None:
    assert social_index(82, population=1000) == 82.0
    assert social_index(41.2, population=618) == 41.2


def test_social_index_divides_weighted_sum_by_population() -> None:
    assert social_index(31230, population=618) == pytest.approx(50.5, rel=1e-3)
    assert social_index(41225, population=618) == pytest.approx(66.7, rel=1e-3)


def test_social_index_returns_none_without_population_for_large_raw() -> None:
    assert social_index(31230, population=None) is None
    assert social_index(150000, population=1000) is None


def test_resident_population_prefers_official_count() -> None:
    snap = {
        "OfficialCityStatistics": {"PopulationFlow": {"population": 618}},
        "Population": {"total_population": 713, "local_population": 618},
    }
    assert resident_population(snap) == 618
