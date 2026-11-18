"""Runs the real dashboard script with Streamlit's AppTest, with MongoDB replaced by sample data."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import queries
from dashboard_data import sample_earthquakes, sample_overview, sample_run_documents
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "streamlit_app" / "app.py")


@pytest.fixture
def with_data(monkeypatch):
    monkeypatch.setattr(queries, "check_connection", lambda: None)
    monkeypatch.setattr(queries, "load_overview", sample_overview)
    monkeypatch.setattr(queries, "load_earthquakes", sample_earthquakes)
    monkeypatch.setattr(queries, "load_runs", lambda: queries.flatten_runs(sample_run_documents()))
    monkeypatch.setattr(
        queries,
        "collection_counts",
        lambda: pd.DataFrame({"collection": ["raw_fx"], "documents": [1]}),
    )


def run_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=30).run()


def metrics(app: AppTest) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


def test_dashboard_renders_headline_numbers_and_tabs(with_data):
    app = run_app()

    assert not app.exception
    assert metrics(app) == {
        "Latest max temperature": "35.0 °C",
        "Latest USD/MXN": "18.10",
        "Earthquakes": "5",
        "Strongest earthquake": "M 6.3",
        "Extreme heat days": "1",
    }
    assert [tab.label for tab in app.tabs] == [
        "Weather and exchange rate",
        "Earthquakes",
        "Pipeline health",
    ]


def test_magnitude_slider_updates_the_earthquake_numbers(with_data):
    app = run_app()

    app.sidebar.slider[0].set_value(5.0).run()

    assert not app.exception
    assert metrics(app)["Earthquakes"] == "2"
    assert metrics(app)["Strongest earthquake"] == "M 6.3"


def test_proximity_checkbox_and_date_range_filter_the_earthquakes(with_data):
    app = run_app()

    app.sidebar.checkbox[0].check().run()
    assert metrics(app)["Earthquakes"] == "3"

    app.sidebar.date_input[0].set_value((date(2026, 11, 1), date(2026, 11, 3))).run()
    assert not app.exception
    assert metrics(app)["Earthquakes"] == "2"
    assert metrics(app)["Extreme heat days"] == "1"


def test_empty_filter_result_shows_guidance_instead_of_failing(with_data):
    app = run_app()

    app.sidebar.slider[0].set_value(7.0).run()

    assert not app.exception
    assert metrics(app)["Strongest earthquake"] == "n/a"
    assert any("No earthquakes match" in info.value for info in app.info)


def test_incomplete_date_range_asks_for_an_end_date(with_data):
    app = run_app()

    app.sidebar.date_input[0].set_value((date(2026, 11, 2),)).run()

    assert not app.exception
    assert any("end date" in info.value for info in app.info)


def test_no_processed_data_tells_the_user_what_to_do(monkeypatch, with_data):
    monkeypatch.setattr(queries, "load_overview", pd.DataFrame)

    app = run_app()

    assert not app.exception
    assert any("main_pipeline" in info.value for info in app.info)
    assert not app.metric


def test_connection_error_is_shown_and_the_page_stops(monkeypatch, with_data):
    monkeypatch.setattr(queries, "check_connection", lambda: "connection refused")

    app = run_app()

    assert not app.exception
    assert any("connection refused" in error.value for error in app.error)
    assert not app.metric
