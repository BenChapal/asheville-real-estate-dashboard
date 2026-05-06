import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.colors as mcolors
import numpy as np
import json
import requests
import plotly.graph_objects as go
from pathlib import Path

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Asheville Real Estate Market",
    page_icon="🏡",
    layout="wide",
)

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
CSV_PATH   = str(BASE_DIR / "asheville_market_data.csv")
USAGE_PATH = BASE_DIR / "api_usage.json"
MONTHLY_LIMIT = 50
WARN_THRESHOLD = 40

HISTORY_MONTHS = [
    "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"
]
MONTH_LABELS = ["Dec '25", "Jan '26", "Feb '26", "Mar '26", "Apr '26", "May '26"]

SALE_HIST_COLS = [f"saleData.history.{m}.medianPrice" for m in HISTORY_MONTHS]
RENT_HIST_COLS = [f"rentalData.history.{m}.medianRent" for m in HISTORY_MONTHS]

# Colorblind-friendly qualitative palette (15 colors)
PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
]

def dollar(x):
    """Format a number as $1,234,567."""
    return f"${x:,.0f}"

def fmt_axis_dollars(x, _):
    if x >= 1_000_000:
        return f"${x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"${x/1_000:.0f}K"
    return f"${x:.0f}"


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv(CSV_PATH, dtype={"zipCode": str})
    # If multiple pulls exist, keep only the most recent row per zip code
    if "pulled_at" in df.columns:
        df["pulled_at"] = pd.to_datetime(df["pulled_at"])
        df = (
            df.sort_values("pulled_at")
              .groupby("zipCode", as_index=False)
              .last()
        )
    df = df.sort_values("saleData.medianPrice", ascending=False).reset_index(drop=True)
    return df


def load_usage() -> dict:
    if USAGE_PATH.exists():
        with open(USAGE_PATH) as f:
            return json.load(f)
    return {"month": "—", "calls_used": 0, "limit": MONTHLY_LIMIT, "pulls": []}


df = load_data()
neighborhoods = df["neighborhood"].tolist()
colors = PALETTE[: len(neighborhoods)]

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🏡 Asheville Area Real Estate Market Dashboard")
st.caption("Buncombe County, NC  ·  Data sourced from Rentcast API")

# Last-updated timestamp (from CSV pulled_at column if available)
if "pulled_at" in df.columns:
    latest_pull = pd.to_datetime(df["pulled_at"]).max()
    last_updated_str = latest_pull.strftime("%-d %b %Y, %-I:%M %p")
else:
    last_updated_str = "Original load (no refresh logged)"

# API usage status bar
usage      = load_usage()
calls_used = usage["calls_used"]
remaining  = usage["limit"] - calls_used
pct_used   = calls_used / usage["limit"]

hdr_left, hdr_right = st.columns([3, 2])
with hdr_left:
    st.markdown(f"🕒 **Last updated:** {last_updated_str}")
with hdr_right:
    bar_color = "#e74c3c" if calls_used >= WARN_THRESHOLD else "#2ecc71"
    st.markdown(
        f"**API usage — {usage['month']}:** "
        f"<span style='color:{bar_color};font-weight:bold'>{calls_used}/{usage['limit']} calls used</span> "
        f"&nbsp;·&nbsp; {remaining} remaining",
        unsafe_allow_html=True,
    )
    st.progress(min(pct_used, 1.0))
    if calls_used >= WARN_THRESHOLD:
        st.warning(
            f"⚠️ {calls_used}/{usage['limit']} API calls used this month. "
            f"Only {remaining} calls left — enough for "
            f"{'1 more' if remaining >= 15 else 'no more'} full refresh."
        )

st.divider()

# ── KPI tiles ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Median Sale Price (county)", dollar(df["saleData.medianPrice"].median()))
k2.metric("Avg Sale Price (county)", dollar(df["saleData.averagePrice"].median()))
k3.metric("Median Rent (county)", dollar(df["rentalData.medianRent"].median()))
k4.metric("Avg Days on Market (sale)", f"{df['saleData.averageDaysOnMarket'].mean():.0f} days")
k5.metric("Total Active Listings", f"{df['saleData.totalListings'].sum():,}")

st.divider()

# ── Shared figure style ────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "#0e1117",
    "axes.facecolor": "#0e1117",
    "axes.edgecolor": "#444",
    "axes.labelcolor": "#e0e0e0",
    "xtick.color": "#e0e0e0",
    "ytick.color": "#e0e0e0",
    "text.color": "#e0e0e0",
    "grid.color": "#333",
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "font.size": 11,
})

