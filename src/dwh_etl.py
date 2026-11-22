from sqlalchemy import text
import pandas as pd
from pathlib import Path
from datetime import date
from src.config import get_engine

BASE_DIR = Path(__file__).resolve().parent.parent
SQL_PATH = BASE_DIR / "sql" / "dwh_schema.sql"


def main():
    """Incremental load of the data warehouse (source DB -> sales_dwh)."""
    source_engine = get_engine("SOURCE_DB_NAME")
    dwh_engine = get_engine("DWH_DB_NAME")

    try:
        print("Engines created successfully!")



        with open(SQL_PATH, "r") as file:
            schema_sql = file.read()

        with dwh_engine.begin() as connection:
            connection.execute(text(schema_sql))

        print("DWH schema created successfully!")



        dates_query = """
        SELECT order_date AS full_date
        FROM orders

        UNION

        SELECT ship_date AS full_date
        FROM orders
        """

        dates = pd.read_sql(dates_query, source_engine)

        dates["full_date"] = pd.to_datetime(dates["full_date"]).dt.date

        dates = dates.sort_values("full_date").reset_index(drop=True)

        dates["day"] = pd.to_datetime(dates["full_date"]).dt.day

        dates["month"] = pd.to_datetime(dates["full_date"]).dt.month

        dates["month_name"] = pd.to_datetime(dates["full_date"]).dt.month_name()

        dates["quarter"] = pd.to_datetime(dates["full_date"]).dt.quarter

        dates["year"] = pd.to_datetime(dates["full_date"]).dt.year

        dates["day_of_week"] = pd.to_datetime(dates["full_date"]).dt.day_name()



        initial_date = dates["full_date"].min()

        # Insert only dates that do not already exist.
        date_records = dates.to_dict("records")

        with dwh_engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO dim_date (
                        full_date,
                        day,
                        month,
                        month_name,
                        quarter,
                        year,
                        day_of_week
                    )
                    VALUES (
                        :full_date,
                        :day,
                        :month,
                        :month_name,
                        :quarter,
                        :year,
                        :day_of_week
                    )
                    ON CONFLICT (full_date) DO NOTHING
                """),
                date_records
            )

        print(f"Date processing completed! Rows checked: {len(dates)}")

        customers_query = """
        SELECT
            customer_id,
            customer AS customer_name,
            segment
        FROM customers
        """

        customers = pd.read_sql(customers_query, source_engine)




        # Read the current customer versions from the DWH.
        with dwh_engine.connect() as connection:
            current_customers = pd.read_sql(
                text("""
                    SELECT
                        customer_key,
                        customer_id,
                        customer_name,
                        segment
                    FROM dim_customer
                    WHERE is_current = TRUE
                """),
                connection
            )

        today = date.today()

        # Compare source customers with their current DWH versions.
        current_lookup = current_customers.set_index("customer_id").to_dict("index")
        new_records = []
        changed_records = []

        for row in customers.to_dict("records"):
            customer_id = row["customer_id"]

            if customer_id not in current_lookup:
                new_records.append({
                    "customer_id": customer_id,
                    "customer_name": row["customer_name"],
                    "segment": row["segment"],
                    "effective_date": today,
                    "end_date": None,
                    "is_current": True
                })
                continue

            old = current_lookup[customer_id]

            # Detect changes in tracked attributes.
            if (
                old["customer_name"] != row["customer_name"]
                or old["segment"] != row["segment"]
            ):
                changed_records.append({
                    "customer_key": old["customer_key"],
                    "customer_id": customer_id,
                    "customer_name": row["customer_name"],
                    "segment": row["segment"],
                    "effective_date": today,
                    "end_date": None,
                    "is_current": True
                })

        # Close old versions and insert new versions atomically.
        with dwh_engine.begin() as connection:

            for record in changed_records:
                connection.execute(
                    text("""
                        UPDATE dim_customer
                        SET end_date = :today,
                            is_current = FALSE
                        WHERE customer_key = :customer_key
                          AND is_current = TRUE
                    """),
                    {
                        "today": today,
                        "customer_key": record["customer_key"]
                    }
                )

            records_to_insert = new_records + [
                {
                    key: value
                    for key, value in record.items()
                    if key != "customer_key"
                }
                for record in changed_records
            ]

            if records_to_insert:
                connection.execute(
                    text("""
                        INSERT INTO dim_customer (
                            customer_id,
                            customer_name,
                            segment,
                            effective_date,
                            end_date,
                            is_current
                        )
                        VALUES (
                            :customer_id,
                            :customer_name,
                            :segment,
                            :effective_date,
                            :end_date,
                            :is_current
                        )
                    """),
                    records_to_insert
                )

        print(f"New customer versions: {len(new_records)}")
        print(f"Changed customer versions: {len(changed_records)}")
        print("Customer SCD Type 2 processing completed!")


        products_query = """
        SELECT
            p.product_id,
            p.product_name,
            m.manufactory AS manufacturer,
            s.subcategory,
            c.category
        FROM products p

        JOIN manufacturers m
            ON p.manufacturer_id = m.manufacturer_id

        JOIN subcategories s
            ON p.subcategory_id = s.subcategory_id

        JOIN categories c
            ON s.category_id = c.category_id
        """

        products = pd.read_sql(products_query, source_engine)




        # Read current product versions from the DWH.
        with dwh_engine.connect() as connection:
            current_products = pd.read_sql(
                text("""
                    SELECT
                        product_key,
                        product_id,
                        product_name,
                        manufacturer,
                        subcategory,
                        category
                    FROM dim_product
                    WHERE is_current = TRUE
                """),
                connection
            )

        today = date.today()

        current_lookup = current_products.set_index("product_id").to_dict("index")

        new_records = []
        changed_records = []

        # Compare incoming source products with current DWH versions.
        for row in products.to_dict("records"):
            product_id = row["product_id"]

            if product_id not in current_lookup:
                new_records.append({
                    "product_id": product_id,
                    "product_name": row["product_name"],
                    "manufacturer": row["manufacturer"],
                    "subcategory": row["subcategory"],
                    "category": row["category"],
                    "effective_date": today,
                    "end_date": None,
                    "is_current": True
                })
                continue

            old = current_lookup[product_id]

            tracked_columns = [
                "product_name",
                "manufacturer",
                "subcategory",
                "category"
            ]

            has_changed = any(
                old[column] != row[column]
                for column in tracked_columns
            )

            if has_changed:
                changed_records.append({
                    "product_key": old["product_key"],
                    "product_id": product_id,
                    "product_name": row["product_name"],
                    "manufacturer": row["manufacturer"],
                    "subcategory": row["subcategory"],
                    "category": row["category"],
                    "effective_date": today,
                    "end_date": None,
                    "is_current": True
                })

        # Close old versions and insert new versions in one transaction.
        with dwh_engine.begin() as connection:

            for record in changed_records:
                connection.execute(
                    text("""
                        UPDATE dim_product
                        SET end_date = :today,
                            is_current = FALSE
                        WHERE product_key = :product_key
                          AND is_current = TRUE
                    """),
                    {
                        "today": today,
                        "product_key": record["product_key"]
                    }
                )

            records_to_insert = new_records + [
                {
                    key: value
                    for key, value in record.items()
                    if key != "product_key"
                }
                for record in changed_records
            ]

            if records_to_insert:
                connection.execute(
                    text("""
                        INSERT INTO dim_product (
                            product_id,
                            product_name,
                            manufacturer,
                            subcategory,
                            category,
                            effective_date,
                            end_date,
                            is_current
                        )
                        VALUES (
                            :product_id,
                            :product_name,
                            :manufacturer,
                            :subcategory,
                            :category,
                            :effective_date,
                            :end_date,
                            :is_current
                        )
                    """),
                    records_to_insert
                )

        print(f"New product versions: {len(new_records)}")
        print(f"Changed product versions: {len(changed_records)}")
        print("Product SCD Type 2 processing completed!")


        locations_query = """
        SELECT
            location_id,
            zip,
            city,
            state,
            country,
            region
        FROM locations
        """

        locations = pd.read_sql(locations_query, source_engine)



        with dwh_engine.begin() as connection:
            existing_locations = pd.read_sql(
                text("SELECT location_id FROM dim_location"),
                connection
            )

            existing_ids = set(existing_locations["location_id"])
            new_locations = locations[
                ~locations["location_id"].isin(existing_ids)
            ]

            if not new_locations.empty:
                new_locations.to_sql(
                    "dim_location",
                    connection,
                    if_exists="append",
                    index=False
                )

        print(f"New locations loaded: {len(new_locations)}")

        print(f"dim_location loaded successfully! Rows: {len(locations)}")


        with dwh_engine.connect() as connection:

            date_lookup = pd.read_sql(
                text("""
                    SELECT
                        date_key,
                        full_date
                    FROM dim_date
                """),
                connection,
            )

            date_lookup["full_date"] = pd.to_datetime(date_lookup["full_date"]).dt.date

            customer_lookup = pd.read_sql(
                text("""
                    SELECT customer_key, customer_id
                    FROM dim_customer
                    WHERE is_current = TRUE
                """),
                connection,
            )

            product_lookup = pd.read_sql(
                text("""
                    SELECT product_key, product_id
                    FROM dim_product
                    WHERE is_current = TRUE
                """),
                connection,
            )

            location_lookup = pd.read_sql(
                text("""
                    SELECT
                        location_key,
                        location_id
                    FROM dim_location
                """),
                connection,
            )


        fact_query = """
        SELECT
            oi.order_item_id,
            o.order_id,
            o.order_date,
            o.ship_date,
            c.customer_id,
            p.product_id,
            l.location_id,
            oi.discount,
            oi.quantity,
            oi.sales,
            oi.profit

        FROM orders o

        JOIN customers c
            ON o.customer_id = c.customer_id

        JOIN order_items oi
            ON o.order_id = oi.order_id

        JOIN products p
            ON oi.product_id = p.product_id

        JOIN locations l
            ON o.location_id = l.location_id
        """

        fact = pd.read_sql(fact_query, source_engine)


        fact["order_date"] = pd.to_datetime(fact["order_date"]).dt.date

        fact["ship_date"] = pd.to_datetime(fact["ship_date"]).dt.date


        fact = fact.merge(date_lookup, left_on="order_date", right_on="full_date", how="left")

        fact.rename(columns={"date_key": "order_date_key"}, inplace=True)

        fact.drop(columns=["full_date"], inplace=True)


        fact = fact.merge(date_lookup, left_on="ship_date", right_on="full_date", how="left")

        fact.rename(columns={"date_key": "ship_date_key"}, inplace=True)

        fact.drop(columns=["full_date"], inplace=True)

        fact = fact.merge(customer_lookup, on="customer_id", how="left")


        fact = fact.merge(product_lookup, on="product_id", how="left")


        fact = fact.merge(location_lookup, on="location_id", how="left")


        fact = fact[
            [
                "order_item_id",
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
        ]   

        print("\nForeign Key Null Check:")

        print(
            fact[
                [
                    "order_date_key",
                    "ship_date_key",
                    "customer_key",
                    "product_key",
                    "location_key",
                ]
            ]
            .isnull()
            .sum()
        )



        existing_fact = pd.read_sql(
            text("SELECT sales_key, order_item_id FROM fact_sales"),
            dwh_engine,
        )

        if existing_fact["order_item_id"].isna().any():
            raise ValueError("Missing order_item_id values in fact_sales")

        if existing_fact["order_item_id"].duplicated().any():
            raise ValueError("Duplicate order_item_id values in fact_sales")

        existing_ids = set(existing_fact["order_item_id"].astype(int))

        new_fact = fact[
            ~fact["order_item_id"].astype(int).isin(existing_ids)
        ].copy()

        if not new_fact.empty:
            new_fact.to_sql(
                "fact_sales",
                dwh_engine,
                if_exists="append",
                index=False,
            )

        print(f"Source sales rows: {len(fact)}")
        print(f"New sales inserted: {len(new_fact)}")
        print(f"Existing sales skipped: {len(fact) - len(new_fact)}")


        print("\nFinal DWH Row Counts:")

        with dwh_engine.connect() as connection:

            tables = ["dim_date", "dim_customer", "dim_product", "dim_location", "fact_sales"]

            for table in tables:

                result = connection.execute(text(f"SELECT COUNT(*) FROM {table}"))

                count = result.scalar()

                print(f"{table}: {count}")


        print("DWH ETL 5alsa")
    finally:
        source_engine.dispose()
        dwh_engine.dispose()


if __name__ == "__main__":
    main()