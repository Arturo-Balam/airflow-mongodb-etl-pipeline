"""Unit tests for the three dataset transformations (pure functions, no I/O)."""

import pytest
from transform_earthquakes import (
    depth_class,
    magnitude_class,
    transform_earthquakes,
)
from transform_fx import transform_fx
from transform_weather import heat_category, transform_weather

# ----------------------------------------------------------------------------- weather


def weather_payload():
    return {
        "daily_units": {
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "precipitation_sum": "mm",
            "wind_speed_10m_max": "km/h",
        },
        "daily": {
            "time": ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"],
            "temperature_2m_max": [33.0, 39.5, None, 95.0],
            "temperature_2m_min": [22.0, 24.5, 21.0, 20.0],
            "precipitation_sum": [0.0, None, 5.2, 1.0],
            "wind_speed_10m_max": [18.0, 25.5, 10.0, 5.0],
            "weather_code": [1, 95, 3, 0],
        },
    }


def test_weather_keeps_clean_days_and_drops_missing_and_corrupted_ones():
    records, stats = transform_weather(weather_payload())

    assert [r["date"] for r in records] == ["2026-11-03", "2026-11-04"]
    assert stats.records_in == 4
    assert stats.records_out == 2
    assert stats.dropped_missing == 1  # 2026-11-05 has no max temperature
    assert stats.dropped_corrupted == 1  # 95 C is not a real air temperature


def test_weather_standardizes_names_and_adds_derived_fields():
    records, _ = transform_weather(weather_payload())
    warm, extreme = records

    assert warm["_id"] == "2026-11-03"
    assert warm["temp_mean_c"] == 27.5
    assert warm["temp_range_c"] == 11.0
    assert warm["heat_category"] == "warm"
    assert warm["is_extreme_heat"] is False
    assert warm["is_rainy_day"] is False
    assert warm["weather_description"] == "mainly clear"
    assert extreme["temp_mean_c"] == 32.0
    assert extreme["heat_category"] == "extreme"
    assert extreme["is_extreme_heat"] is True
    assert extreme["weather_description"] == "thunderstorm"


def test_weather_imputes_missing_rain_as_zero_and_flags_it():
    records, stats = transform_weather(weather_payload())
    extreme = records[1]

    assert extreme["precipitation_mm"] == 0.0
    assert extreme["precipitation_imputed"] is True
    assert records[0]["precipitation_imputed"] is False
    assert stats.imputed == 1


def test_weather_converts_units_to_celsius_mm_and_kmh():
    payload = {
        "daily_units": {
            "temperature_2m_max": "°F",
            "temperature_2m_min": "°F",
            "precipitation_sum": "inch",
            "wind_speed_10m_max": "m/s",
        },
        "daily": {
            "time": ["2026-11-03"],
            "temperature_2m_max": [95.0],
            "temperature_2m_min": [68.0],
            "precipitation_sum": [1.0],
            "wind_speed_10m_max": [10.0],
            "weather_code": [61],
        },
    }

    (record,), _ = transform_weather(payload)

    assert record["temp_max_c"] == 35.0
    assert record["temp_min_c"] == 20.0
    assert record["precipitation_mm"] == 25.4
    assert record["wind_speed_max_kmh"] == 36.0
    assert record["is_rainy_day"] is True


def test_weather_removes_duplicate_days_keeping_the_last():
    payload = {
        "daily": {
            "time": ["2026-11-03", "2026-11-03"],
            "temperature_2m_max": [30.0, 31.0],
            "temperature_2m_min": [20.0, 21.0],
        }
    }

    records, stats = transform_weather(payload)

    assert len(records) == 1
    assert records[0]["temp_max_c"] == 31.0
    assert stats.dropped_duplicates == 1


def test_weather_drops_an_invalid_date_as_corrupted():
    payload = {
        "daily": {
            "time": ["2026-13-45"],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [20.0],
        }
    }

    records, stats = transform_weather(payload)

    assert records == []
    assert stats.dropped_corrupted == 1


def test_weather_handles_an_empty_response():
    records, stats = transform_weather({})

    assert records == []
    assert stats.records_in == 0


@pytest.mark.parametrize(
    ("temperature", "expected"),
    [(29.9, "mild"), (30.0, "warm"), (35.0, "hot"), (38.0, "extreme")],
)
def test_heat_category_boundaries(temperature, expected):
    assert heat_category(temperature) == expected


# ----------------------------------------------------------------------------------- fx


def fx_payload(rows):
    return {"bmx": {"series": [{"idSerie": "SF43718", "datos": rows}]}}


FX_ROWS = [
    {"fecha": "04/11/2026", "dato": "18.00"},
    {"fecha": "05/11/2026", "dato": "18.36"},
    {"fecha": "06/11/2026", "dato": "N/E"},
    {"fecha": "07/11/2026", "dato": "18.36"},
    {"fecha": "08/11/2026", "dato": "250"},
    {"fecha": "31/02/2026", "dato": "18.0"},
]


def test_fx_cleans_rows_and_converts_dates_to_iso():
    records, stats = transform_fx(fx_payload(FX_ROWS), previous_rate=17.9)

    assert [r["date"] for r in records] == ["2026-11-04", "2026-11-05", "2026-11-07"]
    assert stats.records_in == 6
    assert stats.dropped_missing == 1  # "N/E"
    assert stats.dropped_corrupted == 2  # rate of 250 and the date 31/02


