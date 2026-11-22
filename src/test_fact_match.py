import pandas as pd
from sqlalchemy import text
from src.config import get_engine

source_engine = get_engine("SOURCE_DB_NAME")
dwh_engine = get_engine("DWH_DB_NAME")

# Read source sales records
source_query = """
SELECT
    oi.order_item_id,
    o.order_id,
    o.order_date,
    o.ship_date,
    o.customer_id,
    oi.product_id,
    o.location_id,
    oi.discount,
    oi.quantity,
    oi.sales,
    oi.profit
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
"""

source = pd.read_sql(source_query, source_engine)

source["order_date"] = pd.to_datetime(source["order_date"]).dt.date
source["ship_date"] = pd.to_datetime(source["ship_date"]).dt.date

# Read existing DWH data
existing = pd.read_sql(
    text("""
        SELECT
            sales_key, order_id,
            order_date_key, ship_date_key,
            customer_key, product_key, location_key,
            discount, quantity, sales, profit,
            order_item_id
        FROM fact_sales
    """),
    dwh_engine,
)

print("Source rows:", len(source))
print("Existing DWH rows:", len(existing))
print(
    "Existing IDs filled:",
    int(existing["order_item_id"].notna().sum())
)

print("\nRead-only inspection completed.")
print("No data was inserted, updated, or deleted.")

print("\nChecking dimension key mappings...")

checks = [
    ("dim_customer", "customer_id", "customer_key"),
    ("dim_product", "product_id", "product_key"),
    ("dim_location", "location_id", "location_key"),
]

for table, business_col, key_col in checks:
    query = text(f"""
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT {business_col}) AS unique_ids
        FROM {table}
    """)

    with dwh_engine.connect() as connection:
        result = connection.execute(query).mappings().one()

    print(
        f"{table}: rows={result['total_rows']}, "
        f"unique IDs={result['unique_ids']}"
    )

print("\nDimension inspection completed. Read-only.")


print("\nChecking date coverage...")

source_dates = pd.read_sql(
    text("""
        SELECT order_date AS full_date FROM orders
        UNION
        SELECT ship_date AS full_date FROM orders
    """),
    source_engine,
)

dwh_dates = pd.read_sql(
    text("SELECT full_date FROM dim_date"),
    dwh_engine,
)

source_dates["full_date"] = pd.to_datetime(
    source_dates["full_date"]
).dt.date

dwh_dates["full_date"] = pd.to_datetime(
    dwh_dates["full_date"]
).dt.date

missing_dates = set(source_dates["full_date"]) - set(
    dwh_dates["full_date"]
)

print("Distinct source dates:", len(source_dates))
print("Dates in DWH:", len(dwh_dates))
print("Missing dates:", len(missing_dates))

if missing_dates:
    print("Sample missing dates:", sorted(missing_dates)[:10])
else:
    print("All source dates exist in dim_date.")

print("Read-only check completed.")


print("\nChecking actual fact matching...")

with dwh_engine.connect() as connection:
    dates = pd.read_sql(
        text("SELECT date_key, full_date FROM dim_date"),
        connection,
    )
    customers = pd.read_sql(
        text("SELECT customer_key, customer_id FROM dim_customer"),
        connection,
    )
    products = pd.read_sql(
        text("SELECT product_key, product_id FROM dim_product"),
        connection,
    )
    locations = pd.read_sql(
        text("SELECT location_key, location_id FROM dim_location"),
        connection,
    )

dates["full_date"] = pd.to_datetime(dates["full_date"]).dt.date

mapped = source.copy()

mapped = mapped.merge(
    dates.rename(columns={
        "full_date": "order_date",
        "date_key": "order_date_key",
    }),
    on="order_date",
    how="left",
    validate="many_to_one",
)

mapped = mapped.merge(
    dates.rename(columns={
        "full_date": "ship_date",
        "date_key": "ship_date_key",
    }),
    on="ship_date",
    how="left",
    validate="many_to_one",
)

mapped = mapped.merge(
    customers, on="customer_id", how="left",
    validate="many_to_one",
)
mapped = mapped.merge(
    products, on="product_id", how="left",
    validate="many_to_one",
)
mapped = mapped.merge(
    locations, on="location_id", how="left",
    validate="many_to_one",
)

match_columns = [
    "order_id",
    "order_date_key",
    "ship_date_key",
    "customer_key",
    "product_key",
    "location_key",
    "discount",
    "quantity",
    "sales",
    "profit",
]

print("Mapped source rows:", len(mapped))
print(
    "Rows with missing dimension keys:",
    int(mapped[
        [
            "order_date_key", "ship_date_key",
            "customer_key", "product_key", "location_key",
        ]
    ].isna().any(axis=1).sum()),
)

# Normalize numeric values before comparing database and pandas values.
for column in ["discount", "sales", "profit"]:
    mapped[column] = pd.to_numeric(mapped[column]).round(4)
    existing[column] = pd.to_numeric(existing[column]).round(4)

matched = mapped.merge(
    existing,
    on=match_columns,
    how="inner",
    validate="one_to_one",
    suffixes=("_source", "_dwh"),
)

print("Matched existing rows:", len(matched))
print("Unmatched source rows:", len(mapped) - len(matched))
print("Unmatched DWH rows:", len(existing) - len(matched))
print("Read-only matching test completed.")


# Safely backfill order_item_id after exact one-to-one matching
assert len(source) == 9993
assert len(existing) == 9993
assert len(matched) == 9993
assert matched["sales_key"].is_unique
assert matched["order_item_id_source"].is_unique
assert matched["order_item_id_source"].notna().all()

updates = [
    {
        "sales_key": int(row.sales_key),
        "order_item_id": int(row.order_item_id_source),
    }
    for row in matched[
        ["sales_key", "order_item_id_source"]
    ].itertuples(index=False)
]

with dwh_engine.begin() as connection:
    connection.execute(
        text("""
            UPDATE fact_sales
            SET order_item_id = :order_item_id
            WHERE sales_key = :sales_key
              AND order_item_id IS NULL
        """),
        updates,
    )

print("Backfill completed.")

print("\nChecking incremental load readiness...")

existing_ids = set(
    existing["order_item_id"].dropna().astype(int)
)

source_ids = set(
    source["order_item_id"].astype(int)
)

new_ids = source_ids - existing_ids

print("Source IDs:", len(source_ids))
print("Existing IDs:", len(existing_ids))
print("New IDs to insert:", len(new_ids))

if len(new_ids) == 0:
    print("Safe to proceed: no duplicate sales will be inserted.")
else:
    print("New source IDs detected; review before loading.")