from __future__ import annotations

from pathlib import Path

import pytest

from citiesai.dashboard import extract_headline_metrics
from citiesai.rates import (
    IN_GAME_HOURS_PER_MONTH,
    extract_hourly_rates,
    population_change_per_hour,
    treasury_net_per_hour,
)
from citiesai.snapshot import load_snapshot, snapshot_meta

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


def test_treasury_net_per_hour() -> None:
    # Monthly net 136_000 → 5666.67/h at 24h/month
    rate = treasury_net_per_hour(1_112_000, 976_000)
    assert rate is not None
    assert rate == pytest.approx(136_000 / IN_GAME_HOURS_PER_MONTH)


def test_population_change_per_hour() -> None:
    rate = population_change_per_hour(241, 188, 1240, 631)
    assert rate is not None
    assert rate == pytest.approx(662 / IN_GAME_HOURS_PER_MONTH)


def test_extract_hourly_rates_from_sample(vendor_sample: dict) -> None:
    rates = extract_hourly_rates(vendor_sample)
    assert rates["treasury_net_per_hour"] == pytest.approx(136_000 / IN_GAME_HOURS_PER_MONTH)
    assert rates["population_change_per_hour"] == pytest.approx(662 / IN_GAME_HOURS_PER_MONTH)


def test_extract_headline_metrics_includes_hourly(vendor_sample: dict) -> None:
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    metrics = extract_headline_metrics(vendor_sample, meta)
    assert "treasury_net_per_hour" in metrics
    assert "population_change_per_hour" in metrics
    assert metrics["treasury_net_per_hour"] == pytest.approx(136_000 / IN_GAME_HOURS_PER_MONTH)