def test_fx_computes_change_as_decimals_and_flags_large_moves():
    records, _ = transform_fx(fx_payload(FX_ROWS), previous_rate=17.9)
    first, second, third = records

    assert first["usd_mxn_change"] == 0.1
    assert first["usd_mxn_change_pct"] == 0.005587
    assert first["peso_trend"] == "weakening"
    assert first["is_large_move"] is False
    assert second["usd_mxn_change_pct"] == 0.02
    assert second["is_large_move"] is True
    assert third["usd_mxn_change"] == 0.0
    assert third["peso_trend"] == "stable"


def test_fx_has_no_change_for_the_first_day_when_there_is_no_history():
    records, _ = transform_fx(fx_payload(FX_ROWS[:2]))

    assert records[0]["usd_mxn_change"] is None
    assert records[0]["usd_mxn_change_pct"] is None
    assert records[0]["peso_trend"] is None
    assert records[0]["is_large_move"] is False
    assert records[1]["usd_mxn_change"] == 0.36


def test_fx_removes_duplicate_dates_and_handles_empty_or_odd_payloads():
    rows = [{"fecha": "04/11/2026", "dato": "18.0"}, {"fecha": "04/11/2026", "dato": "18.5"}]

    records, stats = transform_fx(fx_payload(rows))

    assert [r["usd_mxn_rate"] for r in records] == [18.5]
    assert stats.dropped_duplicates == 1
    assert transform_fx({})[0] == []
    assert transform_fx(fx_payload(["not a dict"]))[1].dropped_corrupted == 1


# ---------------------------------------------------------------------------- earthquakes


def feature(event_id="us1", mag=4.6, coords=(-99.1, 16.8, 25.0), **props):
    base = {
        "mag": mag,
        "time": 1_700_000_000_000,
        "place": "10 km S of Town, Mexico",
        "felt": 3,
        "alert": "green",
        "tsunami": 0,
        "sig": 326,
        "status": "reviewed",
        "magType": "mb",
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us1",
    }
    base.update(props)
    return {
        "type": "Feature",
        "id": event_id,
        "properties": base,
        "geometry": {"type": "Point", "coordinates": list(coords)},
    }


def test_earthquake_is_flattened_and_standardized():
    (record,), stats = transform_earthquakes({"features": [feature()]})

    assert record["_id"] == "us1"
    assert record["event_time"] == "2023-11-14T22:13:20Z"
    assert record["event_date"] == "2023-11-14"
    assert record["longitude"] == -99.1  # GeoJSON order is [lon, lat, depth]
    assert record["latitude"] == 16.8
    assert record["depth_km"] == 25.0
    assert record["magnitude_type"] == "mb"
    assert record["review_status"] == "reviewed"
    assert stats.records_out == 1


def test_earthquake_derived_fields():
    (far,), _ = transform_earthquakes({"features": [feature()]})
    (near,), _ = transform_earthquakes({"features": [feature("us2", coords=(-90.5, 19.0, 10.0))]})
    (big,), _ = transform_earthquakes({"features": [feature("us3", mag=5.0)]})
    (tsunami,), _ = transform_earthquakes({"features": [feature("us4", tsunami=1)]})

    assert far["magnitude_class"] == "light"
    assert far["depth_class"] == "shallow"
    assert 1050 < far["distance_to_merida_km"] < 1150
    assert far["is_near_merida"] is False
    assert far["is_significant"] is False
    assert near["distance_to_merida_km"] < 300
    assert near["is_near_merida"] is True
    assert big["is_significant"] is True
    assert tsunami["is_significant"] is True
    assert tsunami["tsunami"] is True


def test_earthquake_drops_missing_corrupted_and_duplicate_events():
    payload = {
        "features": [
            feature("ok"),
            feature("no-mag", mag=None),
            feature(None),
            feature("bad-lat", coords=(-99.0, 95.0, 10.0)),
            feature("ok"),
            "garbage",
        ]
    }

    records, stats = transform_earthquakes(payload)

    assert [r["event_id"] for r in records] == ["ok"]
    assert stats.records_in == 6
    assert stats.dropped_missing == 2
    assert stats.dropped_corrupted == 2  # the impossible latitude and the non-dict entry
    assert stats.dropped_duplicates == 1


def test_earthquake_imputes_non_critical_gaps():
    event = feature(felt=None, alert=None, place=None)

    (record,), stats = transform_earthquakes({"features": [event]})

    assert record["felt_reports"] == 0
    assert record["alert_level"] == "none"
    assert record["place"] == "unknown place"
    assert stats.imputed == 1


@pytest.mark.parametrize(
    ("magnitude", "expected"),
    [(3.9, "minor"), (4.0, "light"), (5.0, "moderate"), (6.0, "strong"), (7.0, "major")],
)
def test_magnitude_class_boundaries(magnitude, expected):
    assert magnitude_class(magnitude) == expected


@pytest.mark.parametrize(
    ("depth", "expected"),
    [
        (10, "shallow"),
        (70, "intermediate"),
        (300, "intermediate"),
        (301, "deep"),
        (None, "unknown"),
    ],
)
def test_depth_class_boundaries(depth, expected):
    assert depth_class(depth) == expected
