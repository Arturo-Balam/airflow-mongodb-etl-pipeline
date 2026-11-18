"""Mexico monitor: dashboard on top of the processed collections in MongoDB."""

from __future__ import annotations

import charts
import filters
import queries
import streamlit as st

st.set_page_config(page_title="Mexico monitor", layout="wide")

st.title("Mexico monitor")
st.caption(
    "Daily weather in Mérida, the USD/MXN exchange rate and earthquakes in Mexico. "
    "The data comes from an Airflow pipeline and is stored in MongoDB."
)

connection_error = queries.check_connection()
if connection_error:
    st.error(
        "Cannot reach MongoDB. Check that the mongodb container is healthy with "
        f"`docker compose ps`. Details: {connection_error}"
    )
    st.stop()

if st.sidebar.button("Reload data"):
    st.cache_data.clear()
    st.rerun()

overview = queries.load_overview()
quakes = queries.load_earthquakes()
runs = queries.load_runs()

if overview.empty:
    st.info(
        "There is no processed data yet. Open Airflow at http://localhost:8080 and trigger "
        "the main_pipeline DAG, then reload this page."
    )
    st.stop()

# ---- filters -------------------------------------------------------------------------
first_day, last_day = overview["date"].min().date(), overview["date"].max().date()
date_range = st.sidebar.date_input(
    "Date range", value=(first_day, last_day), min_value=first_day, max_value=last_day
)
if len(date_range) != 2:
    st.info("Pick an end date to apply the date range.")
    st.stop()
start, end = date_range
min_magnitude = st.sidebar.slider("Minimum magnitude", 2.5, 7.0, 2.5, 0.1)
near_only = st.sidebar.checkbox("Only earthquakes within 1,000 km of Mérida")

view = filters.filter_overview(overview, start, end)
view_quakes = filters.filter_earthquakes(quakes, start, end, min_magnitude, near_only)


# ---- headline numbers ------------------------------------------------------------------
def show(value: float | None, template: str) -> str:
    return "n/a" if value is None else template.format(value)


temperature, temperature_change = filters.latest_with_delta(view, "temp_max_c")
rate, rate_change = filters.latest_with_delta(view, "usd_mxn_rate")
strongest = float(view_quakes["magnitude"].max()) if not view_quakes.empty else None

columns = st.columns(5)
columns[0].metric(
    "Latest max temperature",
    show(temperature, "{:.1f} °C"),
    None if temperature_change is None else f"{temperature_change:+.1f} °C",
    delta_color="off",
)
columns[1].metric(
    "Latest USD/MXN",
    show(rate, "{:.2f}"),
    None if rate_change is None else f"{rate_change:+.2f}",
    delta_color="inverse",  # more pesos per dollar means the peso lost value
)
columns[2].metric("Earthquakes", len(view_quakes))
columns[3].metric("Strongest earthquake", show(strongest, "M {:.1f}"))
columns[4].metric("Extreme heat days", filters.count_true(view, "is_extreme_heat"))

# ---- tabs ----------------------------------------------------------------------------------
weather_tab, quake_tab, health_tab = st.tabs(
    ["Weather and exchange rate", "Earthquakes", "Pipeline health"]
)

with weather_tab:
    if view.empty:
        st.info("No days match the selected date range.")
    else:
        st.subheader("Temperature and USD/MXN")
        st.plotly_chart(charts.weather_fx_chart(view))
        st.subheader("Rainfall")
        st.plotly_chart(charts.rainfall_chart(view))

with quake_tab:
    if view_quakes.empty:
        st.info(
            "No earthquakes match these filters. "
            "Lower the minimum magnitude or widen the date range."
        )
    else:
        map_column, class_column = st.columns([2, 1])
        map_column.plotly_chart(charts.quake_map(view_quakes))
        class_column.subheader("By magnitude class")
        class_column.plotly_chart(charts.magnitude_class_chart(view_quakes))
        st.subheader("Earthquakes per day")
        st.plotly_chart(charts.quakes_per_day_chart(view_quakes))
        st.subheader("Strongest events")
        st.dataframe(filters.top_quakes(view_quakes), hide_index=True)

with health_tab:
    if runs.empty:
        st.info("No pipeline runs are recorded yet. Trigger main_pipeline in Airflow.")
    else:
        last = runs.iloc[0]
        st.write(
            f"The last run finished on {last['finished_at']:%Y-%m-%d at %H:%M} UTC and covered "
            f"{last['window_start']} to {last['window_end']}."
        )
        st.dataframe(runs.drop(columns=["run_id"]).head(10), hide_index=True)
        st.subheader("Records removed by cleaning")
        st.plotly_chart(charts.dropped_records_chart(runs))
    st.subheader("Collections")
    st.dataframe(queries.collection_counts(), hide_index=True)

st.caption(
    "Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). "
    "Exchange rate from Banco de México. Earthquakes from the U.S. Geological Survey."
)
