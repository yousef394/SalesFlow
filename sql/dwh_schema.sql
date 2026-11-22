CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    segment VARCHAR(50) NOT NULL,

    effective_date DATE NOT NULL,
    end_date DATE,
    is_current BOOLEAN NOT NULL
);


CREATE TABLE IF NOT EXISTS dim_product  (
    product_key SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    manufacturer VARCHAR(150) NOT NULL,
    subcategory VARCHAR(100) NOT NULL,
    category VARCHAR(100) NOT NULL,

    effective_date DATE NOT NULL,
    end_date DATE,
    is_current BOOLEAN NOT NULL
);


CREATE TABLE IF NOT EXISTS dim_date (
    date_key SERIAL PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    day INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    quarter INTEGER NOT NULL,
    year INTEGER NOT NULL,
    day_of_week VARCHAR(20) NOT NULL
);


CREATE TABLE IF NOT EXISTS dim_location (
    location_key SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL,
    zip INTEGER,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    region VARCHAR(50)
);


CREATE TABLE IF NOT EXISTS fact_sales (
    sales_key SERIAL PRIMARY KEY,
    order_item_id INTEGER UNIQUE,
    order_id VARCHAR(50) NOT NULL,

    order_date_key INTEGER NOT NULL,
    ship_date_key INTEGER NOT NULL,

    customer_key INTEGER NOT NULL,
    product_key INTEGER NOT NULL,
    location_key INTEGER NOT NULL,

    discount NUMERIC(10,4) NOT NULL,
    quantity INTEGER NOT NULL,
    sales NUMERIC(12,4) NOT NULL,
    profit NUMERIC(12,4) NOT NULL,

    FOREIGN KEY (order_date_key)
        REFERENCES dim_date(date_key),

    FOREIGN KEY (ship_date_key)
        REFERENCES dim_date(date_key),

    FOREIGN KEY (customer_key)
        REFERENCES dim_customer(customer_key),

    FOREIGN KEY (product_key)
        REFERENCES dim_product(product_key),

    FOREIGN KEY (location_key)
        REFERENCES dim_location(location_key)
);