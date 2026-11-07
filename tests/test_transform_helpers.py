"""Unit tests for utils.transform_helpers."""

import pytest

from utils.transform_helpers import (
    ddmmyyyy_to_iso_date,
    drop_duplicates,
    epoch_ms_to_iso,
    haversine_km,
    parse_float,
    parse_iso_date,
    to_celsius,
    to_kmh,
    to_mm,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(18.3, 18.3), ("18.30", 18.3), ("1,234.5", 1234.5), (7, 7.0), (" 3.5 ", 3.5)],
)
def test_parse_float_reads_numbers(value, expected):
    assert parse_float(value) == expected


@pytest.mark.parametrize("value", [None, "", "N/E", "abc", True, float("nan"), float("inf")])
def test_parse_float_returns_none_for_missing_or_invalid(value):
    assert parse_float(value) is None


def test_date_conversions_return_iso_8601():
    assert ddmmyyyy_to_iso_date("05/11/2026") == "2026-11-05"
    assert parse_iso_date(" 2026-11-05 ") == "2026-11-05"
    assert epoch_ms_to_iso(1_700_000_000_000) == "2023-11-14T22:13:20Z"
    assert epoch_ms_to_iso(0) == "1970-01-01T00:00:00Z"


@pytest.mark.parametrize("bad", ["31/02/2026", "2026-11-05", "", "05-11-2026"])
def test_ddmmyyyy_rejects_other_formats_and_impossible_dates(bad):
    with pytest.raises(ValueError):
        ddmmyyyy_to_iso_date(bad)


def test_unit_conversions():
    assert to_celsius(212, "°F") == pytest.approx(100)
    assert to_celsius(30, "°C") == 30
    assert to_kmh(10, "m/s") == pytest.approx(36)
    assert to_kmh(10, "mp/h") == pytest.approx(16.09344)
    assert to_mm(1, "inch") == pytest.approx(25.4)


def test_unsupported_units_fail_loudly_instead_of_guessing():
    with pytest.raises(ValueError):
        to_celsius(10, "K")
    with pytest.raises(ValueError):
        to_kmh(10, "furlong/fortnight")
    with pytest.raises(ValueError):
        to_mm(10, "gallons")


def test_haversine_is_zero_for_the_same_point_and_right_for_merida_to_mexico_city():
    assert haversine_km(20.97, -89.59, 20.97, -89.59) == pytest.approx(0)
    assert 980 < haversine_km(20.9674, -89.5926, 19.4326, -99.1332) < 1020


def test_drop_duplicates_keeps_the_last_record_per_key():
    records = [{"k": "a", "v": 1}, {"k": "b", "v": 2}, {"k": "a", "v": 3}]

    unique, dropped = drop_duplicates(records, "k")

    assert unique == [{"k": "a", "v": 3}, {"k": "b", "v": 2}]
    assert dropped == 1
