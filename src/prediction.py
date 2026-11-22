import json
from pathlib import Path

import numpy as np
import pandas as pd


from pyspark.sql import SparkSession
from pyspark.sql.functions import col, avg, when
from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import GBTRegressor
from pyspark.ml.evaluation import RegressionEvaluator
from src.config import get_engine

# How many future years to forecast after the last year in the data
N_FORECAST_YEARS = 3


spark = SparkSession.builder \
    .appName("Sales Prediction") \
    .getOrCreate()

print("Spark started successfully!")


engine = get_engine("DWH_DB_NAME")

print("Connected to sales_dwh successfully!")


# ======================================================================
# PART 1 - TRANSACTION-LEVEL MODEL (same as before: used to validate
#          how well the model learns the sales data)
# ======================================================================

query = """
SELECT
    f.quantity,
    f.discount,
    f.product_key,

    d.year,
    d.month,
    d.quarter,

    p.manufacturer,
    p.category,
    p.subcategory,

    c.segment,

    l.region,

    f.sales

FROM fact_sales f

JOIN dim_date d
    ON f.order_date_key = d.date_key

JOIN dim_product p
    ON f.product_key = p.product_key

JOIN dim_customer c
    ON f.customer_key = c.customer_key

JOIN dim_location l
    ON f.location_key = l.location_key
"""

df = pd.read_sql(query, engine)

print("\nData loaded from DWH:")
print(df.head())

print("\nData shape:")
print(df.shape)


spark_df = spark.createDataFrame(df)

train_data, test_data = spark_df.randomSplit([0.8, 0.2], seed=42)

print("\nTraining rows:", train_data.count())
print("Testing rows:", test_data.count())


train_data = train_data.withColumn(
    "unit_price",
    when(col("quantity") > 0, col("sales") / col("quantity")).otherwise(0)
)

test_data = test_data.withColumn(
    "unit_price",
    when(col("quantity") > 0, col("sales") / col("quantity")).otherwise(0)
)


product_price_lookup = train_data.groupBy("product_key").agg(
    avg("unit_price").alias("historical_avg_unit_price")
)

train_data = train_data.join(product_price_lookup, on="product_key", how="left")
test_data = test_data.join(product_price_lookup, on="product_key", how="left")

overall_avg_price = train_data.select(
    avg("historical_avg_unit_price")
).first()[0]

train_data = train_data.fillna({"historical_avg_unit_price": overall_avg_price})
test_data = test_data.fillna({"historical_avg_unit_price": overall_avg_price})


numeric_features = [
    "quantity",
    "discount",
    "historical_avg_unit_price",
    "year",
    "month",
    "quarter",
]

categorical_features = [
    "manufacturer",
    "category",
    "subcategory",
    "segment",
    "region",
]

indexers = [
    StringIndexer(
        inputCol=column,
        outputCol=column + "_index",
        handleInvalid="keep",
    )
    for column in categorical_features
]

encoder = OneHotEncoder(
    inputCols=[column + "_index" for column in categorical_features],
    outputCols=[column + "_encoded" for column in categorical_features],
)

assembler = VectorAssembler(
    inputCols=numeric_features + [c + "_encoded" for c in categorical_features],
    outputCol="features",
)

gbt = GBTRegressor(
    featuresCol="features",
    labelCol="sales",
    maxIter=30,
    maxDepth=5,
    seed=42,
)

pipeline = Pipeline(stages=indexers + [encoder, assembler, gbt])

print("\nTraining GBT model...")
model = pipeline.fit(train_data)
print("Model trained successfully!")

predictions = model.transform(test_data)

rmse = RegressionEvaluator(
    labelCol="sales", predictionCol="prediction", metricName="rmse"
).evaluate(predictions)

mae = RegressionEvaluator(
    labelCol="sales", predictionCol="prediction", metricName="mae"
).evaluate(predictions)

r2 = RegressionEvaluator(
    labelCol="sales", predictionCol="prediction", metricName="r2"
).evaluate(predictions)


output_dir = Path(__file__).resolve().parent.parent / "prediction_outputs"
output_dir.mkdir(parents=True, exist_ok=True)

prediction_pdf = predictions.select(
    "sales", "prediction", "year", "month", "product_key"
).toPandas()

prediction_pdf = prediction_pdf.rename(columns={
    "sales": "actual_sales",
    "prediction": "predicted_sales",
})

prediction_pdf.to_csv(output_dir / "predictions.csv", index=False)

metrics = {"rmse": float(rmse), "mae": float(mae), "r2": float(r2)}

