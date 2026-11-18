"""Plotly figure builders for the dashboard (a DataFrame goes in, a figure comes out)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

MERIDA = (20.9674, -89.5926)
TEMP_MAX_COLOR = "#d1495b"
TEMP_MIN_COLOR = "#2e86ab"
FX_COLOR = "#3d4a52"
RAIN_COLOR = "#2e86ab"
QUAKE_COLOR = "#b3452f"
# Starts at orange, not pale yellow, so small events stay visible on the light map
QUAKE_SCALE = ["#f4a261", "#e76f51", "#c1121f", "#6a040f"]
MAGNITUDE_ORDER = ["minor", "light", "moderate", "strong", "major"]
MAGNITUDE_COLORS = {
    "minor": "#fdd49e",
    "light": "#fdbb84",
    "moderate": "#e34a33",
    "strong": "#b30000",
    "major": "#4d0000",
}
LAYOUT = {"margin": {"l": 10, "r": 10, "t": 30, "b": 10}, "hovermode": "x unified"}


def weather_fx_chart(overview: pd.DataFrame) -> go.Figure:
    """Max and min temperature (left axis) against the USD/MXN rate (right axis)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=overview["date"],
            y=overview["temp_max_c"],
            name="Max temperature (°C)",
            mode="lines+markers",
            line={"color": TEMP_MAX_COLOR},
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=overview["date"],
            y=overview["temp_min_c"],
            name="Min temperature (°C)",
            mode="lines+markers",
            line={"color": TEMP_MIN_COLOR},
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=overview["date"],
            y=overview["usd_mxn_rate"],
            name="USD/MXN",
            mode="lines+markers",
            connectgaps=True,  # the exchange rate has no value on weekends
            line={"color": FX_COLOR, "dash": "dot"},
        ),
        secondary_y=True,
    )
    fig.update_yaxes(title_text="Temperature (°C)", secondary_y=False)
    fig.update_yaxes(title_text="Pesos per dollar", secondary_y=True, showgrid=False)
    fig.update_layout(legend={"orientation": "h", "y": 1.12, "x": 0}, **LAYOUT)
    return fig


def rainfall_chart(overview: pd.DataFrame) -> go.Figure:
    fig = px.bar(overview, x="date", y="precipitation_mm", color_discrete_sequence=[RAIN_COLOR])
    fig.update_layout(xaxis_title=None, yaxis_title="Rainfall (mm)", **LAYOUT)
    return fig


def quake_map(quakes: pd.DataFrame) -> go.Figure:
    """Earthquakes sized and colored by magnitude, with Mérida marked for reference."""
    data = quakes.assign(marker_size=quakes["magnitude"].clip(lower=0.5))
    fig = px.scatter_map(
        data,
        lat="latitude",
        lon="longitude",
        size="marker_size",
        color="magnitude",
        color_continuous_scale=QUAKE_SCALE,
        opacity=0.85,
        size_max=18,
        zoom=3.2,
        center={"lat": 23.0, "lon": -102.0},
        map_style="open-street-map",
        hover_name="place",
        hover_data={
            "event_time": True,
            "magnitude": True,
            "depth_km": True,
            "distance_to_merida_km": True,
            "latitude": False,
            "longitude": False,
            "marker_size": False,
        },
        labels={"magnitude": "Magnitude"},
    )
    fig.update_traces(marker={"sizemin": 6})  # the smallest events stay clickable
    fig.add_trace(
        go.Scattermap(
            lat=[MERIDA[0]],
            lon=[MERIDA[1]],
            mode="markers+text",
            text=["Mérida"],
            textposition="top right",
            marker={"size": 11, "color": "#16262e"},
            name="Mérida",
            hoverinfo="skip",
        )
    )
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=460)
    return fig


def magnitude_class_chart(quakes: pd.DataFrame) -> go.Figure:
    counts = quakes["magnitude_class"].value_counts().reindex(MAGNITUDE_ORDER).dropna()
    fig = px.pie(
        names=counts.index,
        values=counts.values,
        hole=0.5,
        color=counts.index,
        color_discrete_map=MAGNITUDE_COLORS,
    )
    fig.update_traces(sort=False, textinfo="label+value")
    fig.update_layout(showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10})
    return fig


def quakes_per_day_chart(quakes: pd.DataFrame) -> go.Figure:
    per_day = quakes.groupby("event_date").size().reset_index(name="earthquakes")
    fig = px.bar(per_day, x="event_date", y="earthquakes", color_discrete_sequence=[QUAKE_COLOR])
    fig.update_layout(xaxis_title=None, yaxis_title="Earthquakes", **LAYOUT)
    return fig


def dropped_records_chart(runs: pd.DataFrame) -> go.Figure:
    """Records removed by the cleaning step in each run, stacked by source."""
    long = runs.melt(
        id_vars="finished_at",
        value_vars=["weather_dropped", "fx_dropped", "earthquakes_dropped"],
        var_name="source",
        value_name="dropped",
    )
    long["source"] = long["source"].str.replace("_dropped", "", regex=False)
    fig = px.bar(long, x="finished_at", y="dropped", color="source", barmode="stack")
    fig.update_layout(xaxis_title="Run finished", yaxis_title="Dropped records", **LAYOUT)
    return fig
