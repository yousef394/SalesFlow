import numpy as np
import pandas as pd

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "Sales_data (1).csv"



def main():
    """Read the CSV, validate it and build the normalized tables in memory.

    Does not touch any database. Returns the tables as a dict of DataFrames.
    """
    df = pd.read_csv(CSV_PATH)
    print("CSV columns:")
    print(df.columns.tolist())
    print(df.head())
    print(df.shape)
    print(df.info())
    # الداتا تايبس مش متظبطه لازم اظبطها
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["ship_date"] = pd.to_datetime(df["ship_date"])
    assert (df["ship_date"] >= df["order_date"]).all(), \
        "There are shipping dates before order dates. Check date format!"
    print(df.info())
    # عايز اتأكد من الدوبليكاتس
    print("Duplicate rows:", df.duplicated().sum())

    duplicates = df[df.duplicated(keep=False)]

    print("Potential duplicate rows:", len(duplicates))
    print(duplicates.sort_values("order_id"))
    print("Duplicate rows:", df.duplicated().sum())

    print(df[["discount", "profit", "quantity", "sales", "profit_margin"]].describe())

    print("Customers:", df["customer"].nunique())
    print("Manufacturers:", df["manufactory"].nunique())
    print("Categories:", df["category"].nunique())
    print("Subcategories:", df["subcategory"].nunique())
    print("Products:", df["product_name"].nunique())
    print("Orders:", df["order_id"].nunique())

    customer_segments = df.groupby("customer")["segment"].nunique()

    conflicts = customer_segments[customer_segments > 1]

    if not conflicts.empty:
        raise ValueError(
            f"Customers with multiple segments:\n{conflicts}"
        )

    customers = df[["customer", "segment"]].drop_duplicates()
    customers["customer_id"] = range(1, len(customers) + 1)
    customers = customers[["customer_id", "customer", "segment"]]

    print(customers.head())
    print(customers.shape)

    manufacturers = df[["manufactory"]].drop_duplicates()
    manufacturers["manufacturer_id"] = range(1, len(manufacturers) + 1)
    manufacturers = manufacturers[["manufacturer_id", "manufactory"]]

    print(manufacturers.head())
    print(manufacturers.shape)

    categories = df[["category"]].drop_duplicates()
    categories["category_id"] = range(1, len(categories) + 1)
    categories = categories[["category_id", "category"]]

    print(categories.head())
    print(categories.shape)

    locations = df[["zip", "city", "state", "country", "region"]].drop_duplicates()
    locations["location_id"] = range(1, len(locations) + 1)
    locations = locations[["location_id", "zip", "city", "state", "country", "region"]]


    print(locations.head())
    print(locations.shape)

    subcategories = df[["category", "subcategory"]].drop_duplicates()
    subcategories["subcategory_id"] = range(1, len(subcategories) + 1)
    subcategories = subcategories.merge(categories, on="category", how="left")
    subcategories = subcategories[["subcategory_id", "subcategory", "category_id"]]

    print(subcategories.head(15))
    print(subcategories.shape)

    orders = df[
        [
            "order_id",
            "order_date",
            "ship_date",
            "customer",
            "zip",
            "city",
            "state",
            "country",
            "region",
        ]
    ].drop_duplicates()

    orders = orders.merge(
        customers[["customer_id", "customer"]],
        on="customer",
        how="left",
        validate="many_to_one"
    )

    orders = orders.merge(
        locations[["location_id", "zip", "city", "state", "country", "region"]],
        on=["zip", "city", "state", "country", "region"],
        how="left",
        validate="many_to_one"
    )

    orders = orders[
        ["order_id", "order_date", "ship_date", "customer_id", "location_id"]
    ]

    product_keys = [
        "product_name",
        "category",
        "subcategory",
        "manufactory"
    ]

    products_full = (
        df[product_keys]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    products_full["product_id"] = range(1, len(products_full) + 1)

    products_full = (
        products_full
        .merge(categories, on="category", how="left", validate="many_to_one")
        .merge(
            subcategories,
            on=["subcategory", "category_id"],
            how="left",
            validate="many_to_one"
        )
        .merge(manufacturers, on="manufactory", how="left", validate="many_to_one")
    )

    products = products_full[
        ["product_id", "product_name", "manufacturer_id", "subcategory_id"]
    ]

    order_items = df[
        ["order_id", "discount", "quantity", "sales", "profit"] + product_keys
    ].merge(
        products_full[product_keys + ["product_id"]],
        on=product_keys,
        how="left",
        validate="many_to_one"
    )

    order_items["order_item_id"] = range(1, len(order_items) + 1)

    order_items = order_items[
        [
            "order_item_id",
            "order_id",
            "product_id",
            "discount",
            "quantity",
            "sales",
            "profit"
        ]
    ]

    limits = {
        "customer": 150,
        "segment": 50,
        "manufactory": 100,
        "category": 50,
        "subcategory": 50,
        "city": 100,
        "state": 100,
        "country": 100,
        "region": 50,
        "order_id": 20
    }

    for col, limit in limits.items():
        longest = df[col].dropna().astype(str).str.len().max()

        if pd.notna(longest) and longest > limit:
            raise ValueError(
                f"{col}: length {longest} exceeds VARCHAR({limit})"
            )

    assert df["discount"].between(0, 1).all()
    assert df["quantity"].gt(0).all()
    assert df["sales"].notna().all()
    assert df["profit"].notna().all()

    print("Column constraints validation passed!")

    # هتأكد ان كل ال fk قيمها مليانه

    assert subcategories["category_id"].notna().all()

    assert products[
        ["manufacturer_id", "subcategory_id"]
    ].notna().all().all()

    assert orders[
        ["customer_id", "location_id"]
    ].notna().all().all()

    assert order_items["product_id"].notna().all()

    assert orders["order_id"].is_unique, "Duplicate order_id detected"

    assert len(orders) == df["order_id"].nunique(), \
        "Orders count does not match unique order IDs"

    assert len(order_items) == len(df), \
        "Order items count does not match source rows"

    assert order_items["order_item_id"].is_unique

    print("All foreign key and row count checks passed!")

    # هتأكد من شكل كل تابل الاول

    print("Customers:", customers.shape)
    print("Manufacturers:", manufacturers.shape)
    print("Categories:", categories.shape)
    print("Subcategories:", subcategories.shape)
    print("Products:", products.shape)
    print("Locations:", locations.shape)
    print("Orders:", orders.shape)
    print("Order Items:", order_items.shape)

    return {
        "customers": customers,
        "manufacturers": manufacturers,
        "categories": categories,
        "subcategories": subcategories,
        "locations": locations,
        "products": products,
        "orders": orders,
        "order_items": order_items,
    }


if __name__ == "__main__":
    main()