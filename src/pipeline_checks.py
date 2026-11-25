"""Validation checks between the pipeline stages.

Every check collects ALL problems it finds and raises one ValidationError that
lists them, so a failed task tells you everything that is wrong at once.
Nothing here modifies data: the CSV frame is only read, the databases are only
queried.
"""

import logging
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import text

log = logging.getLogger("salesflow.checks")


class ValidationError(Exception):
    def __init__(self, title, problems):
        self.title = title
        self.problems = list(problems)
        lines = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"{title}: {len(self.problems)} problem(s)\n{lines}")


def _raise_if(title, problems):
    if problems:
        raise ValidationError(title, problems)


# ----------------------------------------------------------------------
# 1. CSV
# ----------------------------------------------------------------------

REQUIRED_CSV_COLUMNS = [
    "order_id", "order_date", "ship_date", "customer", "manufactory", "product_name",
    "segment", "category", "subcategory", "region", "zip", "city", "state", "country",
    "discount", "profit", "quantity", "sales", "profit_margin",
]
NOT_NULL_CSV_COLUMNS = [
    "order_id", "order_date", "ship_date", "customer", "manufactory", "product_name",
    "segment", "category", "subcategory", "region", "discount", "profit", "quantity", "sales",
]


def _bad_rows(mask, limit=5):
    """CSV line numbers (header is line 1) of the first few offending rows."""
    rows = [int(i) + 2 for i in mask[mask].index[:limit]]
    more = int(mask.sum()) - len(rows)
    return f"{rows}" + (f" and {more} more" if more > 0 else "")


def validate_csv_frame(df, csv_path="<csv>"):
    """Check the raw CSV frame. Returns a small report; raises ValidationError on problems.

    Does not change `df`. Exact duplicate rows are reported, not removed or rejected:
    the existing pipeline keeps them as separate order items.
    """
    name = Path(str(csv_path)).name
    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in df.columns]
    _raise_if(f"CSV {name}: wrong columns", [f"missing column: {c}" for c in missing])
    if df.empty:
        raise ValidationError(f"CSV {name}", ["the file has no data rows"])

    problems = []

    for column in NOT_NULL_CSV_COLUMNS:
        nulls = df[column].isna() | (df[column].astype(str).str.strip() == "")
        if nulls.any():
            problems.append(f"{column}: {int(nulls.sum())} empty value(s), lines {_bad_rows(nulls)}")

    dates = {}
    for column in ("order_date", "ship_date"):
        parsed = pd.to_datetime(df[column], errors="coerce")
        invalid = parsed.isna() & df[column].notna()
        if invalid.any():
            problems.append(f"{column}: {int(invalid.sum())} unparseable date(s), lines {_bad_rows(invalid)}")
        dates[column] = parsed
    both = dates["order_date"].notna() & dates["ship_date"].notna()
    backwards = both & (dates["ship_date"] < dates["order_date"])
    if backwards.any():
        problems.append(f"ship_date earlier than order_date in {int(backwards.sum())} row(s), lines {_bad_rows(backwards)}")

    numeric = {}
    for column in ("discount", "profit", "quantity", "sales"):
        converted = pd.to_numeric(df[column], errors="coerce")
        invalid = converted.isna() & df[column].notna()
        if invalid.any():
            problems.append(f"{column}: {int(invalid.sum())} non-numeric value(s), lines {_bad_rows(invalid)}")
        numeric[column] = converted
    if not (numeric["discount"].dropna().between(0, 1)).all():
        bad = ~numeric["discount"].between(0, 1) & numeric["discount"].notna()
        problems.append(f"discount outside 0..1 in {int(bad.sum())} row(s), lines {_bad_rows(bad)}")
    quantity = numeric["quantity"]
    bad = (quantity <= 0) | ((quantity % 1) != 0)
    if bad.fillna(False).any():
        problems.append(f"quantity must be a positive whole number; {int(bad.fillna(False).sum())} row(s), lines {_bad_rows(bad.fillna(False))}")

    segments = df.groupby("customer")["segment"].nunique()
    conflicts = segments[segments > 1]
    if not conflicts.empty:
        problems.append(f"{len(conflicts)} customer(s) appear with more than one segment, e.g. {list(conflicts.index[:3])}")

    _raise_if(f"CSV {name} failed validation", problems)

    duplicates = int(df.duplicated().sum())
    if duplicates:
        log.warning("%s: %d exact duplicate row(s); kept as separate order items (existing behaviour)", name, duplicates)
    report = {"rows": len(df), "orders": int(df["order_id"].nunique()), "duplicate_rows": duplicates}
    log.info("CSV %s passed validation: %s", name, report)
    return report


