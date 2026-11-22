CREATE OR REPLACE VIEW vw_overall_sales_performance AS
SELECT
    COUNT(DISTINCT f.order_id) AS total_orders,
    SUM(f.quantity) AS total_quantity,
    SUM(f.sales) AS total_revenue,
    SUM(f.profit) AS total_profit,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f;


CREATE OR REPLACE VIEW vw_sales_over_time AS
SELECT
    d.year,
    d.month,
    d.month_name,
    d.quarter,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year,
    d.month,
    d.month_name,
    d.quarter
ORDER BY
    d.year,
    d.month;


CREATE OR REPLACE VIEW vw_yearly_performance AS
SELECT
    d.year,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year
ORDER BY
    d.year;


CREATE OR REPLACE VIEW vw_monthly_performance AS
SELECT
    d.year,
    d.month,
    d.month_name,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year,
    d.month,
    d.month_name
ORDER BY
    d.year,
    d.month;


CREATE OR REPLACE VIEW vw_quarterly_performance AS
SELECT
    d.year,
    d.quarter,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year,
    d.quarter
ORDER BY
    d.year,
    d.quarter;


CREATE OR REPLACE VIEW vw_category_performance AS
SELECT
    p.category,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_product p
    ON f.product_key = p.product_key
GROUP BY
    p.category
ORDER BY
    revenue DESC;


CREATE OR REPLACE VIEW vw_subcategory_performance AS
SELECT
    p.category,
    p.subcategory,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_product p
    ON f.product_key = p.product_key
GROUP BY
    p.category,
    p.subcategory
ORDER BY
    revenue DESC;


CREATE OR REPLACE VIEW vw_product_performance AS
SELECT
    p.product_id,
    p.product_name,
    p.manufacturer,
    p.category,
    p.subcategory,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_product p
    ON f.product_key = p.product_key
GROUP BY
    p.product_id,
    p.product_name,
    p.manufacturer,
    p.category,
    p.subcategory
ORDER BY
    revenue DESC;


CREATE OR REPLACE VIEW vw_manufacturer_performance AS
SELECT
    p.manufacturer,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_product p
    ON f.product_key = p.product_key
GROUP BY
    p.manufacturer
ORDER BY
    revenue DESC;


CREATE OR REPLACE VIEW vw_manufacturer_yearly_performance AS
SELECT
    d.year,
    p.manufacturer,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_product p
    ON f.product_key = p.product_key
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year,
    p.manufacturer
ORDER BY
    d.year,
    revenue DESC;


CREATE OR REPLACE VIEW vw_segment_performance AS
SELECT
    c.segment,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    COUNT(DISTINCT c.customer_id) AS customers,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_customer c
    ON f.customer_key = c.customer_key
GROUP BY
    c.segment
ORDER BY
    revenue DESC;


CREATE OR REPLACE VIEW vw_segment_yearly_performance AS
SELECT
    d.year,
    c.segment,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_customer c
    ON f.customer_key = c.customer_key
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year,
    c.segment
ORDER BY
    d.year,
    revenue DESC;


CREATE OR REPLACE VIEW vw_region_performance AS
SELECT
    l.region,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_location l
    ON f.location_key = l.location_key
GROUP BY
    l.region
ORDER BY
    revenue DESC;


CREATE OR REPLACE VIEW vw_region_yearly_performance AS
SELECT
    d.year,
    l.region,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
JOIN dim_location l
    ON f.location_key = l.location_key
JOIN dim_date d
    ON f.order_date_key = d.date_key
GROUP BY
    d.year,
    l.region
ORDER BY
    d.year,
    revenue DESC;


CREATE OR REPLACE VIEW vw_discount_profitability AS
SELECT
    f.discount,
    SUM(f.sales) AS revenue,
    SUM(f.profit) AS profit,
    SUM(f.quantity) AS quantity,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.profit) / NULLIF(SUM(f.sales), 0) AS profit_margin
FROM fact_sales f
GROUP BY
    f.discount
ORDER BY
    f.discount;