def bar_chart(ax, values, labels, title, color_list, horizontal=False):
    if horizontal:
        bars = ax.barh(labels, values, color=color_list, edgecolor="none", height=0.65)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_axis_dollars))
        ax.set_xlabel("Price (USD)")
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.5)
        # Value labels
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + bar.get_width() * 0.01,
                bar.get_y() + bar.get_height() / 2,
                dollar(val),
                va="center", ha="left", fontsize=9, color="#e0e0e0",
            )
    else:
        bars = ax.bar(labels, values, color=color_list, edgecolor="none", width=0.65)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_axis_dollars))
        ax.set_ylabel("Price (USD)")
        ax.grid(axis="y", alpha=0.5)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + bar.get_height() * 0.01,
                dollar(val),
                ha="center", va="bottom", fontsize=8, color="#e0e0e0",
            )
    ax.set_title(title, pad=14, fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)


# ── Row 1: Bar charts ─────────────────────────────────────────────────────────
st.subheader("Current Market Snapshot")
col_a, col_b = st.columns(2)

with col_a:
    fig, ax = plt.subplots(figsize=(7, 6))
    bar_chart(
        ax,
        df["saleData.medianPrice"].values,
        df["neighborhood"].values,
        "Median Sale Price by Neighborhood",
        colors,
        horizontal=True,
    )
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

with col_b:
    fig, ax = plt.subplots(figsize=(7, 6))
    rent_df = df.sort_values("rentalData.medianRent", ascending=False)
    rent_colors = [PALETTE[df[df.neighborhood == n].index[0]] for n in rent_df["neighborhood"]]
    bar_chart(
        ax,
        rent_df["rentalData.medianRent"].values,
        rent_df["neighborhood"].values,
        "Median Monthly Rent by Neighborhood",
        rent_colors,
        horizontal=True,
    )
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

st.divider()

# ── Map ───────────────────────────────────────────────────────────────────────
st.subheader("Zip Code Map — Buncombe County")

@st.cache_data(show_spinner="Loading zip code boundaries…")
def load_geojson(zip_codes):
    zip_list = "','".join(str(z) for z in zip_codes)
    url = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb"
        "/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query"
        f"?where=ZCTA5+IN+('{zip_list}')&outFields=ZCTA5&f=geojson&outSR=4326"
    )
    return requests.get(url, timeout=20).json()

map_metric = st.radio(
    "Color zip codes by:",
    ["Median Sale Price", "Median Rent", "Sale Days on Market"],
    horizontal=True,
)

metric_col_map = {
    "Median Sale Price":   ("saleData.medianPrice",        "YlOrRd", "$"),
    "Median Rent":         ("rentalData.medianRent",       "YlGn",   "$"),
    "Sale Days on Market": ("saleData.averageDaysOnMarket","Blues",  ""),
}
metric_col, colorscale, prefix = metric_col_map[map_metric]

geojson = load_geojson(df["zipCode"].tolist())

# Build per-zip lookup
base_cols = ["zipCode", "neighborhood", "saleData.medianPrice",
             "rentalData.medianRent", "saleData.averageDaysOnMarket",
             "saleData.totalListings"]
extra = [metric_col] if metric_col not in base_cols else []
map_df = df[base_cols + extra].copy()
map_df["zipCode"] = map_df["zipCode"].astype(str)

# Hover text
map_df["hover"] = map_df.apply(
    lambda r: (
        f"<b>{r['neighborhood']}</b><br>"
        f"ZIP: {r['zipCode']}<br>"
        f"Median Sale Price: {dollar(r['saleData.medianPrice'])}<br>"
        f"Median Rent: {dollar(r['rentalData.medianRent'])}<br>"
        f"Sale DOM: {r['saleData.averageDaysOnMarket']:.1f} days<br>"
        f"Listings: {int(r['saleData.totalListings']):,}"
    ),
    axis=1,
)

fig_map = go.Figure(go.Choroplethmapbox(
    geojson=geojson,
    locations=map_df["zipCode"],
    z=map_df[metric_col],
    featureidkey="properties.ZCTA5",
    colorscale=colorscale,
    marker_opacity=0.5,
    marker_line_width=1.5,
    marker_line_color="white",
    text=map_df["hover"],
    hovertemplate="%{text}<extra></extra>",
    colorbar=dict(
        title=dict(text=map_metric, font=dict(color="#e0e0e0")),
        tickfont=dict(color="#e0e0e0"),
        tickprefix=prefix,
        thickness=14,
        len=0.7,
    ),
))

fig_map.update_layout(
    mapbox_style="carto-darkmatter",
    mapbox_zoom=9.2,
    mapbox_center={"lat": 35.57, "lon": -82.55},
    margin=dict(l=0, r=0, t=0, b=0),
    height=540,
    paper_bgcolor="#0e1117",
    font_color="#e0e0e0",
)

st.plotly_chart(fig_map, use_container_width=True)

st.divider()

# ── Row 2: Trend lines ────────────────────────────────────────────────────────
st.subheader("6-Month Price Trends  (Dec 2025 – May 2026)")

