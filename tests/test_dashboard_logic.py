"""Tests for the dashboard's filters, run flattening and figure builders (no Streamlit run)."""

from datetime import date

import charts
import filters
import pandas as pd
import queries
from dashboard_data import sample_earthquakes, sample_overview, sample_run_documents

# --------------------------------------------------------------------------- filters


def test_filter_overview_keeps_the_inclusive_date_range():
    result = filters.filter_overview(sample_overview(), date(2026, 11, 2), date(2026, 11, 4))

    assert list(result["date"].dt.day) == [2, 3, 4]


def test_filter_earthquakes_applies_date_magnitude_and_proximity():
    quakes = sample_earthquakes()
    everything = (date(2026, 11, 1), date(2026, 11, 5))

    assert len(filters.filter_earthquakes(quakes, *everything, 2.5, False)) == 5
    assert list(filters.filter_earthquakes(quakes, *everything, 5.0, False)["event_id"]) == [
        "c",
        "d",
    ]
    assert list(filters.filter_earthquakes(quakes, *everything, 2.5, True)["event_id"]) == [
        "c",
        "d",
        "e",
    ]
    assert list(
        filters.filter_earthquakes(quakes, date(2026, 11, 3), date(2026, 11, 3), 2.5, False)[
            "event_id"
        ]
    ) == ["c", "d"]


def test_filters_handle_empty_frames():
    empty = pd.DataFrame()

    assert filters.filter_overview(empty, date(2026, 11, 1), date(2026, 11, 2)).empty
    assert filters.filter_earthquakes(empty, date(2026, 11, 1), date(2026, 11, 2), 2.5, True).empty
    assert filters.latest_with_delta(empty, "temp_max_c") == (None, None)
    assert filters.count_true(empty, "is_extreme_heat") == 0


def test_latest_with_delta_skips_missing_values():
    overview = sample_overview()

    assert filters.latest_with_delta(overview, "temp_max_c") == (35.0, -1.0)
    # the last two days have no rate (weekend), so the latest real rate is 18.1 vs 18.2 before it
    rate, change = filters.latest_with_delta(overview, "usd_mxn_rate")
    assert rate == 18.1
    assert round(change, 2) == -0.1


def test_latest_with_delta_has_no_change_with_a_single_value():
    one_day = sample_overview().head(1)

    assert filters.latest_with_delta(one_day, "temp_max_c") == (33.0, None)


def test_count_true_counts_flags():
    assert filters.count_true(sample_overview(), "is_extreme_heat") == 1


def test_top_quakes_lists_the_strongest_first_with_display_names():
    table = filters.top_quakes(sample_earthquakes(), n=2)

    assert list(table["Magnitude"]) == [6.3, 5.1]
    assert list(table.columns) == [
        "Time (UTC)",
        "Magnitude",
        "Place",
        "Depth (km)",
        "Distance to Mérida (km)",
    ]
    assert table["Time (UTC)"].iloc[0] == "2026-11-03 20:45"


# ------------------------------------------------------------------------------ runs


def test_flatten_runs_builds_one_row_per_run_with_dropped_totals():
    runs = queries.flatten_runs(sample_run_documents())

    assert list(runs["run_id"]) == ["run-2", "run-1"]
    newest = runs.iloc[0]
    assert newest["window_start"] == "2026-11-01"
    assert newest["weather_out"] == 7
    assert newest["fx_dropped"] == 1
    assert newest["earthquakes_dropped"] == 2
    assert str(runs["finished_at"].dt.tz) == "UTC"


def test_flatten_runs_handles_no_runs_and_incomplete_documents():
    assert queries.flatten_runs([]).empty

    runs = queries.flatten_runs([{"_id": "partial", "finished_at": None}])

    assert runs.iloc[0]["weather_dropped"] == 0
    assert pd.isna(runs.iloc[0]["weather_out"])


# ---------------------------------------------------------------------------- charts


def test_weather_fx_chart_puts_the_exchange_rate_on_a_second_axis():
    fig = charts.weather_fx_chart(sample_overview())

    assert [trace.name for trace in fig.data] == [
        "Max temperature (°C)",
        "Min temperature (°C)",
        "USD/MXN",
    ]
    assert fig.data[2].yaxis == "y2"
    assert fig.data[2].connectgaps is True


def test_rainfall_chart_is_a_bar_chart_of_the_daily_totals():
    fig = charts.rainfall_chart(sample_overview())

    assert fig.data[0].type == "bar"
    assert list(fig.data[0].y) == [0.0, 0.0, 1.5, 4.0, 0.0]


def test_quake_map_plots_every_event_plus_merida():
    quakes = sample_earthquakes()

    fig = charts.quake_map(quakes)

    assert fig.data[0].type == "scattermap"
    assert len(fig.data[0].lat) == len(quakes)
    assert fig.data[0].marker.sizemin == 6  # small events must stay visible
    assert fig.data[-1].name == "Mérida"
    assert fig.data[-1].lat[0] == charts.MERIDA[0]


def test_magnitude_class_chart_orders_classes_from_minor_to_major():
    fig = charts.magnitude_class_chart(sample_earthquakes())

    assert fig.data[0].type == "pie"
    assert list(fig.data[0].labels) == ["minor", "light", "moderate", "strong"]
    assert list(fig.data[0].values) == [2, 1, 1, 1]


def test_quakes_per_day_chart_counts_events_by_date():
    fig = charts.quakes_per_day_chart(sample_earthquakes())

    assert fig.data[0].type == "bar"
    assert sum(fig.data[0].y) == 5
    assert max(fig.data[0].y) == 2  # two events on 2026-11-03


def test_dropped_records_chart_has_one_stacked_series_per_source():
    runs = queries.flatten_runs(sample_run_documents())

    fig = charts.dropped_records_chart(runs)

    assert sorted(trace.name for trace in fig.data) == ["earthquakes", "fx", "weather"]
    assert fig.layout.barmode == "stack"