# ----------------------------------------------------------------------
# helpers for the database checks
# ----------------------------------------------------------------------

def _columns(connection):
    result = {}
    rows = connection.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        )
    )
    for table, column in rows:
        result.setdefault(table, set()).add(column)
    return result


def _check_schema(connection, spec, problems):
    present = _columns(connection)
    ok = []
    for table, info in spec.items():
        if table not in present:
            problems.append(f"table {table} does not exist")
            continue
        missing = [c for c in info["columns"] if c not in present[table]]
        if missing:
            problems.append(f"table {table} is missing column(s): {', '.join(missing)}")
            continue
        ok.append(table)
    return ok


def _scalar(connection, sql, **params):
    return connection.execute(text(sql), params).scalar()


def _check_keys(connection, spec, tables, problems):
    for table in tables:
        info = spec[table]
        pk = info["pk"]
        nulls = _scalar(connection, f"SELECT COUNT(*) FROM {table} WHERE {pk} IS NULL")
        if nulls:
            problems.append(f"{table}.{pk} has {nulls} NULL value(s)")
        dups = _scalar(
            connection,
            f"SELECT COUNT(*) FROM (SELECT {pk} FROM {table} GROUP BY {pk} HAVING COUNT(*) > 1) d",
        )
        if dups:
            problems.append(f"{table}.{pk} has {dups} duplicated value(s)")


def _check_foreign_keys(connection, foreign_keys, tables, problems):
    for child, column, parent, parent_column in foreign_keys:
        if child not in tables or parent not in tables:
            continue
        nulls = _scalar(connection, f"SELECT COUNT(*) FROM {child} WHERE {column} IS NULL")
        if nulls:
            problems.append(f"{child}.{column} has {nulls} NULL value(s)")
        orphans = _scalar(
            connection,
            f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{column} = p.{parent_column} "
            f"WHERE c.{column} IS NOT NULL AND p.{parent_column} IS NULL",
        )
        if orphans:
            problems.append(f"{child}.{column}: {orphans} row(s) point to a missing {parent}.{parent_column}")


# ----------------------------------------------------------------------
# 3. Source database
# ----------------------------------------------------------------------