with open(output_dir / "metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=4)

print("\n===================================")
print("MODEL RESULTS (validation)")
print("===================================")
print(f"RMSE: {rmse:.2f}")
print(f"MAE:  {mae:.2f}")
print(f"R2:   {r2:.4f}")


# ======================================================================
# PART 2 - MULTI-YEAR FORECAST (this is what the dashboard shows)
#
# Why a separate step?
# The GBT model above is a tree model: it cannot extrapolate to years it
# never saw (every future year would just repeat the last one). So the
# future is forecast on monthly totals with trend + seasonality, then
# split across products by their share of the last 12 months.
# ======================================================================

print("\nBuilding multi-year forecast...")

monthly_sql_profit = """
SELECT d.year, d.month,
       SUM(f.sales)  AS sales,
       SUM(f.profit) AS profit
FROM fact_sales f
JOIN dim_date d ON f.order_date_key = d.date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month
"""

monthly_sql_sales = """
SELECT d.year, d.month, SUM(f.sales) AS sales
FROM fact_sales f
JOIN dim_date d ON f.order_date_key = d.date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month
"""

product_sql_profit = """
SELECT d.year, d.month, f.product_key,
       SUM(f.sales)  AS sales,
       SUM(f.profit) AS profit
FROM fact_sales f
JOIN dim_date d ON f.order_date_key = d.date_key
GROUP BY d.year, d.month, f.product_key
"""

product_sql_sales = """
SELECT d.year, d.month, f.product_key, SUM(f.sales) AS sales
FROM fact_sales f
JOIN dim_date d ON f.order_date_key = d.date_key
GROUP BY d.year, d.month, f.product_key
"""

# Profit is used when fact_sales has a "profit" column.
try:
    monthly = pd.read_sql(monthly_sql_profit, engine)
    by_product = pd.read_sql(product_sql_profit, engine)
    has_profit = True
except Exception:
    print("No profit column in fact_sales - forecasting sales only.")
    monthly = pd.read_sql(monthly_sql_sales, engine)
    by_product = pd.read_sql(product_sql_sales, engine)
    has_profit = False

monthly = monthly.sort_values(["year", "month"]).reset_index(drop=True)
first_year = int(monthly["year"].min())
last_year = int(monthly["year"].max())


def design_matrix(frame):
    """Intercept + linear trend + month-of-year seasonality."""
    t = (frame["year"] - first_year) * 12 + frame["month"]
    cols = [np.ones(len(frame)), t.to_numpy(dtype=float)]
    for m in range(2, 13):
        cols.append((frame["month"] == m).to_numpy(dtype=float))
    return np.column_stack(cols)


future = pd.DataFrame(
    [
        {"year": y, "month": m}
        for y in range(last_year + 1, last_year + 1 + N_FORECAST_YEARS)
        for m in range(1, 13)
    ]
)

X_hist = design_matrix(monthly)
X_future = design_matrix(future)

coef_sales, *_ = np.linalg.lstsq(X_hist, monthly["sales"].to_numpy(float), rcond=None)
future["total_sales"] = np.clip(X_future @ coef_sales, 0, None)

if has_profit:
    coef_profit, *_ = np.linalg.lstsq(
        X_hist, monthly["profit"].to_numpy(float), rcond=None
    )
    future["total_profit"] = X_future @ coef_profit


# Split the monthly totals across products using the last 12 months.
by_product["period"] = by_product["year"] * 12 + by_product["month"]
recent = by_product[by_product["period"] > by_product["period"].max() - 12]

shares = recent.groupby("product_key").agg(
    sales=("sales", "sum"),
    **({"profit": ("profit", "sum")} if has_profit else {}),
).reset_index()

shares = shares[shares["sales"] > 0].copy()
shares["share"] = shares["sales"] / shares["sales"].sum()
if has_profit:
    shares["margin"] = shares["profit"] / shares["sales"]

forecast = future.merge(shares[["product_key", "share"]
                               + (["margin"] if has_profit else [])], how="cross")

forecast["predicted_sales"] = forecast["total_sales"] * forecast["share"]
if has_profit:
    forecast["predicted_profit"] = forecast["predicted_sales"] * forecast["margin"]

columns = ["year", "month", "product_key", "predicted_sales"]
if has_profit:
    columns.append("predicted_profit")

forecast[columns].to_csv(output_dir / "forecast.csv", index=False)

summary = forecast.groupby("year")[
    ["predicted_sales"] + (["predicted_profit"] if has_profit else [])
].sum()

print("\nForecast by year:")
print(summary.round(0))

print("\nPrediction results saved successfully!")
print("\n===================================")
print("Sales Prediction Finished!")
print("===================================")

spark.stop()