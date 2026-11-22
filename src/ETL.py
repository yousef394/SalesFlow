import os

import psycopg2
from dotenv import load_dotenv

from src import sales

load_dotenv()


def rows(df):
    return df.astype(object).where(df.notna(), None).values.tolist()


def main(prepared=None):
    """Full load of the source database (drops and rebuilds all 8 tables).

    `prepared` is the dict returned by src.sales.main(). When it is None
    (running this module on its own) the data is prepared here first.
    """
    if prepared is None:
        prepared = sales.main()

    customers = prepared["customers"]
    manufacturers = prepared["manufacturers"]
    categories = prepared["categories"]
    subcategories = prepared["subcategories"]
    locations = prepared["locations"]
    products = prepared["products"]
    orders = prepared["orders"]
    order_items = prepared["order_items"]

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("SOURCE_DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT"),
    )

    print("Connected successfully!")

    try:
        cursor = conn.cursor()

        for table in [
            "order_items", "orders", "products", "subcategories",
            "locations", "customers", "manufacturers", "categories",
        ]:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.commit()

        cursor.execute("""
        CREATE TABLE customers (
            customer_id SERIAL PRIMARY KEY,
            customer VARCHAR(150) NOT NULL,
            segment VARCHAR(50) NOT NULL
        )
        """)

        conn.commit()

        print("customers table created successfully!")

        cursor.execute("""
        CREATE TABLE manufacturers (
            manufacturer_id SERIAL PRIMARY KEY,
            manufactory VARCHAR(100) NOT NULL UNIQUE
        )
        """)

        cursor.execute("""
        CREATE TABLE categories (
            category_id SERIAL PRIMARY KEY,
            category VARCHAR(50) NOT NULL UNIQUE
        )
        """)

        cursor.execute("""
        CREATE TABLE subcategories (
            subcategory_id SERIAL PRIMARY KEY,
            subcategory VARCHAR(50) NOT NULL,
            category_id INTEGER NOT NULL,
            FOREIGN KEY (category_id)
                REFERENCES categories(category_id),
            UNIQUE (subcategory, category_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE locations (
            location_id SERIAL PRIMARY KEY,
            zip INTEGER,
            city VARCHAR(100),
            state VARCHAR(100),
            country VARCHAR(100),
            region VARCHAR(50)
        )
        """)

        cursor.execute("""
        CREATE TABLE products (
            product_id SERIAL PRIMARY KEY,
            product_name TEXT NOT NULL,
            manufacturer_id INTEGER NOT NULL,
            subcategory_id INTEGER NOT NULL,
            FOREIGN KEY (manufacturer_id)
                REFERENCES manufacturers(manufacturer_id),
            FOREIGN KEY (subcategory_id)
                REFERENCES subcategories(subcategory_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE orders (
            order_id VARCHAR(20) PRIMARY KEY,
            order_date DATE NOT NULL,
            ship_date DATE NOT NULL,
            customer_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id),
            FOREIGN KEY (location_id)
                REFERENCES locations(location_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE order_items (
            order_item_id SERIAL PRIMARY KEY,
            order_id VARCHAR(20) NOT NULL,
            product_id INTEGER NOT NULL,
            discount NUMERIC(5,4) NOT NULL,
            quantity INTEGER NOT NULL,
            sales NUMERIC(12,4) NOT NULL,
            profit NUMERIC(12,4) NOT NULL,
            FOREIGN KEY (order_id)
                REFERENCES orders(order_id),
            FOREIGN KEY (product_id)
                REFERENCES products(product_id)
        )
        """)

        conn.commit()

        print("All tables created successfully!")

        cursor.executemany(
            """
            INSERT INTO categories (category_id, category)
            VALUES (%s, %s)
            """,
            rows(categories),
        )

        print("Categories inserted successfully!")

        cursor.execute("SELECT * FROM categories")

        data = cursor.fetchall()

        for row in data:
            print(row)

        cursor.executemany(
            """
            INSERT INTO manufacturers (manufacturer_id, manufactory)
            VALUES (%s, %s)
            """,
            rows(manufacturers),
        )

        print("Manufacturers inserted successfully!")

        cursor.execute("SELECT * FROM manufacturers")

        data = cursor.fetchall()

        for row in data:
            print(row)

        #Customers
        cursor.executemany(
            """
            INSERT INTO customers (customer_id, customer, segment)
            VALUES (%s, %s, %s)
            """,
            rows(customers),
        )

        # Locations
        cursor.executemany(
            """
            INSERT INTO locations
            (location_id, zip, city, state, country, region)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows(locations),
        )

        # Subcategories
        cursor.executemany(
            """
            INSERT INTO subcategories
            (subcategory_id, subcategory, category_id)
            VALUES (%s, %s, %s)
            """,
            rows(subcategories),
        )

        # Products
        cursor.executemany(
            """
            INSERT INTO products
            (product_id, product_name, manufacturer_id, subcategory_id)
            VALUES (%s, %s, %s, %s)
            """,
            rows(products),
        )

        # Orders
        cursor.executemany(
            """
            INSERT INTO orders
            (order_id, order_date, ship_date, customer_id, location_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            rows(orders),
        )

        # Order Items
        cursor.executemany(
            """
            INSERT INTO order_items
            (order_item_id, order_id, product_id, discount, quantity, sales, profit)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows(order_items),
        )

        for table, col in [
            ("customers", "customer_id"), ("manufacturers", "manufacturer_id"),
            ("categories", "category_id"), ("subcategories", "subcategory_id"),
            ("locations", "location_id"), ("products", "product_id"),
            ("order_items", "order_item_id"),
        ]:
            cursor.execute(f"""
                SELECT setval(pg_get_serial_sequence('{table}', '{col}'),
                              (SELECT MAX({col}) FROM {table}))
            """)

        conn.commit()

        print("All remaining data inserted successfully!")

        tables = [
            "customers",
            "manufacturers",
            "categories",
            "subcategories",
            "locations",
            "products",
            "orders",
            "order_items",
        ]

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table}: {count}")

        cursor.execute("""
            SELECT
                o.order_id,
                c.customer,
                p.product_name,
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
            LIMIT 10
        """)

        data = cursor.fetchall()

        for row in data:
            print(row)

        cursor.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()