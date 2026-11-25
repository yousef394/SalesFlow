import os
from pathlib import Path
from textwrap import dedent

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from src import pipeline_status
from src.config import get_engine

from src.visuals import (
    revenue_over_time,
    profit_over_time,
    revenue_by_category,
    profit_by_category,
    revenue_by_subcategory,
    revenue_by_manufacturer,
    profit_by_manufacturer,
    revenue_by_segment,
    profit_by_segment,
    revenue_by_region,
    profit_by_region,
    discount_vs_profit,
    discount_vs_profit_margin,
)


# ======================================================================
# PAGE CONFIG
# ======================================================================

st.set_page_config(
    page_title="Sales Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ======================================================================
# DESIGN TOKENS
# ======================================================================

INK = "#0B1B2B"  # headings / sidebar
SLATE = "#5B6B7C"  # secondary text
MIST = "#98A6B5"  # tertiary text
LINE = "#E3E8EE"  # borders
CANVAS = "#F5F7FA"  # page background
TEAL = "#0F9D8A"  # primary accent (revenue / positive)
INDIGO = "#4F46E5"  # secondary accent (profit)
AMBER = "#F59E0B"  # highlight (margin)
ROSE = "#E11D48"  # negative


def html_block(text):
    """Strip indentation so Streamlit doesn't treat the HTML as a code block."""
    return "\n".join(line.strip() for line in dedent(text).strip("\n").splitlines())


def inject_css():
    st.markdown(
        html_block(
            f"""
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

            html, body, [class*="css"], .stMarkdown, button, input {{
                font-family: 'Plus Jakarta Sans', -apple-system, 'Segoe UI', sans-serif;
            }}

            /* ---------- Global ---------- */
            .stApp {{ background: {CANVAS}; }}
            .block-container {{
                max-width: 1480px;
                padding-top: 1.5rem;
                padding-bottom: 3rem;
            }}
            header[data-testid="stHeader"] {{ background: transparent; }}
            #MainMenu, footer {{ visibility: hidden; }}

            h1, h2, h3, h4 {{
                color: {INK} !important;
                letter-spacing: -0.02em;
                font-weight: 700 !important;
            }}

            /* ---------- Sidebar ---------- */
            [data-testid="stSidebar"] {{
                background: {INK};
                border-right: 1px solid #16293D;
            }}
            [data-testid="stSidebar"] * {{ color: #D5DEE8; }}
            [data-testid="stSidebar"] hr {{ border-color: #1E3248; }}
            [data-testid="stSidebar"] h3 {{
                color: #FFFFFF !important;
                font-size: 0.95rem !important;
            }}

            /* ---------- Hero ---------- */
            .hero {{
                background:
                    radial-gradient(circle at 85% 20%, rgba(15,157,138,.35), transparent 45%),
                    radial-gradient(circle at 10% 90%, rgba(79,70,229,.35), transparent 50%),
                    {INK};
                border-radius: 20px;
                padding: 2rem 2.4rem;
                margin-bottom: 1.4rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 1.5rem;
            }}
            .hero-title {{
                color: #FFFFFF;
                font-size: 2rem;
                font-weight: 800;
                letter-spacing: -0.03em;
                margin: 0;
            }}
            .hero-sub {{
                color: #AFC0D1;
                font-size: 0.98rem;
                margin: 0.35rem 0 0 0;
                max-width: 640px;
            }}
            .hero-badge {{
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                background: rgba(15,157,138,.18);
                border: 1px solid rgba(15,157,138,.5);
                color: #7EE6D4;
                padding: 0.45rem 0.9rem;
                border-radius: 999px;
                font-size: 0.82rem;
                font-weight: 600;
                white-space: nowrap;
            }}
            .hero-dot {{
                width: 8px; height: 8px; border-radius: 50%;
                background: #34D6BE;
                box-shadow: 0 0 0 4px rgba(52,214,190,.2);
            }}

            /* ---------- Tabs ---------- */
            [data-baseweb="tab-list"] {{
                gap: 6px;
                background: #FFFFFF;
                padding: 6px;
                border-radius: 14px;
                border: 1px solid {LINE};
                width: fit-content;
            }}
            [data-baseweb="tab-highlight"],
            [data-baseweb="tab-border"] {{ display: none !important; }}
            button[data-baseweb="tab"] {{
                height: 42px;
                padding: 0 18px;
                border-radius: 10px;
                background: transparent;
            }}
            button[data-baseweb="tab"] p {{
                color: {SLATE} !important;
                font-size: 0.9rem !important;
                font-weight: 600 !important;
            }}
            button[data-baseweb="tab"]:hover {{ background: {CANVAS}; }}
            button[data-baseweb="tab"][aria-selected="true"] {{
                background: {INK};
            }}
            button[data-baseweb="tab"][aria-selected="true"] p {{
                color: #FFFFFF !important;
            }}

            /* ---------- KPI cards ---------- */
            .kpi {{
                background: #FFFFFF;
                border: 1px solid {LINE};
                border-radius: 16px;
                padding: 1.15rem 1.3rem;
                min-height: 128px;
                position: relative;
                overflow: hidden;
            }}
            .kpi::before {{
                content: "";
                position: absolute;
                left: 0; top: 0; bottom: 0;
                width: 4px;
                background: var(--accent);
            }}
            .kpi-top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .kpi-label {{
                color: {SLATE};
                font-size: 0.85rem;
                font-weight: 600;
            }}
            .kpi-icon {{
                width: 34px; height: 34px;
                border-radius: 10px;
                display: flex; align-items: center; justify-content: center;
                background: var(--tint);
                font-size: 1rem;
            }}
            .kpi-value {{
                color: {INK};
                font-size: 1.75rem;
                font-weight: 800;
                letter-spacing: -0.03em;
                margin-top: 0.6rem;
                line-height: 1.1;
            }}
            .kpi-desc {{
                color: {MIST};
                font-size: 0.78rem;
                margin-top: 0.4rem;
            }}

            /* ---------- Section heading ---------- */
            .section {{
                margin: 2.2rem 0 1rem 0;
                padding-left: 0.9rem;
                border-left: 4px solid var(--accent, {TEAL});
            }}
            .section-title {{
                color: {INK};
                font-size: 1.4rem;
                font-weight: 750;
                letter-spacing: -0.02em;
                margin: 0;
            }}
            .section-desc {{
                color: {SLATE};
                font-size: 0.9rem;
                margin: 0.2rem 0 0 0;
            }}

            /* ---------- Bordered containers = chart / table cards ---------- */
            [data-testid="stVerticalBlockBorderWrapper"] {{
                border-radius: 16px;
                border-color: {LINE};
            }}
            .card-title {{
                color: {INK};
                font-size: 1rem;
                font-weight: 700;
                margin: 0;
            }}
            .card-desc {{
                color: {MIST};
                font-size: 0.8rem;
                margin: 0.1rem 0 0.6rem 0;
            }}

            /* ---------- Data & metrics ---------- */
            [data-testid="stDataFrame"] {{
                border: 1px solid {LINE};
                border-radius: 12px;
                overflow: hidden;
            }}
            [data-testid="stMetric"] {{
                background: #FFFFFF;
                border: 1px solid {LINE};
                border-radius: 16px;
                padding: 1rem 1.2rem;
            }}
            [data-testid="stMetricLabel"] p {{
                color: {SLATE} !important;
                font-weight: 600 !important;
            }}
            [data-testid="stMetricValue"] {{
                color: {INK} !important;
                font-weight: 800 !important;
            }}
            [data-testid="stAlert"] {{ border-radius: 12px; }}
            .stButton > button, .stDownloadButton > button {{
                border-radius: 10px;
                font-weight: 600;
                background: {INK};
                color: #FFFFFF;
                border: none;
                padding: 0.55rem 1.1rem;
            }}
            .stDownloadButton > button:hover {{ background: {TEAL}; color: #FFFFFF; }}

            /* ---------- Footer ---------- */
            .app-footer {{
                text-align: center;
                color: {MIST};
                font-size: 0.8rem;
                padding: 2.5rem 0 0.5rem 0;
            }}

            @media (max-width: 900px) {{
                .hero {{ flex-direction: column; align-items: flex-start; }}
            }}
            </style>
            """
        ),
        unsafe_allow_html=True,
    )


inject_css()


# ======================================================================
# UI HELPERS
# ======================================================================

def hero(title, subtitle, badge):
    st.markdown(
        html_block(
            f"""
            <div class="hero">
                <div>
                    <p class="hero-title">{title}</p>
                    <p class="hero-sub">{subtitle}</p>
                </div>
                <div class="hero-badge"><span class="hero-dot"></span>{badge}</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def section(title, description, accent=TEAL):
    st.markdown(
        html_block(
            f"""
            <div class="section" style="--accent:{accent};">
                <p class="section-title">{title}</p>
                <p class="section-desc">{description}</p>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def kpi(label, value, description, icon, accent, tint):
    st.markdown(
        html_block(
            f"""
            <div class="kpi" style="--accent:{accent}; --tint:{tint};">
                <div class="kpi-top">
                    <span class="kpi-label">{label}</span>
                    <span class="kpi-icon">{icon}</span>
                </div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-desc">{description}</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def card_header(title, description=None):
    html = f'<p class="card-title">{title}</p>'
    if description:
        html += f'<p class="card-desc">{description}</p>'
    st.markdown(html, unsafe_allow_html=True)


def chart_card(title, description, chart_fn):
    """A bordered card holding one matplotlib chart from visuals.py."""
    with st.container(border=True):
        card_header(title, description)
        st.pyplot(chart_fn(), use_container_width=True)


def table_card(title, description, df, height=None):
    with st.container(border=True):
        card_header(title, description)
        kwargs = {"height": height} if height else {}
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            **kwargs,
        )


def chart_pair(left, right):
    """Two charts side by side. Each arg: (title, description, chart_fn)."""
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        chart_card(*left)
    with c2:
        chart_card(*right)


# ======================================================================
# DATA
# ======================================================================

@st.cache_resource
def get_dwh_engine():
    return get_engine("DWH_DB_NAME")


engine = get_dwh_engine()

# The analytics views are created by the pipeline (its build_views task runs
# sql/analytics.sql). The dashboard only reads them and never creates them.
REQUIRED_VIEWS = [
    "vw_overall_sales_performance",
    "vw_sales_over_time",
    "vw_yearly_performance",
    "vw_category_performance",
    "vw_subcategory_performance",
    "vw_product_performance",
    "vw_manufacturer_performance",
    "vw_segment_performance",
    "vw_region_performance",
    "vw_discount_profitability",
]
REQUIRED_TABLES = ["dim_product", "fact_sales"]


def check_data_ready():
    """Return (ready, reason). Never raises: a missing view or an unreachable database is a state, not a crash."""
    try:
        with engine.connect() as connection:
            missing = [
                name
                for name in REQUIRED_VIEWS + REQUIRED_TABLES
                if not connection.execute(
                    text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
                ).scalar()
            ]
            if missing:
                return False, "Waiting for the pipeline to create: " + ", ".join(missing) + "."
            if not connection.execute(text("SELECT EXISTS (SELECT 1 FROM fact_sales)")).scalar():
                return False, "The warehouse is still empty."
    except Exception:
        return False, "The database is not reachable right now."
    return True, ""


def current_cache_key():
    """Changes when a new pipeline run has (re)built the views, so cached data never outlives its run."""
    try:
        run = pipeline_status.latest_run(engine)
    except Exception:
        run = None
    if run is None:
        return "no-run"
    built = run["stages"].get("build_views", {})
    return f"{run['run_id']}|{built.get('status')}|{built.get('finished_at')}"


@st.cache_data(ttl=600, show_spinner=False)
def load_view(view_name, cache_key):
    return pd.read_sql(f"SELECT * FROM {view_name};", engine)


@st.cache_data(ttl=600, show_spinner=False)
def load_product_names(cache_key):
    return pd.read_sql("SELECT product_key, product_name FROM dim_product", engine)


def render_skeleton(kpis=True):
    cards = "".join('<div class="sk" style="height:110px;flex:1;"></div>' for _ in range(5 if kpis else 3))
    st.markdown(
        html_block(
            f"""
            <style>
                @keyframes sk-pulse {{ 0% {{opacity:.45}} 50% {{opacity:1}} 100% {{opacity:.45}} }}
                .sk {{ background:{LINE}; border-radius:14px; animation: sk-pulse 1.4s ease-in-out infinite; }}
            </style>
            <div style="display:flex;gap:1rem;margin:0.5rem 0 1rem 0;">{cards}</div>
            <div style="display:flex;gap:1rem;">
                <div class="sk" style="height:260px;flex:1;"></div>
                <div class="sk" style="height:260px;flex:1;"></div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def render_pipeline_progress():
    """Which stage of the latest pipeline run is where. Silent if there is no status yet."""
    try:
        run = pipeline_status.latest_run(engine)
    except Exception:
        return
    if run is None:
        return
    icons = {"success": "✅", "running": "⏳", "failed": "❌"}
    lines = [
        f"{icons.get(run['stages'].get(stage, {}).get('status'), '▫️')} {stage}"
        for stage in pipeline_status.STAGES
    ]
    st.caption(f"Latest pipeline run: {run['run_id']}")
    st.markdown("  \n".join(lines))


@st.fragment(run_every=5)
def poll_until_ready():
    if check_data_ready()[0]:
        st.rerun()


@st.fragment(run_every=10)
def poll_forecast():
    if pipeline_status.forecast_state(engine)[0] != "waiting":
        st.rerun()


data_ready, data_reason = check_data_ready()
if not data_ready:
    hero(
        "Sales Analytics Dashboard",
        "Business performance, trends and predictions, powered by your data warehouse.",
        "Waiting for data",
    )
    render_skeleton()
    st.info(data_reason + " This page refreshes by itself as soon as the data is ready.")
    render_pipeline_progress()
    poll_until_ready()
    st.stop()

CACHE_KEY = current_cache_key()

overall = load_view("vw_overall_sales_performance", CACHE_KEY)
yearly = load_view("vw_yearly_performance", CACHE_KEY)
category = load_view("vw_category_performance", CACHE_KEY)
product = load_view("vw_product_performance", CACHE_KEY)
product_names = load_product_names(CACHE_KEY)
segment = load_view("vw_segment_performance", CACHE_KEY)
region = load_view("vw_region_performance", CACHE_KEY)
discount = load_view("vw_discount_profitability", CACHE_KEY)

total_orders = overall["total_orders"].iloc[0]
total_quantity = overall["total_quantity"].iloc[0]
total_revenue = overall["total_revenue"].iloc[0]
total_profit = overall["total_profit"].iloc[0]
profit_margin = overall["profit_margin"].iloc[0]


# ======================================================================
# SIDEBAR
# ======================================================================

with st.sidebar:
    st.markdown(
        html_block(
            """
            <div style="font-size:1.3rem;font-weight:800;color:#FFFFFF;margin-bottom:0.2rem;">
                📊 Sales Analytics
            </div>
            <div style="color:#8FA3B8;font-size:0.82rem;margin-bottom:1rem;">
                Data Warehouse & Business Intelligence
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### What you can explore")
    st.markdown(
        html_block(
            """
            <div style="font-size:0.85rem;line-height:1.9;">
                📈 Business overview & KPIs<br>
                🕒 Time trends<br>
                🗂️ Categories & products<br>
                👥 Segments & regions<br>
                🏷️ Discount impact<br>
                🤖 Sales predictions
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### Data source")
    st.markdown(
        html_block(
            """
            <div style="color:#8FA3B8;font-size:0.82rem;line-height:1.8;">
                PostgreSQL<br>
                Star schema warehouse<br>
                Analytics views
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


# ======================================================================
# HEADER + TABS
# ======================================================================

hero(
    "Sales Analytics Dashboard",
    "Business performance, trends and predictions, "
    "powered by your data warehouse.",
    "Data warehouse connected",
)

tab_overview, tab_products, tab_customers, tab_discount, tab_prediction = st.tabs(
    [
        "📈 Overview",
        "🗂️ Products",
        "👥 Customers & Regions",
        "🏷️ Discounts",
        "🤖 Prediction",
    ]
)


# ----------------------------------------------------------------------
# TAB 1 — OVERVIEW  (KPIs -> time trends -> yearly table)
# ----------------------------------------------------------------------
with tab_overview:
    section(
        "Business overview",
        "Key indicators from the sales data warehouse.",
    )

    k1, k2, k3, k4, k5 = st.columns(5, gap="medium")
    with k1:
        kpi("Total orders", f"{total_orders:,.0f}", "Unique customer orders",
            "🧾", INDIGO, "#EEF0FF")
    with k2:
        kpi("Total quantity", f"{total_quantity:,.0f}", "Units sold",
            "📦", AMBER, "#FEF3DC")
    with k3:
        kpi("Total revenue", f"${total_revenue:,.0f}", "Total sales revenue",
            "💰", TEAL, "#DDF5F1")
    with k4:
        kpi("Total profit", f"${total_profit:,.0f}", "Total generated profit",
            "📈", INDIGO, "#EEF0FF")
    with k5:
        kpi("Profit margin", f"{profit_margin:.2%}", "Profit divided by revenue",
            "🎯", AMBER, "#FEF3DC")

    section(
        "Performance over time",
        "Monthly trends, then the yearly breakdown behind them.",
    )
    chart_pair(
        ("Revenue over time", "Monthly revenue trend.", revenue_over_time),
        ("Profit over time", "Monthly profit trend.", profit_over_time),
    )
    st.write("")
    table_card(
        "Yearly performance",
        "Revenue, profit and profitability by year.",
        yearly,
    )


# ----------------------------------------------------------------------
# TAB 2 — PRODUCTS  (category + manufacturer, each: chart -> table)
# ----------------------------------------------------------------------
with tab_products:
    section(
        "Category performance",
        "How each product category contributes to revenue and profit.",
        INDIGO,
    )
    chart_pair(
        ("Revenue by category", "Share of revenue per category.", revenue_by_category),
        ("Profit by category", "Share of profit per category.", profit_by_category),
    )
    st.write("")
    table_card(
        "Category details",
        "Full category metrics.",
        category,
    )

    section(
        "Subcategories & manufacturers",
        "The strongest product groups and brands.",
        INDIGO,
    )
    chart_pair(
        ("Top 10 subcategories by revenue", "Best-selling subcategories.",
         revenue_by_subcategory),
        ("Top 10 manufacturers by revenue", "Brands bringing in the most revenue.",
         revenue_by_manufacturer),
    )
    st.write("")

    # ---- Prepare the product table ----------------------------------
    prod = product[
        ["product_name", "manufacturer", "category", "subcategory",
         "revenue", "profit", "profit_margin"]
    ].copy()
    # margin is stored as a fraction (0.12) -> show as percent (12.0)
    if prod["profit_margin"].abs().max() <= 1.5:
        prod["profit_margin"] = prod["profit_margin"] * 100

    top20_by_revenue = prod.sort_values("revenue", ascending=False).head(20)
    top20_share = top20_by_revenue["revenue"].sum() / total_revenue
    best_seller = top20_by_revenue.iloc[0]
    best_margin = prod[prod["revenue"] >= prod["revenue"].median()] \
        .sort_values("profit_margin", ascending=False).iloc[0]

    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        chart_card(
            "Top 10 manufacturers by profit",
            "Brands generating the most profit.",
            profit_by_manufacturer,
        )
    with c2:
        kpi("Top 20 products share", f"{top20_share:.1%}",
            "Of total revenue comes from just 20 products",
            "🏆", AMBER, "#FEF3DC")
        st.write("")
        kpi("Best seller", f"${best_seller['revenue']:,.0f}",
            str(best_seller["product_name"])[:48],
            "🥇", TEAL, "#DDF5F1")
        st.write("")
        kpi("Highest margin (above-median sellers)",
            f"{best_margin['profit_margin']:.1f}%",
            str(best_margin["product_name"])[:48],
            "🎯", INDIGO, "#EEF0FF")

    st.write("")
    with st.container(border=True):
        h1, h2 = st.columns([3, 2], gap="medium")
        with h1:
            card_header(
                "Top 20 products",
                "Ranked by the metric you choose. Bars show each product "
                "relative to the best one in the list.",
            )
        with h2:
            sort_label = st.radio(
                "Rank by",
                ["Revenue", "Profit", "Margin"],
                horizontal=True,
                key="top20_sort",
            )

        sort_col = {"Revenue": "revenue", "Profit": "profit",
                    "Margin": "profit_margin"}[sort_label]
        top20 = (
            prod.sort_values(sort_col, ascending=False)
            .head(20)
            .reset_index(drop=True)
        )
        top20.insert(0, "rank", top20.index + 1)
        top20 = top20.rename(columns={
            "rank": "#",
            "product_name": "Product",
            "manufacturer": "Manufacturer",
            "category": "Category",
            "subcategory": "Subcategory",
            "revenue": "Revenue",
            "profit": "Profit",
            "profit_margin": "Margin",
        })

        profit_min = float(min(0, top20["Profit"].min()))
        st.dataframe(
            top20,
            use_container_width=True,
            hide_index=True,
            height=35 * (len(top20) + 1) + 3,
            column_config={
                "#": st.column_config.NumberColumn(width="small"),
                "Product": st.column_config.TextColumn(width="large"),
                "Manufacturer": st.column_config.TextColumn(width="medium"),
                "Category": st.column_config.TextColumn(width="small"),
                "Subcategory": st.column_config.TextColumn(width="small"),
                "Revenue": st.column_config.ProgressColumn(
                    format="$%.0f", min_value=0,
                    max_value=float(top20["Revenue"].max()),
                ),
                "Profit": st.column_config.ProgressColumn(
                    format="$%.0f", min_value=profit_min,
                    max_value=float(top20["Profit"].max()),
                ),
                "Margin": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )


# ----------------------------------------------------------------------
# TAB 3 — CUSTOMERS & REGIONS
# ----------------------------------------------------------------------
with tab_customers:
    section(
        "Customer segments",
        "Compare segments by revenue, profit and margin.",
        AMBER,
    )
    chart_pair(
        ("Revenue by customer segment", "Which segments bring in revenue.",
         revenue_by_segment),
        ("Profit by customer segment", "Which segments are most profitable.",
         profit_by_segment),
    )
    st.write("")
    table_card("Segment details", "Full segment metrics.", segment)

    section(
        "Regional performance",
        "Sales performance across geographic regions.",
        AMBER,
    )
    chart_pair(
        ("Revenue by region", "Revenue per region.", revenue_by_region),
        ("Profit by region", "Profit per region.", profit_by_region),
    )
    st.write("")
    table_card("Region details", "Full regional metrics.", region)


# ----------------------------------------------------------------------
# TAB 4 — DISCOUNTS
# ----------------------------------------------------------------------
with tab_discount:
    section(
        "Discount & profitability",
        "How discount levels affect profit and margin.",
        ROSE,
    )
    chart_pair(
        ("Discount vs profit", "Profit at each discount level.", discount_vs_profit),
        ("Discount vs profit margin", "Margin at each discount level.",
         discount_vs_profit_margin),
    )
    st.write("")
    table_card(
        "Discount details",
        "Profitability by discount level.",
        discount,
    )


# ----------------------------------------------------------------------
# TAB 5 — PREDICTION  (forecast numbers + revenue / profit charts)
# ----------------------------------------------------------------------
def style_plotly(fig, height=360):
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        font=dict(family="Plus Jakarta Sans, sans-serif", color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0, title_text=""),
        hovermode="x unified",
    )
    fig.update_yaxes(gridcolor=LINE, tickprefix="$", separatethousands=True)
    fig.update_xaxes(showgrid=False)
    return fig


def year_bars(forecast_df, hist_df, col):
    parts = []
    if hist_df is not None:
        h = hist_df[["year", col]].rename(columns={col: "value"})
        h["Type"] = "Actual"
        parts.append(h)
    f = forecast_df[["year", col]].rename(columns={col: "value"})
    f["Type"] = "Forecast"
    parts.append(f)
    out = pd.concat(parts).sort_values("year")
    out["year"] = out["year"].astype(int).astype(str)
    return out


with tab_prediction:
    # The forecast is shown only when it belongs to the latest pipeline run
    # (see src/pipeline_status.py), so an old forecast is never presented as current.
    forecast_status, forecast_info = pipeline_status.forecast_state(engine)
    predictions_file = pipeline_status.forecast_file()

    if forecast_status == "waiting":
        render_skeleton(kpis=False)
        st.info(forecast_info["reason"] + " This tab refreshes by itself when the forecast is ready.")
        poll_forecast()
    else:
        if forecast_status == "ready":
            st.caption(
                f"Forecast from pipeline run {forecast_info['run_id']}, "
                f"generated {forecast_info.get('generated_at', 'unknown')}."
            )
        else:
            st.caption(forecast_info["reason"])
        pred = pd.read_csv(predictions_file)

        # ---- Revenue / profit columns --------------------------------
        # predicted_sales is treated as revenue. If prediction.py also
        # outputs predicted_profit, it is used; otherwise profit is
        # estimated with the historical profit margin of the warehouse.
        pred["revenue"] = pred["predicted_sales"]
        if "predicted_profit" in pred.columns:
            pred["profit"] = pred["predicted_profit"]
            profit_note = "Profit comes from the prediction model."
        else:
            pred["profit"] = pred["revenue"] * profit_margin
            profit_note = (
                f"Profit is estimated as predicted revenue × the historical "
                f"profit margin ({profit_margin:.2%})."
            )

        has_actual = "actual_sales" in pred.columns
        pred["date"] = pd.to_datetime(
            dict(year=pred["year"], month=pred["month"], day=1)
        )

        section(
            "Sales forecast",
            "Expected revenue and profit by year, to support planning decisions.",
            TEAL,
        )

        all_years = sorted(pred["year"].unique())
        selected_years = st.multiselect(
            "Years to show",
            options=all_years,
            default=all_years,
        )
        view = pred[pred["year"].isin(selected_years)]

        if view.empty:
            st.info("Select at least one year to see the forecast.")
        else:
            # ---- Yearly summary table ---------------------------------
            yearly_fc = (
                view.groupby("year")
                .agg(revenue=("revenue", "sum"), profit=("profit", "sum"))
                .reset_index()
            )
            yearly_fc["margin"] = yearly_fc["profit"] / yearly_fc["revenue"]

            # Actual history from the warehouse view (if it has the columns)
            hist = None
            if {"year", "revenue", "profit"}.issubset(yearly.columns):
                hist = yearly[["year", "revenue", "profit"]].copy()
                hist["year"] = hist["year"].astype(int)
                hist = hist[hist["year"] < int(yearly_fc["year"].min())]

            combined = pd.concat(
                [x[["year", "revenue"]] for x in (hist, yearly_fc) if x is not None]
            ).sort_values("year")
            combined["growth"] = combined["revenue"].pct_change()
            yearly_fc["growth"] = yearly_fc["year"].map(
                combined.set_index("year")["growth"]
            )

            if has_actual:
                actual_by_year = view.groupby("year")["actual_sales"].sum(min_count=1)
                yearly_fc["actual_revenue"] = yearly_fc["year"].map(actual_by_year)

            # ---- KPI row ----------------------------------------------
            total_pred_revenue = yearly_fc["revenue"].sum()
            total_pred_profit = yearly_fc["profit"].sum()
            last_growth = yearly_fc["growth"].dropna()
            growth_text = f"{last_growth.iloc[-1]:+.1%}" if len(last_growth) else "–"
            span_text = (
                f"{int(yearly_fc['year'].min())} – {int(yearly_fc['year'].max())}"
                if len(yearly_fc) > 1
                else f"{int(yearly_fc['year'].iloc[0])}"
            )

            f1, f2, f3, f4 = st.columns(4, gap="medium")
            with f1:
                kpi("Predicted revenue", f"${total_pred_revenue:,.0f}",
                    "Sum of the selected years", "💰", TEAL, "#DDF5F1")
            with f2:
                kpi("Predicted profit", f"${total_pred_profit:,.0f}",
                    "Sum of the selected years", "📈", INDIGO, "#EEF0FF")
            with f3:
                kpi("Latest yearly growth", growth_text,
                    "Revenue change vs previous year", "🚀", AMBER, "#FEF3DC")
            with f4:
                kpi("Forecast period", span_text,
                    "Years included", "🗓️", INDIGO, "#EEF0FF")

            st.write("")

            # ---- Yearly table -----------------------------------------
            table = yearly_fc.rename(
                columns={
                    "year": "Year",
                    "revenue": "Predicted revenue",
                    "profit": "Predicted profit",
                    "margin": "Profit margin",
                    "growth": "Revenue growth",
                    "actual_revenue": "Actual revenue",
                }
            )
            table["Year"] = table["Year"].astype(int).astype(str)
            table["Profit margin"] = table["Profit margin"].map(lambda v: f"{v:.2%}")
            table["Revenue growth"] = table["Revenue growth"].map(
                lambda v: "–" if pd.isna(v) else f"{v:+.1%}"
            )

            with st.container(border=True):
                card_header(
                    "Forecast by year",
                    "Predicted revenue and profit for each year. " + profit_note,
                )
                st.dataframe(
                    table,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Predicted revenue": st.column_config.NumberColumn(format="$%.0f"),
                        "Predicted profit": st.column_config.NumberColumn(format="$%.0f"),
                        "Actual revenue": st.column_config.NumberColumn(format="$%.0f"),
                    },
                )

            # ---- Revenue charts ---------------------------------------
            section(
                "Revenue forecast",
                "How predicted revenue develops by year and by month.",
                TEAL,
            )

            r1, r2 = st.columns(2, gap="medium")

            with r1:
                with st.container(border=True):
                    card_header("Revenue by year", "Actual history next to the forecast.")
                    bar_df = year_bars(yearly_fc, hist, "revenue")
                    fig = px.bar(
                        bar_df, x="year", y="value", color="Type",
                        color_discrete_map={"Forecast": TEAL, "Actual": "#B6C2CF"},
                    )
                    fig.update_xaxes(title_text="")
                    fig.update_yaxes(title_text="")
                    st.plotly_chart(style_plotly(fig), use_container_width=True)

            with r2:
                with st.container(border=True):
                    card_header("Monthly revenue", "Predicted revenue month by month.")
                    monthly_fc = (
                        view.groupby("date")
                        .agg(revenue=("revenue", "sum"),
                             actual=("actual_sales", "sum") if has_actual
                             else ("revenue", "sum"))
                        .reset_index()
                    )
                    fig = px.line(
                        monthly_fc, x="date", y="revenue", markers=True,
                        color_discrete_sequence=[TEAL],
                    )
                    fig.update_traces(name="Predicted", showlegend=True)
                    if has_actual:
                        fig.add_scatter(
                            x=monthly_fc["date"], y=monthly_fc["actual"],
                            mode="lines", name="Actual",
                            line=dict(color="#B6C2CF", dash="dot"),
                        )
                    fig.update_xaxes(title_text="")
                    fig.update_yaxes(title_text="")
                    st.plotly_chart(style_plotly(fig), use_container_width=True)

            # ---- Profit charts ----------------------------------------
            section(
                "Profit forecast",
                "How predicted profit develops by year and by month.",
                INDIGO,
            )

            p1, p2 = st.columns(2, gap="medium")

            with p1:
                with st.container(border=True):
                    card_header("Profit by year", "Actual history next to the forecast.")
                    profit_bar = year_bars(yearly_fc, hist, "profit")
                    fig = px.bar(
                        profit_bar, x="year", y="value", color="Type",
                        color_discrete_map={"Forecast": INDIGO, "Actual": "#B6C2CF"},
                    )
                    fig.update_xaxes(title_text="")
                    fig.update_yaxes(title_text="")
                    st.plotly_chart(style_plotly(fig), use_container_width=True)

            with p2:
                with st.container(border=True):
                    card_header("Monthly profit", "Predicted profit month by month.")
                    monthly_profit = view.groupby("date")["profit"].sum().reset_index()
                    fig = px.area(
                        monthly_profit, x="date", y="profit",
                        color_discrete_sequence=[INDIGO],
                    )
                    fig.update_xaxes(title_text="")
                    fig.update_yaxes(title_text="")
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(style_plotly(fig), use_container_width=True)

            # ---- Top products -----------------------------------------
            section(
                "Products driving the forecast",
                "Which products are expected to bring in the most revenue and profit.",
                AMBER,
            )

            top = (
                view.groupby("product_key")
                .agg(revenue=("revenue", "sum"), profit=("profit", "sum"))
                .reset_index()
                .sort_values("revenue", ascending=False)
                .head(10)
            )

            label_col = "product_key"
            if "product_key" in product_names.columns and "product_name" in product_names.columns:
                names = product_names[["product_key", "product_name"]].drop_duplicates("product_key")
                top = top.merge(names, on="product_key", how="left")
                top["product"] = top["product_name"].fillna(top["product_key"].astype(str))
                top["product"] = top["product"].str.slice(0, 35) + top["product"].str.len().gt(35).map({True: "…", False: ""})
                label_col = "product"
            else:
                top["product"] = "Product " + top["product_key"].astype(str)
                label_col = "product"
                
            top = top.sort_values("revenue")

            t1, t2 = st.columns(2, gap="medium")
            with t1:
                with st.container(border=True):
                    card_header("Top 10 products by predicted revenue")
                    fig = px.bar(
                        top, x="revenue", y=label_col, orientation="h",
                        color_discrete_sequence=[TEAL],
                    )
                    fig.update_xaxes(title_text="", tickprefix="$")
                    fig.update_yaxes(title_text="", tickprefix="")
                    fig.update_layout(showlegend=False)
                    fig = style_plotly(fig, 420)
                    fig.update_yaxes(tickprefix="")
                    st.plotly_chart(fig, use_container_width=True)
                    
            with t2:
                with st.container(border=True):
                    card_header("Same products by predicted profit")
                    fig = px.bar(
                        top, x="profit", y=label_col, orientation="h",
                        color_discrete_sequence=[INDIGO],
                    )
                    fig.update_xaxes(title_text="", tickprefix="$")
                    fig.update_yaxes(title_text="", tickprefix="")
                    fig.update_layout(showlegend=False)
                    fig = style_plotly(fig, 420)
                    fig.update_yaxes(tickprefix="")
                    st.plotly_chart(fig, use_container_width=True)
                    

            # ---- Download ---------------------------------------------
            st.write("")
            st.download_button(
                "Download forecast (CSV)",
                data=table.to_csv(index=False).encode("utf-8"),
                file_name="forecast_by_year.csv",
                mime="text/csv",
            )


# ======================================================================
# FOOTER
# ======================================================================

st.markdown(
    html_block(
        """
        <div class="app-footer">
            Sales Analytics Platform · PostgreSQL · Python · Pandas ·
            Matplotlib · Streamlit · PySpark
        </div>
        """
    ),
    unsafe_allow_html=True,
)