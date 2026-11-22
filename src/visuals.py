import pandas as pd
import matplotlib.pyplot as plt

from src.config import get_engine

engine = get_engine("DWH_DB_NAME")

print("Connected to sales_dwh successfully!")


def revenue_over_time():

    df = pd.read_sql("SELECT * FROM vw_sales_over_time;", engine)

    df["period"] = df["month_name"] + " " + df["year"].astype(str)

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(df["period"], df["revenue"], marker="o")

    ax.set_title("Revenue Over Time")
    ax.set_xlabel("Month")
    ax.set_ylabel("Revenue")

    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    return fig


def profit_over_time():

    df = pd.read_sql("SELECT * FROM vw_sales_over_time;", engine)

    df["period"] = df["month_name"] + " " + df["year"].astype(str)

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(df["period"], df["profit"], marker="o")

    ax.set_title("Profit Over Time")
    ax.set_xlabel("Month")
    ax.set_ylabel("Profit")

    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    return fig


def revenue_by_category():

    df = pd.read_sql("SELECT * FROM vw_category_performance;", engine)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df["category"], df["revenue"])

    ax.set_title("Revenue by Category")
    ax.set_xlabel("Category")
    ax.set_ylabel("Revenue")

    fig.tight_layout()

    return fig


def profit_by_category():

    df = pd.read_sql("SELECT * FROM vw_category_performance;", engine)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df["category"], df["profit"])

    ax.set_title("Profit by Category")
    ax.set_xlabel("Category")
    ax.set_ylabel("Profit")

    fig.tight_layout()

    return fig


def revenue_by_subcategory():

    df = pd.read_sql("SELECT * FROM vw_subcategory_performance;", engine)

    df = df.sort_values("revenue", ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(df["subcategory"], df["revenue"])

    ax.set_title("Top 10 Subcategories by Revenue")
    ax.set_xlabel("Subcategory")
    ax.set_ylabel("Revenue")

    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    return fig


def revenue_by_manufacturer():

    df = pd.read_sql("SELECT * FROM vw_manufacturer_performance;", engine)

    df = df.sort_values("revenue", ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(df["manufacturer"], df["revenue"])

    ax.set_title("Top 10 Manufacturers by Revenue")
    ax.set_xlabel("Manufacturer")
    ax.set_ylabel("Revenue")

    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    return fig


def profit_by_manufacturer():

    df = pd.read_sql("SELECT * FROM vw_manufacturer_performance;", engine)

    df = df.sort_values("profit", ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(df["manufacturer"], df["profit"])

    ax.set_title("Top 10 Manufacturers by Profit")
    ax.set_xlabel("Manufacturer")
    ax.set_ylabel("Profit")

    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    return fig


def revenue_by_segment():

    df = pd.read_sql("SELECT * FROM vw_segment_performance;", engine)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df["segment"], df["revenue"])

    ax.set_title("Revenue by Customer Segment")
    ax.set_xlabel("Segment")
    ax.set_ylabel("Revenue")

    fig.tight_layout()

    return fig


def profit_by_segment():

    df = pd.read_sql("SELECT * FROM vw_segment_performance;", engine)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df["segment"], df["profit"])

    ax.set_title("Profit by Customer Segment")
    ax.set_xlabel("Segment")
    ax.set_ylabel("Profit")

    fig.tight_layout()

    return fig


def revenue_by_region():

    df = pd.read_sql("SELECT * FROM vw_region_performance;", engine)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df["region"], df["revenue"])

    ax.set_title("Revenue by Region")
    ax.set_xlabel("Region")
    ax.set_ylabel("Revenue")

    fig.tight_layout()

    return fig


def profit_by_region():

    df = pd.read_sql("SELECT * FROM vw_region_performance;", engine)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df["region"], df["profit"])

    ax.set_title("Profit by Region")
    ax.set_xlabel("Region")
    ax.set_ylabel("Profit")

    fig.tight_layout()

    return fig


def discount_vs_profit():

    df = pd.read_sql("SELECT * FROM vw_discount_profitability;", engine)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.scatter(df["discount"], df["profit"])

    ax.set_title("Discount vs Profit")
    ax.set_xlabel("Discount")
    ax.set_ylabel("Profit")

    fig.tight_layout()

    return fig


def discount_vs_profit_margin():

    df = pd.read_sql("SELECT * FROM vw_discount_profitability;", engine)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.scatter(df["discount"], df["profit_margin"])

    ax.set_title("Discount vs Profit Margin")
    ax.set_xlabel("Discount")
    ax.set_ylabel("Profit Margin")

    fig.tight_layout()

    return fig


if __name__ == "__main__":

    figures = [
        revenue_over_time(),
        profit_over_time(),
        revenue_by_category(),
        profit_by_category(),
        revenue_by_subcategory(),
        revenue_by_manufacturer(),
        profit_by_manufacturer(),
        revenue_by_segment(),
        profit_by_segment(),
        revenue_by_region(),
        profit_by_region(),
        discount_vs_profit(),
        discount_vs_profit_margin(),
    ]

    for fig in figures:
        plt.show()