SOURCE_SPEC = {
    "customers": {"columns": ["customer_id", "customer", "segment"], "pk": "customer_id"},
    "manufacturers": {"columns": ["manufacturer_id", "manufactory"], "pk": "manufacturer_id"},
    "categories": {"columns": ["category_id", "category"], "pk": "category_id"},
    "subcategories": {"columns": ["subcategory_id", "subcategory", "category_id"], "pk": "subcategory_id"},
    "locations": {"columns": ["location_id", "zip", "city", "state", "country", "region"], "pk": "location_id"},
    "products": {"columns": ["product_id", "product_name", "manufacturer_id", "subcategory_id"], "pk": "product_id"},
    "orders": {"columns": ["order_id", "order_date", "ship_date", "customer_id", "location_id"], "pk": "order_id"},
    "order_items": {
        "columns": ["order_item_id", "order_id", "product_id", "discount", "quantity", "sales", "profit"],
        "pk": "order_item_id",
    },
}
SOURCE_FOREIGN_KEYS = [
    ("subcategories", "category_id", "categories", "category_id"),
    ("products", "manufacturer_id", "manufacturers", "manufacturer_id"),
    ("products", "subcategory_id", "subcategories", "subcategory_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("orders", "location_id", "locations", "location_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
]


def validate_source_db(engine, expected_counts=None):
    """Check the source database after the full load.

    expected_counts: {table: rows} taken from the prepared tables of this run.
    Without it, only "not empty" is checked.
    """
    problems = []
    with engine.connect() as connection:
        tables = _check_schema(connection, SOURCE_SPEC, problems)
        for table in tables:
            count = _scalar(connection, f"SELECT COUNT(*) FROM {table}")
            expected = (expected_counts or {}).get(table)
            if count == 0:
                problems.append(f"table {table} is empty")
            elif expected is not None and count != expected:
                problems.append(f"table {table} has {count} rows, this run prepared {expected}")
        _check_keys(connection, SOURCE_SPEC, tables, problems)
        _check_foreign_keys(connection, SOURCE_FOREIGN_KEYS, tables, problems)
    _raise_if("Source database validation failed", problems)
    log.info("Source database passed validation")


# ----------------------------------------------------------------------
# 5. Data warehouse
# ----------------------------------------------------------------------

DWH_SPEC = {
    "dim_customer": {
        "columns": ["customer_key", "customer_id", "customer_name", "segment",
                    "effective_date", "end_date", "is_current"],
        "pk": "customer_key",
    },
    "dim_product": {
        "columns": ["product_key", "product_id", "product_name", "manufacturer", "subcategory",
                    "category", "effective_date", "end_date", "is_current"],
        "pk": "product_key",
    },
    "dim_date": {
        "columns": ["date_key", "full_date", "day", "month", "month_name", "quarter", "year", "day_of_week"],
        "pk": "date_key",
    },
    "dim_location": {
        "columns": ["location_key", "location_id", "zip", "city", "state", "country", "region"],
        "pk": "location_key",
    },
    "fact_sales": {
        "columns": ["sales_key", "order_item_id", "order_id", "order_date_key", "ship_date_key",
                    "customer_key", "product_key", "location_key", "discount", "quantity", "sales", "profit"],
        "pk": "sales_key",
    },
}
DWH_FOREIGN_KEYS = [
    ("fact_sales", "order_date_key", "dim_date", "date_key"),
    ("fact_sales", "ship_date_key", "dim_date", "date_key"),
    ("fact_sales", "customer_key", "dim_customer", "customer_key"),
    ("fact_sales", "product_key", "dim_product", "product_key"),
    ("fact_sales", "location_key", "dim_location", "location_key"),
]
# SCD Type 2 dimensions: (table, business key)
SCD2 = [("dim_customer", "customer_id"), ("dim_product", "product_id")]
MONEY_TOLERANCE = Decimal("0.01")


def validate_dwh(dwh_engine, source_engine=None):
    """Check the warehouse after the load; optionally reconcile it with the source database."""
    problems = []
    with dwh_engine.connect() as connection:
        tables = _check_schema(connection, DWH_SPEC, problems)
        for table in tables:
            if _scalar(connection, f"SELECT COUNT(*) FROM {table}") == 0:
                problems.append(f"table {table} is empty")
        _check_keys(connection, DWH_SPEC, tables, problems)
        _check_foreign_keys(connection, DWH_FOREIGN_KEYS, tables, problems)

        if "dim_date" in tables:
            dups = _scalar(connection, "SELECT COUNT(*) FROM (SELECT full_date FROM dim_date GROUP BY full_date HAVING COUNT(*) > 1) d")
            if dups:
                problems.append(f"dim_date.full_date has {dups} duplicated date(s)")
        if "dim_location" in tables:
            dups = _scalar(connection, "SELECT COUNT(*) FROM (SELECT location_id FROM dim_location GROUP BY location_id HAVING COUNT(*) > 1) d")
            if dups:
                problems.append(f"dim_location.location_id has {dups} duplicated business key(s)")
        if "fact_sales" in tables:
            nulls = _scalar(connection, "SELECT COUNT(*) FROM fact_sales WHERE order_item_id IS NULL")
            if nulls:
                problems.append(f"fact_sales.order_item_id has {nulls} NULL value(s)")
            dups = _scalar(connection, "SELECT COUNT(*) FROM (SELECT order_item_id FROM fact_sales GROUP BY order_item_id HAVING COUNT(*) > 1) d")
            if dups:
                problems.append(f"fact_sales has {dups} order_item_id value(s) loaded more than once (business key = order_item_id)")

        for table, business_key in SCD2:
            if table not in tables:
                continue
            multiple = _scalar(
                connection,
                f"SELECT COUNT(*) FROM (SELECT {business_key} FROM {table} WHERE is_current "
                f"GROUP BY {business_key} HAVING COUNT(*) > 1) d",
            )
            if multiple:
                problems.append(f"{table}: {multiple} {business_key} value(s) have more than one current version")
            without = _scalar(
                connection,
                f"SELECT COUNT(*) FROM (SELECT {business_key} FROM {table} GROUP BY {business_key} "
                f"HAVING SUM(CASE WHEN is_current THEN 1 ELSE 0 END) = 0) d",
            )
            if without:
                problems.append(f"{table}: {without} {business_key} value(s) have no current version")
            bad_open = _scalar(connection, f"SELECT COUNT(*) FROM {table} WHERE is_current AND end_date IS NOT NULL")
            if bad_open:
                problems.append(f"{table}: {bad_open} current row(s) have an end_date")
            bad_closed = _scalar(connection, f"SELECT COUNT(*) FROM {table} WHERE NOT is_current AND end_date IS NULL")
            if bad_closed:
                problems.append(f"{table}: {bad_closed} closed row(s) have no end_date")
            reversed_ = _scalar(connection, f"SELECT COUNT(*) FROM {table} WHERE end_date < effective_date")
            if reversed_:
                problems.append(f"{table}: {reversed_} row(s) end before they start")

        fact_totals = None
        if "fact_sales" in tables:
            row = connection.execute(
                text("SELECT COUNT(*), COUNT(DISTINCT order_id), COALESCE(SUM(sales),0), COALESCE(SUM(profit),0) FROM fact_sales")
            ).one()
            fact_totals = tuple(row)

    if source_engine is not None and fact_totals is not None:
        with source_engine.connect() as connection:
            if "order_items" in _columns(connection):
                src = tuple(
                    connection.execute(
                        text("SELECT COUNT(*), COUNT(DISTINCT order_id), COALESCE(SUM(sales),0), COALESCE(SUM(profit),0) FROM order_items")
                    ).one()
                )
                labels = ["row count", "distinct orders", "total sales", "total profit"]
                for label, s, f in zip(labels, src, fact_totals):
                    if abs(Decimal(str(s)) - Decimal(str(f))) > MONEY_TOLERANCE:
                        problems.append(
                            f"fact_sales does not match the source order_items: {label} is {f} in the warehouse, "
                            f"{s} in the source"
                        )

    _raise_if("Data warehouse validation failed", problems)
    log.info("Data warehouse passed validation")


# ----------------------------------------------------------------------
# 6A. Analytics views
# ----------------------------------------------------------------------

def view_names(sql_text):
    return re.findall(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+(\w+)", sql_text, flags=re.IGNORECASE)


def validate_views(engine, names):
    problems = []
    with engine.connect() as connection:
        for name in names:
            exists = _scalar(connection, "SELECT to_regclass(:n) IS NOT NULL", n=name)
            if not exists:
                problems.append(f"view {name} does not exist")
                continue
            try:
                connection.execute(text(f"SELECT * FROM {name} LIMIT 1")).fetchall()
            except Exception as exc:
                connection.rollback()
                problems.append(f"view {name} cannot be queried: {type(exc).__name__}")
    _raise_if("Analytics views validation failed", problems)
    log.info("All %d analytics views exist and can be queried", len(names))