# Neighborhood filter (multiselect to avoid chart clutter)
default_hoods = neighborhoods[:6]
selected = st.multiselect(
    "Filter neighborhoods (applies to both trend charts):",
    options=neighborhoods,
    default=default_hoods,
)

if not selected:
    st.warning("Select at least one neighborhood to display trends.")
else:
    mask = df["neighborhood"].isin(selected)
    dfs = df[mask].reset_index(drop=True)

    col_c, col_d = st.columns(2)

    # Sale price trend
    with col_c:
        fig, ax = plt.subplots(figsize=(7, 5))
        for i, row in dfs.iterrows():
            color = PALETTE[neighborhoods.index(row["neighborhood"]) % len(PALETTE)]
            vals = row[SALE_HIST_COLS].values.astype(float)
            ax.plot(MONTH_LABELS, vals, marker="o", linewidth=2, color=color,
                    label=row["neighborhood"], markersize=5)
            ax.annotate(
                row["neighborhood"].split()[0],
                xy=(MONTH_LABELS[-1], vals[-1]),
                xytext=(4, 0), textcoords="offset points",
                fontsize=8, color=color, va="center",
            )
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_axis_dollars))
        ax.set_title("Median Sale Price Trend", pad=14, fontsize=13, fontweight="bold")
        ax.set_ylabel("Median Price (USD)")
        ax.grid(axis="y", alpha=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    # Rent trend
    with col_d:
        fig, ax = plt.subplots(figsize=(7, 5))
        legend_handles = []
        for i, row in dfs.iterrows():
            color = PALETTE[neighborhoods.index(row["neighborhood"]) % len(PALETTE)]
            vals = row[RENT_HIST_COLS].values.astype(float)
            line, = ax.plot(MONTH_LABELS, vals, marker="o", linewidth=2, color=color,
                            label=row["neighborhood"], markersize=5)
            legend_handles.append(line)
            ax.annotate(
                row["neighborhood"].split()[0],
                xy=(MONTH_LABELS[-1], vals[-1]),
                xytext=(4, 0), textcoords="offset points",
                fontsize=8, color=color, va="center",
            )
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_axis_dollars))
        ax.set_title("Median Rent Trend", pad=14, fontsize=13, fontweight="bold")
        ax.set_ylabel("Median Monthly Rent (USD)")
        ax.grid(axis="y", alpha=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    # Shared legend below both trend charts
    ncols = min(len(legend_handles), 5)
    fig_leg, ax_leg = plt.subplots(figsize=(10, max(1, len(legend_handles) / ncols) * 0.45))
    ax_leg.axis("off")
    ax_leg.legend(
        handles=legend_handles,
        loc="center",
        ncol=ncols,
        fontsize=10,
        framealpha=0,
        handlelength=1.5,
        columnspacing=1.2,
    )
    fig_leg.tight_layout(pad=0)
    st.pyplot(fig_leg)
    plt.close(fig_leg)

st.divider()

# ── Summary table ─────────────────────────────────────────────────────────────
st.subheader("Neighborhood Summary Table")

summary = df[[
    "neighborhood",
    "zipCode",
    "saleData.medianPrice",
    "rentalData.medianRent",
    "saleData.averageDaysOnMarket",
    "rentalData.averageDaysOnMarket",
    "saleData.totalListings",
]].copy()

summary.columns = [
    "Neighborhood",
    "Zip Code",
    "Median Sale Price",
    "Median Rent",
    "Sale DOM (days)",
    "Rental DOM (days)",
    "Total Listings",
]

# Compute price-to-rent ratio (annual)
summary["Price/Rent Ratio"] = (
    summary["Median Sale Price"] / (summary["Median Rent"] * 12)
).round(1)

summary = summary.sort_values("Median Sale Price", ascending=False).reset_index(drop=True)

styled = summary.style.format({
    "Median Sale Price": "${:,.0f}",
    "Median Rent": "${:,.0f}",
    "Sale DOM (days)": "{:.1f}",
    "Rental DOM (days)": "{:.1f}",
    "Total Listings": "{:,}",
    "Price/Rent Ratio": "{:.1f}x",
}).background_gradient(
    subset=["Median Sale Price"],
    cmap="Blues",
).background_gradient(
    subset=["Median Rent"],
    cmap="Greens",
).background_gradient(
    subset=["Sale DOM (days)"],
    cmap="Oranges",
).set_properties(**{"text-align": "right"}) \
 .set_table_styles([
    {"selector": "th", "props": [("text-align", "center"), ("font-weight", "bold")]},
])

st.dataframe(styled, use_container_width=True, hide_index=True)

st.caption(
    "Price/Rent Ratio = Median Sale Price ÷ (Median Rent × 12). "
    "Lower values suggest relatively stronger rental returns. "
    "DOM = Days on Market."
)
