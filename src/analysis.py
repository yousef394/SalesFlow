import pandas as pd
from pathlib import Path
from src.config import get_engine

engine = get_engine("DWH_DB_NAME")

print("Connected to sales_dwh successfully!")


BASE_DIR = Path(__file__).resolve().parent.parent
SQL_PATH = BASE_DIR / "sql" / "analytics.sql"

with open(SQL_PATH, "r") as file:
    analysis_sql = file.read()

with engine.begin() as connection:
    connection.exec_driver_sql(analysis_sql)

print("Analytics views created successfully!")


overall = pd.read_sql("SELECT * FROM vw_overall_sales_performance;", engine)

print("\n========== Overall Sales Performance ==========")
print(overall)


sales_over_time = pd.read_sql("SELECT * FROM vw_sales_over_time;", engine)

print("\n========== Sales Over Time ==========")
print(sales_over_time)


yearly = pd.read_sql("SELECT * FROM vw_yearly_performance;", engine)

print("\n========== Yearly Performance ==========")
print(yearly)


monthly = pd.read_sql("SELECT * FROM vw_monthly_performance;", engine)

print("\n========== Monthly Performance ==========")
print(monthly)


quarterly = pd.read_sql("SELECT * FROM vw_quarterly_performance;", engine)

print("\n========== Quarterly Performance ==========")
print(quarterly)


category = pd.read_sql("SELECT * FROM vw_category_performance;", engine)

print("\n========== Category Performance ==========")
print(category)


subcategory = pd.read_sql("SELECT * FROM vw_subcategory_performance;", engine)

print("\n========== Subcategory Performance ==========")
print(subcategory)


product = pd.read_sql("SELECT * FROM vw_product_performance;", engine)

print("\n========== Product Performance ==========")
print(product)


manufacturer = pd.read_sql("SELECT * FROM vw_manufacturer_performance;", engine)

print("\n========== Manufacturer Performance ==========")
print(manufacturer)


manufacturer_yearly = pd.read_sql(
    "SELECT * FROM vw_manufacturer_yearly_performance;", engine
)

print("\n========== Manufacturer Yearly Performance ==========")
print(manufacturer_yearly)


segment = pd.read_sql("SELECT * FROM vw_segment_performance;", engine)

print("\n========== Segment Performance ==========")
print(segment)


segment_yearly = pd.read_sql("SELECT * FROM vw_segment_yearly_performance;", engine)

print("\n========== Segment Yearly Performance ==========")
print(segment_yearly)


region = pd.read_sql("SELECT * FROM vw_region_performance;", engine)

print("\n========== Region Performance ==========")
print(region)


region_yearly = pd.read_sql("SELECT * FROM vw_region_yearly_performance;", engine)

print("\n========== Region Yearly Performance ==========")
print(region_yearly)


discount = pd.read_sql("SELECT * FROM vw_discount_profitability;", engine)

print("\n========== Discount & Profitability ==========")
print(discount)
